import pytest
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.confidence import ConfidenceExtractor
from cgtel.signals.failure_rate import HistoricalFailureRateLookup
from cgtel.signals.reversibility import ReversibilityEstimator
from cgtel.types import RiskDecision


def test_default_weights_scoring():
    # Default weights: 1/3, 1/3, 1/3
    engine = RiskScoringEngine()

    # read_file: reversibility=0.0, confidence=0.9 (gap=0.1), failure_rate=0.1 (cold-start)
    # Expected R = (1/3 * 0.0) + (1/3 * 0.1) + (1/3 * 0.1) = 0.0667
    score, signals = engine.evaluate("read_file")
    assert pytest.approx(score, 0.001) == 0.0667
    assert signals["reversibility"] == 0.0
    assert signals["confidence"] == 0.9
    assert signals["confidence_gap"] == 0.1
    assert signals["failure_rate"] == 0.1


def test_custom_weights_scoring():
    # w1=0.6, w2=0.2, w3=0.2
    engine = RiskScoringEngine(w1=0.6, w2=0.2, w3=0.2)

    # delete_file: reversibility=0.7, confidence=0.9 (gap=0.1), failure_rate=0.1
    # R = (0.6 * 0.7) + (0.2 * 0.1) + (0.2 * 0.1) = 0.42 + 0.02 + 0.02 = 0.46
    score, signals = engine.evaluate("delete_file")
    assert pytest.approx(score, 0.001) == 0.46


def test_compute_decision_object():
    engine = RiskScoringEngine(w1=0.5, w2=0.25, w3=0.25)
    decision = engine.compute_decision("payment_tool")

    assert isinstance(decision, RiskDecision)
    # payment_tool: reversibility=1.0, conf=0.9 (gap=0.1), fail=0.1
    # R = (0.5 * 1.0) + (0.25 * 0.1) + (0.25 * 0.1) = 0.5 + 0.025 + 0.025 = 0.55
    assert pytest.approx(decision.score, 0.001) == 0.55
    assert "reversibility" in decision.contributing_signals
    assert "confidence" in decision.contributing_signals
    assert "failure_rate" in decision.contributing_signals
