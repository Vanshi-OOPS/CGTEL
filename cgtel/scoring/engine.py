from typing import Any, Dict, Optional, Tuple

from cgtel.config import DEFAULT_WEIGHTS
from cgtel.signals.confidence import ConfidenceExtractor
from cgtel.signals.failure_rate import HistoricalFailureRateLookup
from cgtel.signals.reversibility import ReversibilityEstimator
from cgtel.types import RiskDecision, RiskTier


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

    def evaluate(
        self, tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
    ) -> Tuple[float, Dict[str, float]]:
        """
        Extracts individual signals and computes the composite risk score R in [0.0, 1.0].
        Returns a tuple of (score, contributing_signals).
        """
        rev = self.reversibility_estimator.estimate(tool_name, args)
        conf = self.confidence_extractor.extract(tool_name, args, **kwargs)
        fail = self.failure_rate_lookup.get_failure_rate(tool_name)

        conf_gap = 1.0 - conf

        raw_score = (self.w1 * rev) + (self.w2 * conf_gap) + (self.w3 * fail)
        score = max(0.0, min(1.0, float(raw_score)))

        signals = {
            "reversibility": round(float(rev), 4),
            "confidence": round(float(conf), 4),
            "confidence_gap": round(float(conf_gap), 4),
            "failure_rate": round(float(fail), 4),
        }

        return score, signals

    def compute_decision(
        self, tool_name: str, args: Optional[Dict[str, Any]] = None, **kwargs
    ) -> RiskDecision:
        """
        Evaluates risk score and returns a RiskDecision object containing the score and contributing signals.
        """
        score, signals = self.evaluate(tool_name, args, **kwargs)
        return RiskDecision(
            score=score,
            tier=RiskTier.AUTO_ALLOW,
            contributing_signals=signals,
        )
