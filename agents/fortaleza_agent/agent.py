"""Google ADK Agent Orchestrator for B&B Purchase - Course-aligned implementation."""

import asyncio
import json
import os
from datetime import datetime
from pathlib import Path
from typing import List

from google.adk.agents import Agent
from google.adk.models.google_llm import Gemini
from google.adk.runners import InMemoryRunner
from google.adk.tools import FunctionTool
from google.genai import types
from playwright.async_api import TimeoutError as PlaywrightTimeout, Error as PlaywrightError

from src.core import browser_service
from src.core.browser import managed_browser, get_browser_manager
from src.core.config import get_settings, Mode, MODE_SAFETY
from src.core.errors import (
    NavigationError,
    TwoFactorRequired,
    CaptchaRequired,
    ProductSoldOutError,
    ThreeDSecureRequired,
)
from src.core.logging import get_logger
from src.core.notify import send_notification
from src.tools.navigate import navigate_to_product
from src.tools.login import login_to_account
from src.tools.cart import add_to_cart
from src.tools.checkout import checkout_and_pay

logger = get_logger(__name__)

AGENT_MODEL = "gemini-2.5-flash-lite"

# Retry config for transient LLM/http errors
retry_config = types.HttpRetryOptions(
    attempts=5,           # Maximum retry attempts
    exp_base=7,           # Delay multiplier
    initial_delay=1,      # Initial delay before first retry (seconds)
    http_status_codes=[429, 500, 503, 504],  # Retry on these HTTP errors
)

# Agent system instructions - guides the agent's reasoning
# This is aligned with course concepts: clear instructions, tool usage strategy
SYSTEM_INSTRUCTION = """You are an intelligent purchase agent for Bitters & Bottles Spirit Shop.

Your goal is to purchase the specified product when instructed. The user will tell you which product to purchase.

AVAILABLE TOOLS - Use them intelligently based on page state:
1. login_to_account - Login to account (call this FIRST)
2. verify_age - Handle age verification modal (call if you encounter age prompts)
3. navigate_to_url - Navigate browser to any URL (use with direct_link)
4. search_for_product - Search for product by name (use if navigation fails)
5. add_to_cart - Add product to cart (proceeds to checkout)
6. checkout_and_pay - Complete checkout (respects mode setting)
7. notify_human - Alert human when stuck or encountering unexpected situations

REASONING STRATEGY - Be adaptive and autonomous:
- Login to account FIRST
- Call verify_age if you encounter an age verification modal (can appear anytime)
- Navigate to product using navigate_to_url with the direct_link
- If navigation fails (404, protocol error), use search_for_product as fallback
- Check each tool's response and adapt your strategy
- Use notify_human for urgent situations requiring intervention

ERROR HANDLING & NOTIFICATIONS:
- Product sold out → Auto-notified, you will see error response, stop immediately
- 2FA required during login → Auto-notified, you will see error response, stop immediately
- 3D Secure required at checkout → Auto-notified, you will see error response, stop immediately
- Protocol errors (trk.bittersandbottles.com) → Use search_for_product fallback
- Unexpected situations or stuck → Use notify_human tool, then stop
- Other errors → Attempt recovery where possible

MODES:
- dryrun: Complete all steps but DO NOT submit final order (testing selectors)
- test: Submit real order for any product (end-to-end validation)
- prod: Submit real order for Fortaleza with safety checks (verify product name matches!)

Think through each step. Observe tool results. Adapt your approach.
"""


# Tool wrappers - These connect our Playwright tools to ADK
# Following the course pattern: wrap Python functions with FunctionTool

async def ensure_browser_started():
    """
    Ensure browser is started (lazy initialization for ADK Web UI compatibility).

    This allows the agent to work in two modes:
    1. Production mode: Browser managed by run_purchase_agent() with managed_browser()
    2. ADK Web UI mode: Browser lazily initialized on first tool call

    Returns:
        BrowserManager instance with browser started
    """
    browser = get_browser_manager()
    if not browser.browser:
        logger.info("Browser not started, initializing now (lazy initialization for ADK Web UI)")
        await browser.start()
    return browser


def create_adk_tools(product_name: str = "", event_id: str = "", effective_mode: Mode = None):
    """
    Create ADK-compatible tool definitions.

    Args:
        product_name: Product name for search fallback if direct link fails
        event_id: Unique event ID for this purchase attempt (used for approval flow)
        effective_mode: Effective operating mode (after webhook override if any)
    """
    use_worker = browser_service.is_enabled()

    async def navigate_to_url(url: str) -> dict:
        """
        Navigate browser to a specific URL. Returns success/failure and current URL.

        Note: This function manages page lifecycle by closing the old page before
        assigning the new one to prevent memory leaks. The new page becomes the
        active browser.page for subsequent operations.

        Args:
            url: URL to navigate to (must be a valid HTTP/HTTPS URL)
        """
        # Input validation: Check URL format
        if not url or not isinstance(url, str):
            return {
                "status": "error",
                "message": "URL must be a non-empty string"
            }

        # Basic URL validation
        from urllib.parse import urlparse
        try:
            parsed = urlparse(url)
            if not all([parsed.scheme, parsed.netloc]):
                return {
                    "status": "error",
                    "message": f"Invalid URL format: {url}. Must include scheme (http/https) and domain."
                }
            if parsed.scheme not in ['http', 'https']:
                return {
                    "status": "error",
                    "message": f"Invalid URL scheme: {parsed.scheme}. Only http and https are supported."
                }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Invalid URL: {str(e)}"
            }

        try:
            if use_worker:
                result = await navigate_to_product(
                    direct_link=url,
                    product_name=product_name,  # fallback still available
                )
                return {
                    "status": result["status"],
                    "current_url": result.get("current_url"),
                    "message": result.get("message", "Navigation successful")
                }

            browser = await ensure_browser_started()
            result = await navigate_to_product(
                direct_link=url,
                product_name=product_name,
            )
            # Close old page before assigning new one to prevent memory leak
            if browser.page:
                await browser.page.close()
            browser.page = result["page"]
            return {
                "status": result["status"],
                "current_url": result["current_url"],
                "message": result.get("message", "Navigation successful")
            }
        except (NavigationError, PlaywrightTimeout, PlaywrightError) as e:
            logger.error("Navigate to URL failed (expected error)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except Exception as e:
            logger.exception("Navigate to URL failed (unexpected error)")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }

    async def search_for_product(product_name: str) -> dict:
        """Search for a product by name on the website. Returns search results and navigation status."""
        try:
            if use_worker:
                # use worker's search path via navigate endpoint
                result = await browser_service.navigate(None, product_name, None)
                return {
                    "status": result.get("status"),
                    "current_url": result.get("current_url"),
                    "message": result.get("message", f"Found and navigated to {product_name}")
                }

            from src.tools.navigate import _search_for_product
            browser = await ensure_browser_started()
            page = browser.page
            result = await _search_for_product(page, product_name)
            return {
                "status": result["status"],
                "current_url": result["current_url"],
                "message": f"Found and navigated to {product_name}"
            }
        except (NavigationError, PlaywrightTimeout, PlaywrightError) as e:
            logger.error("Search failed (expected error)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except Exception as e:
            logger.exception("Search failed (unexpected error)")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }

    async def verify_age_tool() -> dict:
        """Handle age verification modal if it appears. Call this whenever you encounter age verification prompts."""
        try:
            from src.tools.verify_age import verify_age
            if use_worker:
                result = await verify_age(None)  # type: ignore[arg-type]
            else:
                browser = await ensure_browser_started()
                page = browser.page
                result = await verify_age(page)
            return result
        except Exception as e:
            logger.error("Age verification failed", error=str(e))
            return {
                "status": "error",
                "message": str(e)
            }

    async def login_tool() -> dict:
        """Login to Bitters & Bottles account. Automatically checks if already logged in."""
        try:
            if use_worker:
                result = await login_to_account(None)  # type: ignore[arg-type]
            else:
                browser = await ensure_browser_started()
                page = browser.page
                result = await login_to_account(page)
            return result
        except (TwoFactorRequired, CaptchaRequired) as e:
            logger.error("Login failed (auth required)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except (PlaywrightTimeout, PlaywrightError) as e:
            logger.error("Login failed (playwright error)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except Exception as e:
            logger.exception("Login failed (unexpected error)")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }

    async def cart_tool() -> dict:
        """Add current product to shopping cart and proceed to checkout."""
        try:
            if use_worker:
                result = await add_to_cart(None, proceed_to_checkout=True)  # type: ignore[arg-type]
            else:
                browser = await ensure_browser_started()
                page = browser.page
                result = await add_to_cart(page, proceed_to_checkout=True)
            return result
        except ProductSoldOutError as e:
            logger.error("Add to cart failed (sold out)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except (PlaywrightTimeout, PlaywrightError) as e:
            logger.error("Add to cart failed (playwright error)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except Exception as e:
            logger.exception("Add to cart failed (unexpected error)")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }

    async def checkout_tool() -> dict:
        """Complete checkout with payment. In dryrun mode, does NOT submit. In test/prod mode, submits real order."""
        try:
            # Use effective_mode to determine submit behavior
            # This ensures webhook mode override is respected
            submit_order = effective_mode in [Mode.PROD, Mode.TEST] if effective_mode else None
            
            if use_worker:
                result = await checkout_and_pay(None, submit_order=submit_order, run_id=event_id)  # type: ignore[arg-type]
            else:
                browser = await ensure_browser_started()
                page = browser.page
                result = await checkout_and_pay(page, submit_order=submit_order, run_id=event_id)
            return result
        except ThreeDSecureRequired as e:
            logger.error("Checkout failed (3DS required)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except (PlaywrightTimeout, PlaywrightError) as e:
            logger.error("Checkout failed (playwright error)", error=str(e), error_type=type(e).__name__)
            return {
                "status": "error",
                "message": str(e)
            }
        except Exception as e:
            logger.exception("Checkout failed (unexpected error)")
            return {
                "status": "error",
                "message": f"Unexpected error: {str(e)}"
            }

    async def notify_human_tool(reason: str, details: str) -> dict:
        """Notify human for unexpected situations or when stuck. Use for: unknown errors, unexpected page states, or when you've tried multiple approaches and nothing works. Note: 2FA, 3DS, and sold-out are already auto-notified, so only use this for OTHER situations."""
        logger.warning(
            "Agent requesting human assistance",
            reason=reason,
            details=details
        )
        send_notification(
            f"🚨 Human Assistance Needed",
            f"Reason: {reason}\n\nDetails: {details}",
            priority=2  # Emergency priority - requires acknowledgment
        )
        return {
            "status": "notified",
            "reason": reason,
            "message": "Human has been notified"
        }

    return [
        FunctionTool(navigate_to_url),
        FunctionTool(search_for_product),
        FunctionTool(verify_age_tool),
        FunctionTool(login_tool),
        FunctionTool(cart_tool),
        FunctionTool(checkout_tool),
        FunctionTool(notify_human_tool)
    ]


def log_agent_events(events: List, event_id: str, product_name: str) -> None:
    """
    Log agent execution events to JSON file for observability.

    Course-aligned implementation: Captures agent reasoning, tool calls,
    and responses for later inspection and debugging.

    Args:
        events: List of events from runner.run_debug()
        event_id: Unique event ID for this purchase attempt
        product_name: Product name being purchased
    """
    # Create logs/traces directory
    traces_dir = Path("logs/traces")
    traces_dir.mkdir(parents=True, exist_ok=True)

    # Create trace file with timestamp
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    trace_file = traces_dir / f"{event_id}_{timestamp}.json"

    # Parse events into structured format
    trace_data = {
        "event_id": event_id,
        "product_name": product_name,
        "timestamp": datetime.now().isoformat(),
        "total_events": len(events),
        "events": []
    }

    total_prompt_tokens = 0
    total_response_tokens = 0

    for idx, event in enumerate(events):
        event_data = {
            "event_number": idx + 1,
            "author": getattr(event, 'author', 'unknown'),
            "finish_reason": str(getattr(event, 'finish_reason', None)),
            "content_parts": []
        }

        # Extract content parts (agent messages, tool calls, responses)
        if hasattr(event, 'content') and event.content:
            for part in event.content.parts:
                if hasattr(part, 'text') and part.text:
                    # Agent reasoning/message
                    event_data["content_parts"].append({
                        "type": "agent_message",
                        "text": part.text.strip()
                    })
                elif hasattr(part, 'function_call') and part.function_call:
                    # Tool call
                    event_data["content_parts"].append({
                        "type": "tool_call",
                        "tool": getattr(part.function_call, 'name', 'unknown'),
                        "args": getattr(part.function_call, 'args', {})
                    })
                elif hasattr(part, 'function_response') and part.function_response:
                    # Tool response
                    event_data["content_parts"].append({
                        "type": "tool_response",
                        "tool": getattr(part.function_response, 'name', 'unknown'),
                        "response": getattr(part.function_response, 'response', {})
                    })

        # Extract token usage
        if hasattr(event, 'usage_metadata') and event.usage_metadata:
            usage = event.usage_metadata
            event_data["token_usage"] = {
                "prompt_tokens": usage.prompt_token_count,
                "response_tokens": usage.candidates_token_count,
                "total_tokens": usage.total_token_count
            }
            total_prompt_tokens += usage.prompt_token_count
            total_response_tokens += usage.candidates_token_count

        trace_data["events"].append(event_data)

    # Add summary statistics
    trace_data["summary"] = {
        "total_prompt_tokens": total_prompt_tokens,
        "total_response_tokens": total_response_tokens,
        "total_tokens": total_prompt_tokens + total_response_tokens
    }

    # Write to file
    with open(trace_file, 'w') as f:
        json.dump(trace_data, f, indent=2, default=str)

    logger.info(
        "Agent trace saved",
        trace_file=str(trace_file),
        total_events=len(events),
        total_tokens=total_prompt_tokens + total_response_tokens
    )

async def run_purchase_agent(
    direct_link: str,
    product_name: str,
    event_id: str,
    mode_override: str | None = None
) -> dict:
    """
    Run the ADK-powered purchase agent using course-aligned patterns.

    Args:
        direct_link: Direct URL to product from email
        product_name: Product name (for search fallback)
        event_id: Unique event ID for this purchase attempt
        mode_override: Optional mode override (dryrun, test, or prod) from webhook payload

    Returns:
        dict with execution result
    """
    settings = get_settings()
    
    # Override mode if specified in webhook payload
    # Safety rule: Can only override to SAME or SAFER modes
    # MODE_SAFETY defines levels (higher = safer): DRYRUN(3) > TEST(2) > PROD(1)
    # 
    # NOTE: This validation is INTENTIONALLY duplicated in webhook.py (lines 289-324)
    # Defense-in-depth strategy:
    # - Webhook layer: Fail fast at API boundary (returns HTTP 400)
    # - Agent layer: Graceful fallback + handles direct agent invocations
    # Both layers are necessary for comprehensive security coverage.
    if mode_override:
        try:
            requested_mode = Mode(mode_override.lower())
            env_mode_safety = MODE_SAFETY[settings.mode]
            requested_mode_safety = MODE_SAFETY[requested_mode]
            
            # Only allow override if requested mode is SAFER (higher safety level)
            if requested_mode_safety >= env_mode_safety:
                effective_mode = requested_mode
                if requested_mode != settings.mode:
                    logger.info(
                        "Mode overridden to safer mode",
                        environment_mode=settings.mode.value,
                        effective_mode=effective_mode.value
                    )
                else:
                    # Log when mode matches environment (helps debugging)
                    logger.info(
                        "Mode override matches environment mode",
                        mode=settings.mode.value
                    )
            else:
                logger.warning(
                    "Rejecting mode override to less safe mode",
                    requested_mode=requested_mode.value,
                    environment_mode=settings.mode.value,
                    reason=f"Cannot override from {settings.mode.value} (safety={env_mode_safety}) to {requested_mode.value} (safety={requested_mode_safety})"
                )
                effective_mode = settings.mode
        except ValueError:
            logger.warning(
                "Invalid mode override in webhook payload, using environment mode",
                invalid_mode=mode_override,
                environment_mode=settings.mode.value
            )
            effective_mode = settings.mode
    else:
        effective_mode = settings.mode

    # Note: GOOGLE_API_KEY is set once at application startup in src/app/main.py lifespan()
    # to avoid runtime os.environ mutation and ensure thread safety

    logger.info(
        "Starting ADK purchase agent (course-aligned)",
        event_id=event_id,
        mode=effective_mode.value,
        product=product_name
    )

    # Send start notification
    send_notification(
        f"🤖 AI Agent Starting",
        f"Mode: {effective_mode.value}\nProduct: {product_name}\nEvent: {event_id}"
    )

    try:
        async with managed_browser():
            # Create tools with product_name for search fallback, event_id for approval,
            # and effective_mode to ensure checkout respects mode override
            tools = create_adk_tools(product_name=product_name, event_id=event_id, effective_mode=effective_mode)

            # Create Agent (following course pattern)
            agent = Agent(
                name="bnb_purchase_agent",
                model=Gemini(
                    model=AGENT_MODEL,
                    retry_config=retry_config,
                    api_key=settings.google_api_key,
                ),
                description="AI agent that autonomously purchases products from Bitters & Bottles Spirit Shop.",
                instruction=SYSTEM_INSTRUCTION,
                tools=tools,
            )

            logger.info("Agent created with ADK framework")

            # Create Runner (following course pattern)
            runner = InMemoryRunner(agent=agent)

            logger.info("Runner created")

            # Craft the user prompt
            user_prompt = f"""Purchase this product:

Product: {product_name}
Direct Link: {direct_link}
Mode: {effective_mode.value}
Event ID: {event_id}

Instructions:
1. Login to the account FIRST
2. Call verify_age if you encounter an age verification modal
3. Navigate to product using navigate_to_url with the direct_link
4. If navigation fails, use search_for_product as fallback
5. Add to cart and proceed to checkout
6. Complete checkout ({"DO NOT submit - dryrun mode" if effective_mode == Mode.DRYRUN else "SUBMIT the order - test/prod mode"})

Important:
- Critical errors (2FA, 3DS, sold out) are auto-notified - just stop when you see them
- If you get stuck or encounter unexpected situations → use notify_human tool
- Check each tool's response before proceeding to next step

Begin the purchase process now."""

            logger.info("Sending prompt to agent")

            # Run agent with debug mode (creates session automatically)
            response = await runner.run_debug(user_prompt)

            logger.info("Agent execution completed", total_events=len(response))

            # Log agent events for observability (course-aligned)
            log_agent_events(response, event_id, product_name)

            # Send success notification
            send_notification(
                f"✅ Purchase {'Completed' if effective_mode == Mode.PROD else 'Simulated'}",
                f"Product: {product_name}\nMode: {effective_mode.value}\nEvent: {event_id}\n\nAgent completed successfully"
            )

            return {
                "status": "success",
                "event_id": event_id,
                "mode": effective_mode.value,
                "agent_response": str(response)
            }

    except Exception as e:
        logger.error(
            "Purchase agent failed",
            event_id=event_id,
            error=str(e),
            exc_info=True
        )

        send_notification(
            f"❌ Purchase Failed",
            f"Product: {product_name}\nError: {str(e)}\nEvent: {event_id}",
            priority=2  # Emergency - requires acknowledgment
        )

        return {
            "status": "error",
            "event_id": event_id,
            "mode": effective_mode.value,
            "error": str(e)
        }


# ============================================================================
# Module-Level Agent Instance (ADK Web UI Requirement)
# ============================================================================
# This module-level agent is instantiated at import time to support the ADK Web UI.
# The Web UI requires a top-level variable named 'root_agent' for agent discovery.
#
# IMPORTANT NOTES:
# 1. This initialization happens at module import time with environment guard:
#    - Only created if GOOGLE_API_KEY is already set in environment
#    - It's only used for ADK Web UI (development tool, not production)
#    - Production code uses run_purchase_agent() which creates agents dynamically
#
# 2. For ADK Web UI usage:
#    - Ensure GOOGLE_API_KEY is exported in your shell before running
#    - Run: export GOOGLE_API_KEY=your_key && adk web agents/ --port=4200 --reload
#
# 3. For production (FastAPI webhook):
#    - This root_agent will not be created (GOOGLE_API_KEY set in lifespan, after import)
#    - run_purchase_agent() creates agents with proper lifecycle management
#    - GOOGLE_API_KEY is set once at application startup in lifespan()
# ============================================================================

# Only create root_agent if GOOGLE_API_KEY is already set (for ADK Web UI)
# Production imports this module before setting GOOGLE_API_KEY, so root_agent won't be created
import os
if os.getenv("GOOGLE_API_KEY"):
    root_agent = Agent(
        name="bnb_purchase_agent",
        model=Gemini(
            model=AGENT_MODEL,
            retry_config=retry_config,
            api_key=os.getenv("GOOGLE_API_KEY"),
        ),
        description="AI agent that autonomously purchases products from Bitters & Bottles Spirit Shop.",
        instruction=SYSTEM_INSTRUCTION,
        tools=create_adk_tools(),
    )
else:
    # For production: root_agent not needed (run_purchase_agent() is used instead)
    root_agent = None  # type: ignore
