import pytest
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.confidence import ConfidenceExtractor
from cgtel.signals.failure_rate import HistoricalFailureRateLookup
from cgtel.signals.reversibility import ReversibilityEstimator
from cgtel.types import RiskDecision, RiskTier


def test_default_weights_scoring():
    # Default weights: 0.25, 0.25, 0.50
    engine = RiskScoringEngine()

    # read_file: reversibility=0.0, confidence=0.9 (gap=0.1), failure_rate=0.1 (cold-start)
    # Effective F is max(read_file prior 0.05, cold-start failure rate 0.1).
    # R = (0.25 * 0.0) + (0.25 * 0.1) + (0.50 * 0.1) = 0.075
    score, signals = engine.evaluate("read_file")
    assert pytest.approx(score, 0.001) == 0.075
    assert signals["reversibility"] == 0.0
    assert signals["confidence"] == 0.9
    assert signals["confidence_gap"] == 0.1
    assert signals["failure_rate"] == 0.1


def test_custom_weights_scoring():
    # w1=0.6, w2=0.2, w3=0.2
    engine = RiskScoringEngine(w1=0.6, w2=0.2, w3=0.2)

    # Delete's F prior is 0.8; the configured weights keep the original equation.
    # R = (0.6 * 0.7) + (0.2 * 0.1) + (0.2 * 0.8) = 0.60
    score, signals = engine.evaluate("delete_file")
    assert pytest.approx(score, 0.001) == 0.60


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


def test_tool_policy_floor_raises_score_based_decision():
    engine = RiskScoringEngine(severity_priors={"write_file": 0.0})
    decision = engine.compute_decision("write_file", {}, confidence=1.0)

    assert decision.score == pytest.approx(0.125)
    assert decision.contributing_signals["score_based_decision"] == "AUTO_ALLOW"
    assert decision.contributing_signals["floor"] == "LOG_AND_MONITOR"
    assert decision.contributing_signals["floor_applied"] is True
    assert decision.tier == RiskTier.LOG_AND_MONITOR


def test_payment_and_delete_priors_reach_human_review_with_full_confidence():
    engine = RiskScoringEngine()
    payment = engine.compute_decision("make_payment", {}, confidence=1.0)
    deletion = engine.compute_decision("delete_file", {}, confidence=1.0)

    assert payment.score >= 0.35
    assert payment.tier == RiskTier.HUMAN_REVIEW
    assert deletion.score >= 0.35
    assert deletion.tier == RiskTier.HUMAN_REVIEW
