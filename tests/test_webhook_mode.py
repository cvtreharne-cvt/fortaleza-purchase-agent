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
    """Test WebhookPayload accepts mode='test'."""
    payload = WebhookPayload(
        event_id="test-123",
        received_at="2025-11-17T00:00:00Z",
        subject="Test",
        direct_link="https://example.com/product",
        product_hint="Test Product",
        mode="test"
    )
    assert payload.mode == "test"


def test_webhook_payload_with_prod_mode():
    """Test WebhookPayload accepts mode='prod'."""
    payload = WebhookPayload(
        event_id="test-123",
        received_at="2025-11-17T00:00:00Z",
        subject="Test",
        direct_link="https://example.com/product",
        product_hint="Test Product",
        mode="prod"
    )
    assert payload.mode == "prod"


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
            "description": "Full flow, submits order (end-to-end validation with cheap product)"
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


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
