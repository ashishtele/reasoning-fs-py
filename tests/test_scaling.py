"""Tests for ConfidenceScaler."""

import pytest

from reasoning_fs.scaling import ConfidenceScaler, ScalingParams


class TestConfidenceScaler:
    """Tests for ConfidenceScaler class."""

    def test_init(self):
        """Test initialization."""
        scaler = ConfidenceScaler()
        assert scaler.base_max_tokens == 2000
        assert scaler.base_temperature == 0.7
        assert scaler.confidence_threshold == 0.5

    def test_init_custom(self):
        """Test initialization with custom values."""
        scaler = ConfidenceScaler(
            base_max_tokens=1000,
            base_temperature=0.5,
            confidence_threshold=0.3
        )
        assert scaler.base_max_tokens == 1000
        assert scaler.base_temperature == 0.5
        assert scaler.confidence_threshold == 0.3

    def test_calculate_confidence_empty(self):
        """Test confidence calculation with no traces."""
        scaler = ConfidenceScaler()
        confidence = scaler.calculate_confidence([])
        assert confidence == 0.0

    def test_calculate_confidence_all_success(self):
        """Test confidence with all successful traces."""
        scaler = ConfidenceScaler()
        
        # Mock traces
        class MockTrace:
            def __init__(self, success):
                self.success = success
        
        traces = [MockTrace(True) for _ in range(5)]
        confidence = scaler.calculate_confidence(traces)
        
        # High confidence with all successes
        assert confidence >= 0.7

    def test_calculate_confidence_all_failure(self):
        """Test confidence with all failed traces."""
        scaler = ConfidenceScaler()
        
        class MockTrace:
            def __init__(self, success):
                self.success = success
        
        traces = [MockTrace(False) for _ in range(5)]
        confidence = scaler.calculate_confidence(traces)
        
        # Low confidence with all failures
        assert confidence < 0.5

    def test_calculate_confidence_mixed(self):
        """Test confidence with mixed results."""
        scaler = ConfidenceScaler()
        
        class MockTrace:
            def __init__(self, success):
                self.success = success
        
        traces = [
            MockTrace(True),
            MockTrace(True),
            MockTrace(False),
            MockTrace(True),
            MockTrace(False),
        ]
        confidence = scaler.calculate_confidence(traces)
        
        # Medium confidence (3/5 success = 0.6 * 0.7 + 1.0 * 0.3 = 0.72)
        assert 0.5 <= confidence <= 0.8

    def test_scale_high_confidence(self):
        """Test scaling with high confidence."""
        scaler = ConfidenceScaler()
        params = scaler.scale(0.9)
        
        # High confidence = MORE tokens (for verification), lower temperature
        # With confidence 0.9: max_tokens = 500 + 0.9 * (8000 - 500) = 7250
        assert params.max_tokens > scaler.base_max_tokens
        assert params.temperature <= scaler.base_temperature

    def test_scale_low_confidence(self):
        """Test scaling with low confidence."""
        scaler = ConfidenceScaler()
        params = scaler.scale(0.1)
        
        # Low confidence = FEWER tokens (exploration is expensive), higher temperature
        # With confidence 0.1: max_tokens = 500 + 0.1 * (8000 - 500) = 1250
        assert params.max_tokens < scaler.base_max_tokens
        assert params.temperature >= scaler.base_temperature

    def test_scale_bounds(self):
        """Test that scaling respects bounds."""
        scaler = ConfidenceScaler()
        
        # Test high confidence
        params_high = scaler.scale(1.0)
        assert params_high.max_tokens >= scaler.min_max_tokens
        assert params_high.temperature >= scaler.min_temperature
        
        # Test low confidence
        params_low = scaler.scale(0.0)
        assert params_low.max_tokens <= scaler.max_max_tokens
        assert params_low.temperature <= scaler.max_temperature

    def test_get_recommendation_high(self):
        """Test recommendation for high confidence."""
        scaler = ConfidenceScaler()
        rec = scaler.get_recommendation(0.9)
        assert "High confidence" in rec
        assert "conservative" in rec.lower()

    def test_get_recommendation_medium(self):
        """Test recommendation for medium confidence."""
        scaler = ConfidenceScaler()
        rec = scaler.get_recommendation(0.6)
        assert "Medium confidence" in rec
        assert "balanced" in rec.lower()

    def test_get_recommendation_low(self):
        """Test recommendation for low confidence."""
        scaler = ConfidenceScaler()
        rec = scaler.get_recommendation(0.3)
        assert "Low confidence" in rec
        assert "exploration" in rec.lower()

    def test_get_recommendation_very_low(self):
        """Test recommendation for very low confidence."""
        scaler = ConfidenceScaler()
        rec = scaler.get_recommendation(0.1)
        assert "Very low confidence" in rec
        assert "extensive" in rec.lower()
