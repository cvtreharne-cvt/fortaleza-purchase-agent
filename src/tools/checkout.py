"""
Checkout and payment processing.

This module handles the complete checkout workflow:
1. Verifies we're on the checkout page
2. Selects "Pick up" as the delivery method
3. Selects pickup location (South SF preferred, SF fallback)
4. Fills in credit card payment information (PCI-compliant iframes)
5. Extracts order summary (subtotal, tax, total, pickup location)
6. Optionally submits the order based on mode setting

The checkout process supports dryrun mode for testing without actual purchases,
and includes detection for 3D Secure challenges that require manual intervention.
"""

import asyncio
import time
from playwright.async_api import Page, TimeoutError as PlaywrightTimeout

from ..core import browser_service
from ..core.logging import get_logger
from ..core.notify import get_pushover_client
from ..core.secrets import get_secret_manager
from ..core.config import get_settings, Mode
from ..core.errors import ThreeDSecureRequired, ApprovalRejectedError, ApprovalTimeoutError
from ..core.approval import create_approval_request, get_approval_status, delete_approval_request

logger = get_logger(__name__)

# Timeout constants (in milliseconds)
SELECTOR_WAIT_TIMEOUT = 3000  # Standard timeout for element selectors
PICKUP_LOCATION_TIMEOUT = 2000  # Timeout for pickup location detection
PAGE_LOAD_DELAY = 1000  # Delay after clicking pickup option
PAYMENT_SECTION_DELAY = 1000  # Delay after scrolling to payment section
CARD_NUMBER_IFRAME_TIMEOUT = 5000  # Timeout for card number iframe
CARD_INPUT_TIMEOUT = 5000  # Timeout for card input field
FIELD_TRANSITION_DELAY = 500  # Delay between form field transitions
TYPING_DELAY = 30  # Delay between keystrokes (ms)
INITIAL_TYPING_DELAY = 200  # Delay before starting to type in card field
ORDER_SUBMISSION_DELAY = 5000  # Wait time after clicking Pay now
SECURE_CHECK_TIMEOUT = 2000  # Timeout for 3D Secure detection
ERROR_CHECK_TIMEOUT = 2000  # Timeout for payment error detection

# Approval polling constants
APPROVAL_TIMEOUT_MINUTES = 10  # Total time to wait for human approval
APPROVAL_POLL_INTERVAL_SECONDS = 2  # How often to check approval status


async def checkout_and_pay(page: Page, submit_order: bool = None, run_id: str = None) -> dict:
    """
    Complete checkout process with payment information.

    This function:
    - Verifies we're on checkout page
    - Selects "Pick up" as the Delivery method
    - Selects pickup location (South SF preferred, SF fallback)
    - Fills in credit card information
    - Fills in cardholder name
    - Requests human approval (if submitting order)
    - Optionally submits the order (based on mode and approval)

    Args:
        page: Playwright page (should be on checkout page)
        submit_order: If True, submits order. If None, uses mode setting
                     (dryrun/test=False, prod=True)
        run_id: Unique identifier for this agent run (required for approval)

    Returns:
        dict with status, message, and order details

    Raises:
        ThreeDSecureRequired: If 3D Secure verification is needed
        Exception: For other failures (including approval rejection/timeout)
    """
    settings = get_settings()

    # Determine if we should submit based on mode
    if submit_order is None:
        submit_order = settings.mode == Mode.PROD

    logger.info("Starting checkout process", submit_order=submit_order, mode=settings.mode.value, run_id=run_id)

    # Guard early when running local Python Playwright: must already be on checkout
    if not browser_service.is_enabled() and "checkout" not in page.url.lower():
        logger.warning("Aborting checkout - not on checkout page", current_url=page.url)
        raise Exception(f"Not on checkout page. Current URL: {page.url}")

    # Browser worker path (Node Playwright)
    if browser_service.is_enabled():
        secret_manager = get_secret_manager()
        payment = {
            "cc_number": secret_manager.get_secret("cc_number"),
            "cc_exp_month": secret_manager.get_secret("cc_exp_month"),
            "cc_exp_year": secret_manager.get_secret("cc_exp_year"),
            "cc_cvv": secret_manager.get_secret("cc_cvv"),
            "billing_name": secret_manager.get_secret("billing_name"),
        }

        # First, get order summary without submitting (submit_order=False temporarily)
        result = await browser_service.checkout(False, payment)
        status = result.get("status")
        if status == "error":
            error_type = result.get("error_type")
            if error_type == "ThreeDSecureRequired":
                raise ThreeDSecureRequired(result.get("message", "3DS required"))
            raise Exception(result.get("message", "Checkout failed"))

        order_summary = result.get("order_summary", {})
        logger.info("Order summary from browser worker", **order_summary)

        # Request human approval if submitting order
        if submit_order:
            if run_id:
                logger.info("Requesting human approval for purchase", run_id=run_id)

                # Create approval request
                create_approval_request(
                    run_id=run_id,
                    order_summary=order_summary,
                    timeout_minutes=APPROVAL_TIMEOUT_MINUTES
                )

                # Send Pushover notification with approval request
                pushover_client = get_pushover_client()

                # Validate webhook configuration before proceeding
                settings.validate_webhook_config()

                # Construct approval callback URLs using configured base URL
                approve_url = f"{settings.webhook_base_url}/approval/{run_id}/approve"
                reject_url = f"{settings.webhook_base_url}/approval/{run_id}/reject"

                notification_sent = pushover_client.send_approval_request(
                    run_id=run_id,
                    order_summary=order_summary,
                    approve_url=approve_url,
                    reject_url=reject_url
                )

                if not notification_sent:
                    # Clean up approval request if notification failed
                    delete_approval_request(run_id)
                    raise Exception("Failed to send approval notification")

                # Poll for approval
                logger.info("Polling for approval decision",
                           timeout_minutes=APPROVAL_TIMEOUT_MINUTES,
                           poll_interval_seconds=APPROVAL_POLL_INTERVAL_SECONDS)

                approval_status = await _poll_for_approval(run_id)

                if approval_status["decision"] == "approved":
                    logger.info("Purchase approved by human", run_id=run_id)
                elif approval_status["decision"] == "rejected":
                    logger.warning("Purchase rejected by human", run_id=run_id)
                    raise ApprovalRejectedError("Purchase rejected by human approval")
                elif approval_status["decision"] == "timeout":
                    logger.warning("Approval request timed out", run_id=run_id)
                    raise ApprovalTimeoutError(f"Approval request timed out after {APPROVAL_TIMEOUT_MINUTES} minutes")
                else:
                    logger.error("Unexpected approval status", status=approval_status)
                    raise Exception(f"Unexpected approval status: {approval_status['decision']}")
            else:
                logger.warning("No run_id provided - skipping approval (not recommended for production)")

            # Now submit the order for real
            logger.info("Submitting order via browser worker")
            result = await browser_service.checkout(True, payment)
            status = result.get("status")
            if status == "error":
                error_type = result.get("error_type")
                if error_type == "ThreeDSecureRequired":
                    raise ThreeDSecureRequired(result.get("message", "3DS required"))
                raise Exception(result.get("message", "Checkout failed"))

        return result
    
    try:
        # Wait for page to fully load
        await page.wait_for_load_state("domcontentloaded")

        # Verify pick-up is selected (should be default)
        await _verify_pickup_selected(page)
        
        # Detect pickup location (returns location string or None)
        pickup_location = await _select_pickup_location(page)
        
        # Fill in payment information
        await _fill_payment_info(page)
        
        # Get order summary before submitting
        order_summary = await _get_order_summary(page, pickup_location=pickup_location)
        logger.info("Order summary", **order_summary)
        
        if submit_order:
            # Request human approval before submitting
            if run_id:
                logger.info("Requesting human approval for purchase", run_id=run_id)

                # Create approval request
                create_approval_request(
                    run_id=run_id,
                    order_summary=order_summary,
                    timeout_minutes=APPROVAL_TIMEOUT_MINUTES
                )

                # Send Pushover notification with approval request
                pushover_client = get_pushover_client()

                # Validate webhook configuration before proceeding
                settings.validate_webhook_config()

                # Construct approval callback URLs using configured base URL
                approve_url = f"{settings.webhook_base_url}/approval/{run_id}/approve"
                reject_url = f"{settings.webhook_base_url}/approval/{run_id}/reject"

                notification_sent = pushover_client.send_approval_request(
                    run_id=run_id,
                    order_summary=order_summary,
                    approve_url=approve_url,
                    reject_url=reject_url
                )

                if not notification_sent:
                    # Clean up approval request if notification failed
                    delete_approval_request(run_id)
                    raise Exception("Failed to send approval notification")

                # Poll for approval
                logger.info("Polling for approval decision",
                           timeout_minutes=APPROVAL_TIMEOUT_MINUTES,
                           poll_interval_seconds=APPROVAL_POLL_INTERVAL_SECONDS)

                approval_status = await _poll_for_approval(run_id)

                if approval_status["decision"] == "approved":
                    logger.info("Purchase approved by human", run_id=run_id)
                elif approval_status["decision"] == "rejected":
                    logger.warning("Purchase rejected by human", run_id=run_id)
                    raise ApprovalRejectedError("Purchase rejected by human approval")
                elif approval_status["decision"] == "timeout":
                    logger.warning("Approval request timed out", run_id=run_id)
                    raise ApprovalTimeoutError(f"Approval request timed out after {APPROVAL_TIMEOUT_MINUTES} minutes")
                else:
                    logger.error("Unexpected approval status", status=approval_status)
                    raise Exception(f"Unexpected approval status: {approval_status['decision']}")
            else:
                logger.warning("No run_id provided - skipping approval (not recommended for production)")

            # Submit the order
            logger.info("Submitting order for real")
            result = await _submit_order(page)

            return {
                "status": "success",
                "message": "Order submitted successfully",
                "order_summary": order_summary,
                **result
            }
        else:
            logger.info("Dryrun mode - NOT submitting order", order_summary=order_summary)
            return {
                "status": "success",
                "message": "Checkout completed (dryrun - order NOT submitted)",
                "order_summary": order_summary,
                "current_url": page.url
            }

    except ThreeDSecureRequired as e:
        # Send emergency notification immediately
        logger.error("3D Secure required - sending emergency notification")
        send_notification(
            "🚨 3D Secure Required",
            "3D Secure authentication is required for payment. Please complete manually.",
            priority=2  # Emergency - requires acknowledgment
        )
        raise
    except Exception as e:
        logger.error("Checkout failed", error=str(e))
        raise


async def _poll_for_approval(run_id: str) -> dict:
    """
    Poll for human approval decision.

    Polls the approval status every APPROVAL_POLL_INTERVAL_SECONDS
    for up to APPROVAL_TIMEOUT_MINUTES.

    Args:
        run_id: Unique identifier for this approval request

    Returns:
        dict with approval status (includes 'decision' field)

    Raises:
        Exception: If approval request not found or polling fails
    """
    timeout_seconds = APPROVAL_TIMEOUT_MINUTES * 60
    poll_count = 0
    max_polls = timeout_seconds // APPROVAL_POLL_INTERVAL_SECONDS

    while poll_count < max_polls:
        approval_status = get_approval_status(run_id)

        if not approval_status:
            raise Exception(f"Approval request {run_id} not found")

        # Check if decision has been made
        if approval_status["decision"] is not None:
            logger.info("Approval decision received",
                       run_id=run_id,
                       decision=approval_status["decision"],
                       polls=poll_count)
            return approval_status

        # Wait before next poll
        await asyncio.sleep(APPROVAL_POLL_INTERVAL_SECONDS)
        poll_count += 1

        if poll_count % 30 == 0:  # Log every minute
            logger.debug("Still waiting for approval",
                        run_id=run_id,
                        elapsed_minutes=poll_count * APPROVAL_POLL_INTERVAL_SECONDS / 60)

    # Timeout reached - check one final time
    final_status = get_approval_status(run_id)
    if final_status and final_status["decision"] is not None:
        return final_status

    logger.warning("Approval polling timed out", run_id=run_id)
    raise Exception(f"Approval polling timed out after {APPROVAL_TIMEOUT_MINUTES} minutes")


async def _verify_pickup_selected(page: Page) -> None:
    """Verify that Pick-up delivery option is selected."""
    # Look for selected pickup radio button
    pickup_selectors = [
        "input[type='radio'][value*='pick']:checked",
        "input[type='radio'][id*='pickup']:checked",
        "input[type='radio']:checked + label:has-text('Pick')",
    ]
    
    pickup_selected = False
    for selector in pickup_selectors:
        element = await page.query_selector(selector)
        if element:
            logger.debug("Pick-up is selected", selector=selector)
            pickup_selected = True
            break
    
    if not pickup_selected:
        # Try to find and click pickup option
        logger.info("Pick-up not selected, attempting to select it")
        pickup_click_selectors = [
            "input[type='radio'][value*='pick']",
            "label:has-text('Pick-up')",
            "label:has-text('Pick up')",
        ]
        
        for selector in pickup_click_selectors:
            try:
                element = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
                if element:
                    await element.click()
                    logger.info("Selected pick-up option")
                    await page.wait_for_timeout(PAGE_LOAD_DELAY)
                    return
            except PlaywrightTimeout:
                continue
        
        logger.warning("Could not verify pick-up is selected")


async def _select_pickup_location(page: Page) -> str | None:
    """Verify and return the selected pickup location.
    
    Returns:
        The pickup location string, or None if not detected
    """
    # Pickup location is automatically selected when "Pick up" is chosen
    # The site selects the closest location by default
    
    logger.info("Checking selected pickup location")
    
    # Try to find text indicating which location is selected
    # Look for the pickup location section
    pickup_text_selectors = [
        "text=/South San Francisco.*240 Grand/i",
        "text=/San Francisco.*Fell Street/i",
        "text=/South San Francisco/i",
        "text=/1275 Fell Street/i",
        "text=/240 Grand Ave/i",
    ]
    
    for selector in pickup_text_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=PICKUP_LOCATION_TIMEOUT)
            if element:
                location_text = await element.inner_text()
                # Extract just the first line (location name)
                location = location_text.split("\n")[0].strip()[:50]
                logger.info("Pickup location detected", location=location)
                return location
        except Exception:
            continue
    
    logger.info("Using auto-selected pickup location (unable to verify which)")
    return None


async def _fill_payment_info(page: Page) -> None:
    """Fill in credit card payment information."""
    logger.info("Filling payment information")
    
    # Scroll to payment section to ensure fields are loaded
    payment_section = await page.query_selector("text=/Payment/i")
    if payment_section:
        await payment_section.scroll_into_view_if_needed()
        await page.wait_for_timeout(PAYMENT_SECTION_DELAY)
        logger.debug("Scrolled to payment section")
    
    # Get payment info from secrets
    secret_manager = get_secret_manager()
    cc_number = secret_manager.get_secret("cc_number")
    cc_exp_month = secret_manager.get_secret("cc_exp_month")
    cc_exp_year = secret_manager.get_secret("cc_exp_year")
    cc_cvv = secret_manager.get_secret("cc_cvv")
    billing_name = secret_manager.get_secret("billing_name")
    
    # Payment fields are in iframes (Shopify PCI-compliant checkout)
    # We need to find the iframes and fill them
    # Important: The iframe title="Field container for: Card number" etc.
    
    # Fill card number (in iframe)
    logger.debug("Looking for card number iframe")
    try:
        # Look for iframe with title containing "Card number"
        card_number_iframe = await page.wait_for_selector(
            "iframe[title*='Field container for: Card number' i], iframe[name*='number' i]",
            timeout=CARD_NUMBER_IFRAME_TIMEOUT
        )
        if card_number_iframe:
            card_frame = await card_number_iframe.content_frame()
            card_input = await card_frame.wait_for_selector("input", timeout=CARD_INPUT_TIMEOUT)
            await card_input.click(force=True)
            await page.wait_for_timeout(INITIAL_TYPING_DELAY)
            await card_input.type(cc_number, delay=TYPING_DELAY)
            logger.info("Filled card number", last_4=cc_number[-4:])
            # Press Tab to move to expiration field
            await card_input.press("Tab")
            await page.wait_for_timeout(FIELD_TRANSITION_DELAY)
        else:
            raise Exception("Could not find card number iframe")
    except Exception as e:
        logger.error("Failed to fill card number", error=str(e))
        raise
    
    # Fill expiration date (focus should already be here after Tab)
    logger.debug("Filling expiration date")
    try:
        exp_value = f"{cc_exp_month.zfill(2)}{cc_exp_year[-2:]}"
        await page.keyboard.type(exp_value, delay=TYPING_DELAY)
        logger.info("Filled expiration date", value=f"{cc_exp_month}/{cc_exp_year[-2:]}")
        # Tab to CVV field
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(FIELD_TRANSITION_DELAY)
    except Exception as e:
        logger.warning("Could not fill expiration date", error=str(e))

    # Fill security code (CVV, focus should already be here after Tab)
    logger.debug("Filling CVV")
    try:
        await page.keyboard.type(cc_cvv, delay=TYPING_DELAY)
        logger.info("Filled CVV")
        # Tab to name on card field
        await page.keyboard.press("Tab")
        await page.wait_for_timeout(FIELD_TRANSITION_DELAY)
    except Exception as e:
        logger.warning("Could not fill CVV", error=str(e))

    # Fill name on card (focus should already be here after Tab)
    logger.debug("Filling name on card")
    try:
        await page.keyboard.type(billing_name, delay=TYPING_DELAY)
        logger.info("Filled name on card")
    except Exception as e:
        logger.warning("Could not fill name on card", error=str(e))
    
    logger.info("Payment information filled successfully")


async def _get_order_summary(page: Page, pickup_location: str | None = None) -> dict:
    """Extract order summary information from checkout page.

    Args:
        page: The Playwright page object
        pickup_location: The pickup location string (if already detected), or None
    """
    summary = {
        "subtotal": "unknown",
        "tax": "unknown",
        "total": "unknown",
        "pickup_location": pickup_location or "unknown",
        "quantity": "unknown",
    }

    # Try to get subtotal - grandparent contains "Subtotal\n$36.50"
    try:
        subtotal_elem = await page.query_selector("text=/^Subtotal$/i")
        if subtotal_elem:
            grandparent = await subtotal_elem.evaluate_handle("el => el.parentElement.parentElement")
            text = await grandparent.inner_text()
            # Extract price from text like "Subtotal\n$36.50"
            if "$" in text:
                price = text.split("$")[1].strip().split()[0]
                summary["subtotal"] = f"${price}"
    except Exception as e:
        logger.debug("Could not get subtotal", error=str(e))

    # Try to get tax - level 4 parent contains "Estimated taxes\n$3.61"
    try:
        tax_elem = await page.query_selector("text=/^Estimated taxes$/i")
        if tax_elem:
            # Go up 4 levels to find the container with both label and value
            parent4 = await tax_elem.evaluate_handle(
                "el => el.parentElement?.parentElement?.parentElement?.parentElement"
            )
            text = await parent4.inner_text()
            # Extract price from text like "Estimated taxes\n$3.61"
            if "$" in text:
                price = text.split("$")[1].strip().split()[0]
                summary["tax"] = f"${price}"
    except Exception as e:
        logger.debug("Could not get tax", error=str(e))

    # Try to get total - grandparent contains "Total\nUSD\n$40.11"
    try:
        total_elem = await page.query_selector("text=/^Total$/i")
        if total_elem:
            grandparent = await total_elem.evaluate_handle("el => el.parentElement.parentElement")
            text = await grandparent.inner_text()
            # Extract price from text like "Total\nUSD\n$40.11"
            if "$" in text:
                price = text.split("$")[1].strip().split()[0]
                summary["total"] = f"${price}"
    except Exception as e:
        logger.debug("Could not get total", error=str(e))

    # Note: pickup_location is passed in as a parameter (already detected earlier)

    # Try to get quantity - sum visible item quantities in the order summary
    try:
        # Shopify checkout exposes line_items with quantity; prefer this if available
        qty_from_shopify = await page.evaluate(
            """() => {
                try {
                    const li = window.Shopify?.checkout?.line_items || [];
                    return li.reduce((sum, item) => sum + (item.quantity || 0), 0);
                } catch (e) {
                    return null;
                }
            }"""
        )
        if qty_from_shopify and qty_from_shopify > 0:
            summary["quantity"] = qty_from_shopify

        # Try to find quantity by looking for "Quantity" label followed by aria-hidden span
        # This is the pattern used in Shopify checkout pages
        if summary["quantity"] == "unknown":
            qty_from_label = await page.evaluate(
                """() => {
                    try {
                        // Find all spans that contain "Quantity" text
                        const allSpans = Array.from(document.querySelectorAll('span'));
                        const qtyLabel = allSpans.find(span => span.textContent.trim().toLowerCase() === 'quantity');

                        if (qtyLabel) {
                            // Look for next sibling with aria-hidden="true"
                            let nextSibling = qtyLabel.nextElementSibling;
                            if (nextSibling && nextSibling.tagName === 'SPAN' && nextSibling.getAttribute('aria-hidden') === 'true') {
                                const qtyText = nextSibling.textContent.trim();
                                const match = qtyText.match(/\\d+/);
                                return match ? parseInt(match[0], 10) : null;
                            }
                        }
                        return null;
                    } catch (e) {
                        return null;
                    }
                }"""
            )

            if qty_from_label and qty_from_label > 0:
                summary["quantity"] = qty_from_label

        qty_total = 0
        qty_nodes = await page.query_selector_all(
            ".product__quantity, .order-summary__quantity, [data-checkout-line-item] .quantity, "
            ".product-table__quantity, select[data-cartitem-quantity], [data-quantity], [data-cart-item-quantity], "
            "select[aria-label='Quantity'], select[id^='quantity'], select[name*='quantity'], "
            ".product-thumbnail__quantity, span.product-thumbnail__quantity, span[class*='thumbnail__quantity'], "
            "span[data-order-summary-section='line-item-quantity']"
        )
        for node in qty_nodes:
            # For select elements, use value attribute; otherwise parse inner text
            tag = (await node.evaluate("el => el.tagName")).lower()
            if tag == "select":
                value = await node.get_attribute("value")
                if value and value.isdigit():
                    qty_total += int(value)
                else:
                    # try selected option text
                    option = await node.query_selector("option:checked")
                    if option:
                        opt_text = (await option.inner_text() or "").strip()
                        digits = "".join(ch for ch in opt_text if ch.isdigit())
                        if digits:
                            qty_total += int(digits)
            else:
                text = (await node.inner_text() or "").strip()
                digits = "".join(ch for ch in text if ch.isdigit())
                if digits:
                    qty_total += int(digits)
        if qty_total > 0:
            summary["quantity"] = qty_total
    except Exception as e:
        logger.debug("Could not get quantity", error=str(e))

    # Log warnings for any fields that could not be extracted
    if summary["subtotal"] == "unknown":
        logger.warning("Could not extract subtotal from order summary")
    if summary["tax"] == "unknown":
        logger.warning("Could not extract tax from order summary")
    if summary["total"] == "unknown":
        logger.warning("Could not extract total from order summary")
    if summary["pickup_location"] == "unknown":
        logger.warning("Could not determine pickup location")

    return summary


async def _submit_order(page: Page) -> dict:
    """Submit the order."""
    logger.info("Looking for 'Pay now' button")
    
    # Based on screenshot: blue button with "Pay now"
    submit_selectors = [
        "button:has-text('Pay now')",
        "button[type='submit']:has-text('Pay')",
        "button:has-text('Complete order')",
        "button:has-text('Place order')",
        "button[type='submit']",
        "#submit-button",
    ]
    
    submit_button = None
    for selector in submit_selectors:
        try:
            submit_button = await page.wait_for_selector(selector, timeout=SELECTOR_WAIT_TIMEOUT)
            if submit_button:
                logger.debug("Found submit button", selector=selector)
                break
        except PlaywrightTimeout:
            continue

    if not submit_button:
        raise Exception("Could not find 'Pay now' button")

    logger.info("Clicking 'Pay now' button")
    await submit_button.click()

    # Wait for navigation or processing
    await page.wait_for_timeout(ORDER_SUBMISSION_DELAY)
    
    # Check for 3D Secure
    if await _check_for_3d_secure(page):
        logger.warning("3D Secure verification required - human intervention needed")
        raise ThreeDSecureRequired("3D Secure verification required - manual intervention needed")
    
    # Check for errors
    error = await _check_for_payment_error(page)
    if error:
        raise Exception(f"Payment failed: {error}")
    
    # Verify order was placed
    if "thank" in page.url.lower() or "confirmation" in page.url.lower() or "order" in page.url.lower():
        logger.info("Order submitted successfully", confirmation_url=page.url)
        return {
            "confirmation_url": page.url,
            "order_placed": True
        }
    else:
        logger.warning("Order submission unclear", current_url=page.url)
        return {
            "current_url": page.url,
            "order_placed": False
        }


async def _check_for_3d_secure(page: Page) -> bool:
    """Check if 3D Secure verification is required."""
    secure_selectors = [
        "iframe[name*='3d']",
        "iframe[name*='secure']",
        "text=/3d secure/i",
        "text=/verify/i",
        "#challenge-iframe",
    ]
    
    for selector in secure_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=SECURE_CHECK_TIMEOUT)
            if element:
                logger.debug("Found 3D Secure indicator", selector=selector)
                return True
        except PlaywrightTimeout:
            continue

    return False


async def _check_for_payment_error(page: Page) -> str | None:
    """Check for payment error messages."""
    error_selectors = [
        ".error-message",
        ".payment-error",
        "[role='alert']",
        "text=/payment.*failed/i",
        "text=/card.*declined/i",
        "text=/error/i",
    ]

    for selector in error_selectors:
        try:
            element = await page.wait_for_selector(selector, timeout=ERROR_CHECK_TIMEOUT)
            if element:
                error_text = await element.inner_text()
                logger.debug("Found error message", selector=selector, error=error_text)
                return error_text
        except PlaywrightTimeout:
            continue

    return None
