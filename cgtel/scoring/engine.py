from typing import Any, Dict, Optional, Tuple

from cgtel.config import DEFAULT_TOOL_POLICIES, DEFAULT_WEIGHTS, TAU_1, TAU_2
from cgtel.signals.confidence import ConfidenceExtractor
from cgtel.signals.failure_rate import HistoricalFailureRateLookup
from cgtel.signals.reversibility import ReversibilityEstimator
from cgtel.types import RiskDecision, RiskTier


_DECISION_RANK = {
    RiskTier.AUTO_ALLOW.value: 0,
    RiskTier.LOG_AND_MONITOR.value: 1,
    RiskTier.HUMAN_REVIEW.value: 2,
}


def stricter_decision(score_decision: str, minimum_decision: Optional[str]) -> tuple[str, bool]:
    """Apply a per-tool minimum tier without changing the score classification."""
    if minimum_decision not in _DECISION_RANK:
        return score_decision, False
    applied = _DECISION_RANK[minimum_decision] > _DECISION_RANK[score_decision]
    return (minimum_decision if applied else score_decision), applied


class RiskScoringEngine:
    """
    Computes composite risk score:
    R = w1 * reversibility + w2 * (1 - confidence) + w3 * failure_rate
    """

    def __init__(
        self,
        w1: Optional[float] = None,
        w2: Optional[float] = None,
        w3: Optional[float] = None,
        reversibility_estimator: Optional[ReversibilityEstimator] = None,
        confidence_extractor: Optional[ConfidenceExtractor] = None,
        failure_rate_lookup: Optional[HistoricalFailureRateLookup] = None,
        severity_priors: Optional[Dict[str, float]] = None,
        minimum_decisions: Optional[Dict[str, Optional[str]]] = None,
        tau1: Optional[float] = None,
        tau2: Optional[float] = None,
    ):
        """
        Initialize scoring engine with configurable signal weights and signal extractors.
        """
        weights = DEFAULT_WEIGHTS
        self.w1 = float(w1) if w1 is not None else float(weights["w1"])
        self.w2 = float(w2) if w2 is not None else float(weights["w2"])
        self.w3 = float(w3) if w3 is not None else float(weights["w3"])

        self.reversibility_estimator = reversibility_estimator or ReversibilityEstimator()
        self.confidence_extractor = confidence_extractor or ConfidenceExtractor()
        self.failure_rate_lookup = failure_rate_lookup or HistoricalFailureRateLookup()
        self.severity_priors = {
            name: float(policy["severity_prior"])
            for name, policy in DEFAULT_TOOL_POLICIES.items()
        }
        self.minimum_decisions = {
            name: policy.get("minimum_decision")
            for name, policy in DEFAULT_TOOL_POLICIES.items()
        }
        if severity_priors:
            self.severity_priors.update({name: float(value) for name, value in severity_priors.items()})
        if minimum_decisions:
            self.minimum_decisions.update(minimum_decisions)
        self.tau1 = float(TAU_1 if tau1 is None else tau1)
        self.tau2 = float(TAU_2 if tau2 is None else tau2)

    def evaluate(
        self, tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Tuple[float, Dict[str, float]]:
        """
        Extracts individual signals and computes the composite risk score R in [0.0, 1.0].
        Returns a tuple of (score, contributing_signals).
        """
        rev = self.reversibility_estimator.estimate(tool_name, args)
        explicit_confidence = kwargs.pop("confidence", None)
        confidence_source = kwargs.pop("confidence_source", None)
        if explicit_confidence is None:
            conf = self.confidence_extractor.extract(tool_name, args, **kwargs)
            confidence_source = confidence_source or "default_mock"
        else:
            try:
                conf = max(0.0, min(1.0, float(explicit_confidence)))
            except (TypeError, ValueError):
                conf = 0.0
            confidence_source = confidence_source or "explicit"
        observed_failure_rate = self.failure_rate_lookup.get_failure_rate(tool_name)
        severity_prior = self.severity_priors.get(tool_name, 0.0)
        fail = max(float(observed_failure_rate), float(severity_prior))

        conf_gap = 1.0 - conf

        raw_score = (self.w1 * rev) + (self.w2 * conf_gap) + (self.w3 * fail)
        score = max(0.0, min(1.0, float(raw_score)))

        signals = {
            "reversibility": round(float(rev), 4),
            "confidence": round(float(conf), 4),
            "confidence_gap": round(float(conf_gap), 4),
            "failure_rate": round(float(fail), 4),
            "historical_failure_rate": round(float(observed_failure_rate), 4),
            "severity_prior": round(float(severity_prior), 4),
            "confidence_source": confidence_source,
        }

        return score, signals

    def compute_decision(
        self, tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
    ) -> RiskDecision:
        """
        Evaluates risk score and returns a RiskDecision object containing the score and contributing signals.
        """
        score, signals = self.evaluate(tool_name, args, **kwargs)
        score_tier = (
            RiskTier.AUTO_ALLOW.value if score < self.tau1
            else RiskTier.LOG_AND_MONITOR.value if score < self.tau2
            else RiskTier.HUMAN_REVIEW.value
        )
        floor = self.minimum_decisions.get(tool_name)
        final_tier, floor_applied = stricter_decision(score_tier, floor)
        signals["score_based_decision"] = score_tier
        signals["floor"] = floor
        signals["floor_applied"] = floor_applied
        signals["weights"] = {"w1": self.w1, "w2": self.w2, "w3": self.w3}
        signals["R"] = score
        signals["final_decision"] = final_tier
        return RiskDecision(
            score=score,
            tier=RiskTier(final_tier),
            contributing_signals=signals,
        )
