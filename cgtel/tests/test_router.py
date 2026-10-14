import pytest
from cgtel.router.decision_router import DecisionRouter
from cgtel.types import RiskDecision, RiskTier


def test_invalid_thresholds():
    with pytest.raises(ValueError):
        DecisionRouter(tau1=0.5, tau2=0.3)


def test_classification_logic():
    router = DecisionRouter(tau1=0.2, tau2=0.6)

    assert router.classify(0.1) == RiskTier.AUTO_ALLOW
    assert router.classify(0.2) == RiskTier.LOG_AND_MONITOR
    assert router.classify(0.4) == RiskTier.LOG_AND_MONITOR
    assert router.classify(0.6) == RiskTier.HUMAN_REVIEW
    assert router.classify(0.8) == RiskTier.HUMAN_REVIEW


def test_route_auto_allow():
    router = DecisionRouter(tau1=0.2, tau2=0.6)
    decision = RiskDecision(score=0.1, tier=RiskTier.AUTO_ALLOW)

    routed = router.route(decision, tool_name="read_file")
    assert routed.tier == RiskTier.AUTO_ALLOW


def test_route_log_and_monitor():
    router = DecisionRouter(tau1=0.2, tau2=0.6)
    decision = RiskDecision(score=0.4, tier=RiskTier.AUTO_ALLOW)

    routed = router.route(decision, tool_name="update_file")
    assert routed.tier == RiskTier.LOG_AND_MONITOR


def test_route_human_review_approved():
    router = DecisionRouter(tau1=0.2, tau2=0.6)
    decision = RiskDecision(score=0.7, tier=RiskTier.AUTO_ALLOW)

    # Test auto_approve=True
    routed = router.route(decision, tool_name="delete_database", auto_approve=True)
    assert routed.tier == RiskTier.HUMAN_REVIEW


def test_route_human_review_denied():
    router = DecisionRouter(tau1=0.2, tau2=0.6)
    decision = RiskDecision(score=0.7, tier=RiskTier.AUTO_ALLOW)

    # Test auto_approve=False raising PermissionError
    with pytest.raises(PermissionError) as exc_info:
        router.route(decision, tool_name="delete_database", auto_approve=False)

    assert "DENIED by Human Review" in str(exc_info.value)
