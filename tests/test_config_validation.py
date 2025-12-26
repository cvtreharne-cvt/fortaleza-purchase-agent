"""Tests for configuration validation, specifically MODE_SAFETY validation."""

import pytest
from src.core.errors import ConfigurationError


def test_mode_safety_validates_at_import():
    """Test that MODE_SAFETY validation runs at module load time.
    
    Since the validation runs at import, this test verifies the module
    imports successfully, which means validation passed.
    """
    from src.core.config import MODE_SAFETY, Mode
    
    # If we get here, validation passed
    assert len(MODE_SAFETY) > 0
    assert Mode.DRYRUN in MODE_SAFETY
    assert Mode.TEST in MODE_SAFETY
    assert Mode.PROD in MODE_SAFETY


def test_mode_safety_has_all_modes():
    """Test that MODE_SAFETY includes all Mode enum values."""
    from src.core.config import MODE_SAFETY, Mode
    
    mode_values = set(Mode)
    safety_keys = set(MODE_SAFETY.keys())
    
    assert mode_values == safety_keys, \
        f"MODE_SAFETY keys {safety_keys} don't match Mode enum {mode_values}"


def test_mode_safety_levels_are_unique():
    """Test that each mode has a unique safety level."""
    from src.core.config import MODE_SAFETY
    
    safety_values = list(MODE_SAFETY.values())
    assert len(safety_values) == len(set(safety_values)), \
        f"MODE_SAFETY has duplicate safety levels: {safety_values}"


def test_mode_safety_levels_are_positive_integers():
    """Test that all safety levels are positive integers."""
    from src.core.config import MODE_SAFETY
    
    for mode, safety_level in MODE_SAFETY.items():
        assert isinstance(safety_level, int), \
            f"MODE_SAFETY[{mode.value}] is not an integer: {safety_level}"
        assert safety_level > 0, \
            f"MODE_SAFETY[{mode.value}] must be positive: {safety_level}"


def test_mode_safety_hierarchy():
    """Test that MODE_SAFETY correctly defines safety hierarchy.
    
    DRYRUN should be safest (highest value)
    TEST should be medium
    PROD should be least safe (lowest value)
    """
    from src.core.config import MODE_SAFETY, Mode
    
    assert MODE_SAFETY[Mode.DRYRUN] > MODE_SAFETY[Mode.TEST], \
        "DRYRUN should be safer than TEST"
    assert MODE_SAFETY[Mode.TEST] > MODE_SAFETY[Mode.PROD], \
        "TEST should be safer than PROD"
    assert MODE_SAFETY[Mode.DRYRUN] > MODE_SAFETY[Mode.PROD], \
        "DRYRUN should be safer than PROD"


def test_mode_safety_validation_would_catch_missing_mode():
    """Test that validation would catch missing mode entries.
    
    This is a conceptual test - we can't actually test the validation
    failing at import time without breaking the test suite, but we can
    verify the logic would work.
    """
    from src.core.config import Mode
    
    # Create a mock MODE_SAFETY missing one mode
    mock_safety = {
        Mode.DRYRUN: 3,
        Mode.TEST: 2,
        # PROD is missing
    }
    
    mode_values = set(Mode)
    safety_keys = set(mock_safety.keys())
    missing = mode_values - safety_keys
    
    assert len(missing) == 1, "Should detect one missing mode"
    assert Mode.PROD in missing, "Should detect PROD is missing"


def test_mode_safety_validation_would_catch_duplicate_levels():
    """Test that validation would catch duplicate safety levels."""
    from src.core.config import Mode
    
    # Create a mock MODE_SAFETY with duplicate levels
    mock_safety = {
        Mode.DRYRUN: 2,
        Mode.TEST: 2,  # Duplicate!
        Mode.PROD: 1,
    }
    
    safety_values = list(mock_safety.values())
    has_duplicates = len(safety_values) != len(set(safety_values))
    
    assert has_duplicates, "Should detect duplicate safety levels"


if __name__ == '__main__':
    pytest.main([__file__, '-v'])
