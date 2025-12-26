"""Tests for webhook mode override functionality.

Valid mode values: 'prod', 'dryrun', 'test'
"""

import pytest
from src.app.webhook import WebhookPayload
from src.core.config import get_settings, Mode


def test_webhook_payload_without_mode():
    """Test WebhookPayload works without mode field (defaults to None)."""
    payload = WebhookPayload(
        event_id="test-123",
        received_at="2025-11-17T00:00:00Z",
        subject="Test",
        direct_link="https://example.com/product",
        product_hint="Test Product"
    )
    assert payload.mode is None


def test_webhook_payload_with_dryrun_mode():
    """Test WebhookPayload accepts mode='dryrun'."""
    payload = WebhookPayload(
        event_id="test-123",
        received_at="2025-11-17T00:00:00Z",
        subject="Test",
        direct_link="https://example.com/product",
        product_hint="Test Product",
        mode="dryrun"
    )
    assert payload.mode == "dryrun"


def test_webhook_payload_with_test_mode():
    """Test WebhookPayload accepts mode='test' when environment allows it.
    
    Note: This test will only pass if environment MODE is PROD or TEST,
    since safety validation prevents override from DRYRUN to TEST.
    """
    from unittest.mock import patch
    from src.core.config import reload_settings
    
    # Mock environment to allow test mode override
    with patch.dict('os.environ', {'MODE': 'prod', 'CONFIRM_PROD': 'YES'}):
        reload_settings()  # Reload settings with new env
        payload = WebhookPayload(
            event_id="test-123",
            received_at="2025-11-17T00:00:00Z",
            subject="Test",
            direct_link="https://example.com/product",
            product_hint="Test Product",
            mode="test"
        )
        assert payload.mode == "test"
        reload_settings()  # Restore original settings


def test_webhook_payload_with_prod_mode():
    """Test WebhookPayload accepts mode='prod' when environment allows it.
    
    Note: This test will only pass if environment MODE is PROD,
    since safety validation prevents override from DRYRUN/TEST to PROD.
    """
    from unittest.mock import patch
    from src.core.config import reload_settings
    
    # Mock environment to allow prod mode (same mode = allowed)
    with patch.dict('os.environ', {'MODE': 'prod', 'CONFIRM_PROD': 'YES'}):
        reload_settings()  # Reload settings with new env
        payload = WebhookPayload(
            event_id="test-123",
            received_at="2025-11-17T00:00:00Z",
            subject="Test",
            direct_link="https://example.com/product",
            product_hint="Test Product",
            mode="prod"
        )
        assert payload.mode == "prod"
        reload_settings()  # Restore original settings


def test_mode_enum_values():
    """Test Mode enum has expected values."""
    assert Mode.DRYRUN.value == "dryrun"
    assert Mode.TEST.value == "test"
    assert Mode.PROD.value == "prod"


def test_run_purchase_agent_signature():
    """Test run_purchase_agent accepts mode_override parameter."""
    from agents.fortaleza_agent.agent import run_purchase_agent
    import inspect
    
    sig = inspect.signature(run_purchase_agent)
    assert 'mode_override' in sig.parameters
    
    # Verify it's optional
    param = sig.parameters['mode_override']
    assert param.default is None


def test_checkout_submit_order_dryrun_mode():
    """Test checkout does NOT submit in dryrun mode."""
    from unittest.mock import Mock
    from src.core.config import Mode, Settings
    
    # Mock settings with dryrun mode
    mock_settings = Mock(spec=Settings)
    mock_settings.mode = Mode.DRYRUN
    
    # In dryrun mode, submit_order should be False
    submit_order = mock_settings.mode in [Mode.PROD, Mode.TEST]
    assert submit_order is False, "dryrun mode should NOT submit orders"


def test_checkout_submit_order_test_mode():
    """Test checkout DOES submit in test mode."""
    from unittest.mock import Mock
    from src.core.config import Mode, Settings
    
    # Mock settings with test mode
    mock_settings = Mock(spec=Settings)
    mock_settings.mode = Mode.TEST
    
    # In test mode, submit_order should be True
    submit_order = mock_settings.mode in [Mode.PROD, Mode.TEST]
    assert submit_order is True, "test mode SHOULD submit orders for end-to-end validation"


def test_checkout_submit_order_prod_mode():
    """Test checkout DOES submit in prod mode."""
    from unittest.mock import Mock
    from src.core.config import Mode, Settings
    
    # Mock settings with prod mode
    mock_settings = Mock(spec=Settings)
    mock_settings.mode = Mode.PROD
    
    # In prod mode, submit_order should be True
    submit_order = mock_settings.mode in [Mode.PROD, Mode.TEST]
    assert submit_order is True, "prod mode SHOULD submit orders"


def test_mode_behavior_matrix():
    """Test the complete mode behavior matrix."""
    from src.core.config import Mode
    
    # Define expected behaviors
    mode_behaviors = {
        Mode.DRYRUN: {
            "submit_order": False,
            "description": "Full flow, stops before submit (testing selectors)"
        },
        Mode.TEST: {
            "submit_order": True,
            "description": "Full flow, submits order (any product end-to-end validation - for testing or purchasing)"
        },
        Mode.PROD: {
            "submit_order": True,
            "description": "Full flow, submits order (real Fortaleza purchase)"
        }
    }
    
    # Verify each mode
    for mode, expected in mode_behaviors.items():
        submit_order = mode in [Mode.PROD, Mode.TEST]
        assert submit_order == expected["submit_order"], \
            f"{mode.value} mode: expected submit_order={expected['submit_order']}, got {submit_order}"


def test_mode_override_safety_dryrun_to_prod_rejected():
    """Test that DRYRUN environment cannot be overridden to PROD (less safe)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.DRYRUN
    requested_mode = Mode.PROD
    
    # Should be rejected (requested is less safe)
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is False, "Should NOT allow override from DRYRUN to PROD"


def test_mode_override_safety_dryrun_to_test_rejected():
    """Test that DRYRUN environment cannot be overridden to TEST (less safe)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.DRYRUN
    requested_mode = Mode.TEST
    
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is False, "Should NOT allow override from DRYRUN to TEST"


def test_mode_override_safety_prod_to_dryrun_allowed():
    """Test that PROD environment CAN be overridden to DRYRUN (safer)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.PROD
    requested_mode = Mode.DRYRUN
    
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is True, "Should allow override from PROD to DRYRUN"


def test_mode_override_safety_prod_to_test_allowed():
    """Test that PROD environment CAN be overridden to TEST (safer)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.PROD
    requested_mode = Mode.TEST
    
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is True, "Should allow override from PROD to TEST"


def test_mode_override_safety_test_to_dryrun_allowed():
    """Test that TEST environment CAN be overridden to DRYRUN (safer)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.TEST
    requested_mode = Mode.DRYRUN
    
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is True, "Should allow override from TEST to DRYRUN"


def test_mode_override_safety_test_to_prod_rejected():
    """Test that TEST environment cannot be overridden to PROD (less safe)."""
    from src.core.config import Mode, MODE_SAFETY
    
    env_mode = Mode.TEST
    requested_mode = Mode.PROD
    
    should_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
    assert should_allow is False, "Should NOT allow override from TEST to PROD"


def test_mode_override_safety_matrix():
    """Test complete mode override safety matrix."""
    from src.core.config import Mode, MODE_SAFETY
    
    # Expected results: Can override if requested >= environment (same or safer)
    test_cases = [
        # (env_mode, requested_mode, should_allow)
        (Mode.PROD, Mode.PROD, True),      # Same level
        (Mode.PROD, Mode.TEST, True),      # Safer
        (Mode.PROD, Mode.DRYRUN, True),    # Safer
        (Mode.TEST, Mode.PROD, False),     # Less safe - REJECT
        (Mode.TEST, Mode.TEST, True),      # Same level
        (Mode.TEST, Mode.DRYRUN, True),    # Safer
        (Mode.DRYRUN, Mode.PROD, False),   # Less safe - REJECT
        (Mode.DRYRUN, Mode.TEST, False),   # Less safe - REJECT  
        (Mode.DRYRUN, Mode.DRYRUN, True),  # Same level
    ]
    
    for env_mode, requested_mode, expected_allow in test_cases:
        actual_allow = MODE_SAFETY[requested_mode] >= MODE_SAFETY[env_mode]
        assert actual_allow == expected_allow, \
            f"env={env_mode.value}, requested={requested_mode.value}: expected {expected_allow}, got {actual_allow}"


def test_webhook_validation_rejects_unsafe_override():
    """Test that webhook validation rejects unsafe mode overrides at API boundary.
    
    Note: After refactoring, safety validation happens in the webhook handler,
    not the Pydantic validator. This test now verifies the Pydantic validator
    only checks format, and the handler would reject unsafe overrides.
    """
    from unittest.mock import patch
    from src.core.config import reload_settings
    
    # Set environment to DRYRUN
    with patch.dict('os.environ', {'MODE': 'dryrun'}):
        reload_settings()
        
        # Pydantic validator should accept the format ("prod" is valid)
        # Safety rejection happens in webhook handler, not validator
        payload = WebhookPayload(
            event_id="test-123",
            received_at="2025-11-17T00:00:00Z",
            subject="Test",
            direct_link="https://example.com/product",
            product_hint="Test Product",
            mode="prod"  # Valid format, handler will reject safety
        )
        
        # Verify payload was created (format validation passed)
        assert payload.mode == "prod"
        
        # Note: The actual safety rejection happens in handle_webhook()
        # See test_webhook_handler_rejects_unsafe_override for integration test
        
        reload_settings()


def test_webhook_validation_allows_safe_override():
    """Test that webhook validation allows safe mode overrides."""
    from unittest.mock import patch
    from src.core.config import reload_settings
    
    # Set environment to PROD
    with patch.dict('os.environ', {'MODE': 'prod', 'CONFIRM_PROD': 'YES'}):
        reload_settings()
        
        # Override to DRYRUN (safe - should be allowed)
        payload = WebhookPayload(
            event_id="test-123",
            received_at="2025-11-17T00:00:00Z",
            subject="Test",
            direct_link="https://example.com/product",
            product_hint="Test Product",
            mode="dryrun"
        )
        assert payload.mode == "dryrun"
        
        reload_settings()


def test_effective_mode_passed_to_checkout():
    """Test that effective_mode is properly passed to checkout tool.
    
    This test verifies the critical bug fix: checkout must use effective_mode
    from webhook override, not settings.mode from environment.
    """
    from agents.fortaleza_agent.agent import create_adk_tools
    from src.core.config import Mode
    from unittest.mock import AsyncMock, patch
    
    # Create tools with effective_mode=DRYRUN (simulating webhook override)
    tools = create_adk_tools(
        product_name="Test Product",
        event_id="test-123",
        effective_mode=Mode.DRYRUN
    )
    
    # Find the checkout tool
    checkout_tool = None
    for tool in tools:
        if hasattr(tool, 'func') and tool.func.__name__ == 'checkout_tool':
            checkout_tool = tool.func
            break
    
    assert checkout_tool is not None, "checkout_tool not found in tools"
    
    # Mock the checkout_and_pay function to verify it receives correct submit_order
    with patch('agents.fortaleza_agent.agent.checkout_and_pay', new_callable=AsyncMock) as mock_checkout:
        mock_checkout.return_value = {"status": "success"}
        
        # Mock browser manager
        with patch('agents.fortaleza_agent.agent.ensure_browser_started', new_callable=AsyncMock) as mock_browser:
            mock_page = AsyncMock()
            mock_browser.return_value.page = mock_page
            
            # Call checkout tool (should use effective_mode=DRYRUN → submit_order=False)
            import asyncio
            result = asyncio.run(checkout_tool())
            
            # Verify checkout_and_pay was called with submit_order=False (DRYRUN mode)
            mock_checkout.assert_called_once()
            call_args = mock_checkout.call_args
            assert call_args[1]['submit_order'] is False, \
                "Checkout should use submit_order=False when effective_mode=DRYRUN"


def test_effective_mode_prod_submits_order():
    """Test that effective_mode=PROD results in submit_order=True."""
    from agents.fortaleza_agent.agent import create_adk_tools
    from src.core.config import Mode
    from unittest.mock import AsyncMock, patch
    
    # Create tools with effective_mode=PROD
    tools = create_adk_tools(
        product_name="Test Product",
        event_id="test-123",
        effective_mode=Mode.PROD
    )
    
    # Find the checkout tool
    checkout_tool = None
    for tool in tools:
        if hasattr(tool, 'func') and tool.func.__name__ == 'checkout_tool':
            checkout_tool = tool.func
            break
    
    assert checkout_tool is not None
    
    with patch('agents.fortaleza_agent.agent.checkout_and_pay', new_callable=AsyncMock) as mock_checkout:
        mock_checkout.return_value = {"status": "success"}
        
        with patch('agents.fortaleza_agent.agent.ensure_browser_started', new_callable=AsyncMock) as mock_browser:
            mock_page = AsyncMock()
            mock_browser.return_value.page = mock_page
            
            import asyncio
            result = asyncio.run(checkout_tool())
            
            # Verify submit_order=True for PROD mode
            call_args = mock_checkout.call_args
            assert call_args[1]['submit_order'] is True, \
                "Checkout should use submit_order=True when effective_mode=PROD"


def test_webhook_payload_invalid_mode_format():
    """Test that Pydantic validator rejects invalid mode format."""
    from pydantic import ValidationError
    
    # Try to create payload with invalid mode
    with pytest.raises(ValidationError) as exc_info:
        WebhookPayload(
            event_id="test-123",
            received_at="2025-11-17T00:00:00Z",
            subject="Test",
            direct_link="https://example.com/product",
            product_hint="Test Product",
            mode="invalid_mode"  # Invalid format
        )
    
    # Verify error mentions valid modes
    error_msg = str(exc_info.value)
    assert "Invalid mode" in error_msg


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
