#!/usr/bin/env python
"""
Manual test script for the ADK agent.

This script simulates a webhook event and runs the agent.
Use this to test the agent workflow before deploying.
"""

import asyncio
import sys
from pathlib import Path

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from agents.fortaleza_agent.agent import run_purchase_agent
from src.core.logging import setup_logging, get_logger
from src.core.config import get_settings

setup_logging()
logger = get_logger(__name__)


async def main():
    """Run agent test."""
    print("\n" + "=" * 60)
    print("🤖 Manual Agent Test")
    print("=" * 60)

    settings = get_settings()

    print(f"\nConfiguration:")
    print(f"  Mode: {settings.mode.value}")
    print(f"  Headless: {settings.headless}")
    print(f"  Product: {settings.product_name}")
    print(f"  Agent Model: {settings.agent_model}")

    # Check required config
    if not settings.google_api_key:
        print("\n❌ ERROR: GOOGLE_API_KEY not set in .env.local")
        print("Please add your Google API key to .env.local:")
        print("  GOOGLE_API_KEY=your-api-key-here")
        return

    if not settings.bnb_email or not settings.bnb_password:
        print("\n❌ ERROR: B&B credentials not set in .env.local")
        print("Please add your Bitters & Bottles credentials:")
        print("  BNB_EMAIL=your-email")
        print("  BNB_PASSWORD=your-password")
        return

    print("\n✅ Configuration looks good!")
    print("\n" + "=" * 60)
    print("Starting Agent Run...")
    print("=" * 60 + "\n")

    # Test parameters - Using in-stock product for testing
    direct_link = "https://www.bittersandbottles.com/products/hamilton-the-grass-skirt-blend-rum"
    product_name = "Hamilton The Grass Skirt Blend Rum"
    event_id = "manual-test-001"

    print(f"Test Product: {product_name}")
    print(f"Direct Link: {direct_link}")
    print(f"Event ID: {event_id}\n")

    try:
        result = await run_purchase_agent(
            direct_link=direct_link,
            product_name=product_name,
            event_id=event_id
        )

        print("\n" + "=" * 60)
        print("🎉 Agent Run Completed")
        print("=" * 60)
        print(f"\nResult: {result['status']}")
        print(f"Event ID: {result['event_id']}")
        print(f"Mode: {result['mode']}")

        if result['status'] == 'success':
            print(f"\n✅ SUCCESS!")
            if 'agent_response' in result:
                print(f"\nAgent Response:")
                print(result['agent_response'])
        else:
            print(f"\n❌ FAILED")
            print(f"Error: {result.get('error', 'Unknown error')}")

    except KeyboardInterrupt:
        print("\n\n⚠️  Test interrupted by user")
    except Exception as e:
        print(f"\n\n❌ Test failed with exception: {e}")
        import traceback
        traceback.print_exc()

    print("\n" + "=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
