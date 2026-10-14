import pytest
from cgtel.signals.confidence import ConfidenceExtractor, default_mock_confidence_provider


def test_default_mock_provider():
    extractor = ConfidenceExtractor()
    confidence = extractor.extract("fake_tool", args={"x": 1})
    assert confidence == 0.9

    # Direct call to default mock function
    assert default_mock_confidence_provider("any_tool") == 0.9


def test_custom_confidence_provider():
    def custom_provider(tool_name: str, args=None, **kwargs) -> float:
        if tool_name == "high_confidence_tool":
            return 0.95
        return 0.4

    extractor = ConfidenceExtractor(provider=custom_provider)

    assert extractor.extract("high_confidence_tool") == 0.95
    assert extractor.extract("low_confidence_tool") == 0.4


def test_normalization_out_of_bounds():
    # Callback returning values outside [0.0, 1.0]
    extractor_high = ConfidenceExtractor(provider=lambda name, args=None, **kw: 1.8)
    assert extractor_high.extract("any_tool") == 1.0

    extractor_low = ConfidenceExtractor(provider=lambda name, args=None, **kw: -0.5)
    assert extractor_low.extract("any_tool") == 0.0


def test_error_handling_provider():
    def broken_provider(tool_name: str, args=None, **kwargs):
        raise ValueError("Provider unexpected error")

    extractor = ConfidenceExtractor(provider=broken_provider)
    # Should handle exception and return fallback 0.0
    assert extractor.extract("any_tool") == 0.0
