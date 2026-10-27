from typing import Any, Callable, Dict, Optional

from cgtel.config import TAU_1, TAU_2
from cgtel.logger import logger
from cgtel.scoring.engine import stricter_decision
from cgtel.types import RiskDecision, RiskTier


class DecisionRouter:
    """
    Decision Router for enforcing policy actions based on risk score thresholds.
    - score < tau1 -> AUTO_ALLOW
    - tau1 <= score < tau2 -> LOG_AND_MONITOR
    - score >= tau2 -> HUMAN_REVIEW
    """

    def __init__(
        self,
        tau1: float = TAU_1,
        tau2: float = TAU_2,
        input_func: Callable[[str], str] = input,
    ):
        if tau1 >= tau2:
            raise ValueError(f"tau1 ({tau1}) must be strictly less than tau2 ({tau2})")
        self.tau1 = float(tau1)
        self.tau2 = float(tau2)
        self.input_func = input_func

    def classify(self, score: float) -> RiskTier:
        """Classifies a numerical score into a RiskTier."""
        if score < self.tau1:
            return RiskTier.AUTO_ALLOW
        elif score < self.tau2:
            return RiskTier.LOG_AND_MONITOR
        else:
            return RiskTier.HUMAN_REVIEW

    def route(
        self,
        decision: RiskDecision,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        auto_approve: Optional[bool] = None,
    ) -> RiskDecision:
        """
        Routes the risk decision, sets decision.tier, logs action, and prompts for human review if required.
        Raises PermissionError if human review is denied.
        """
        score_tier = self.classify(decision.score)
        floor = decision.contributing_signals.get("floor") if decision.contributing_signals else None
        final_tier_name, floor_applied = stricter_decision(
            score_tier.value,
            floor,
        )
        tier = RiskTier(final_tier_name)
        if decision.contributing_signals is not None:
            decision.contributing_signals["score_based_decision"] = score_tier.value
            decision.contributing_signals["floor_applied"] = floor_applied
            decision.contributing_signals["final_decision"] = tier.value
        decision.tier = tier

        if tier == RiskTier.AUTO_ALLOW:
            logger.info(
                f"[ROUTER AUTO_ALLOW] Tool: '{tool_name}' | Score: {decision.score:.4f} < {self.tau1}"
            )

        elif tier == RiskTier.LOG_AND_MONITOR:
            logger.warning(
                f"[ROUTER LOG_AND_MONITOR] Tool: '{tool_name}' | Score: {decision.score:.4f} (Thresholds: [{self.tau1}, {self.tau2})) | Signals: {decision.contributing_signals}"
            )
            print(
                f"  [LOG_AND_MONITOR FLAGGED] Tool '{tool_name}' executed with risk score {decision.score:.4f}"
            )

        elif tier == RiskTier.HUMAN_REVIEW:
            logger.error(
                f"[ROUTER HUMAN_REVIEW] Tool: '{tool_name}' | Score: {decision.score:.4f} >= {self.tau2} | Signals: {decision.contributing_signals}"
            )
            print("\n" + "!" * 60)
            print(f"  [HUMAN REVIEW REQUIRED]")
            print(f"  Action Tool Name : {tool_name}")
            print(f"  Call Arguments   : {args}")
            print(f"  Risk Score       : {decision.score:.4f} (>= Threshold {self.tau2})")
            print(f"  Contributing Sig : {decision.contributing_signals}")
            print("!" * 60)

            if auto_approve is not None:
                approved = auto_approve
            else:
                prompt_str = f"Approve execution of '{tool_name}'? [y/N]: "
                try:
                    user_input = self.input_func(prompt_str).strip().lower()
                    approved = user_input in ("y", "yes")
                except (EOFError, KeyboardInterrupt):
                    approved = False

            if not approved:
                print(f"  [HUMAN REVIEW DENIED] Execution of '{tool_name}' was rejected.\n")
                raise PermissionError(
                    f"Execution of tool '{tool_name}' was DENIED by Human Review (Risk Score: {decision.score:.4f})"
                )

            print(f"  [HUMAN REVIEW APPROVED] Execution of '{tool_name}' authorized.\n")

        return decision
