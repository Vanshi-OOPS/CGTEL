"""StreamingRouter subclassing DecisionRouter for SSE event emission and async review."""
from typing import Any, Dict, Optional

from cgtel.config import TAU_1, TAU_2
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import stricter_decision
from cgtel.types import RiskDecision, RiskTier


class StreamingRouter(DecisionRouter):
    def __init__(
        self,
        tau1: float = TAU_1,
        tau2: float = TAU_2,
        timeout_seconds: float = 120.0,
    ):
        super().__init__(tau1=tau1, tau2=tau2, input_func=self._handle_human_review)
        self.timeout_seconds = timeout_seconds
        self.current_run = None

    def set_current_run(self, run_session: Any) -> None:
        self.current_run = run_session

    def route(
        self,
        decision: RiskDecision,
        tool_name: str,
        args: Optional[Dict[str, Any]] = None,
        auto_approve: Optional[bool] = None,
    ) -> RiskDecision:
        score_tier = self.classify(decision.score)
        floor = decision.contributing_signals.get("floor") if decision.contributing_signals else None
        final_tier, floor_applied = stricter_decision(score_tier.value, floor)
        tier = RiskTier(final_tier)
        decision.tier = tier
        if decision.contributing_signals is not None:
            decision.contributing_signals["score_based_decision"] = score_tier.value
            decision.contributing_signals["floor_applied"] = floor_applied
            decision.contributing_signals["final_decision"] = tier.value

        if self.current_run is not None:
            scored_data = {
                "tool_name": tool_name,
                "args": args,
                "score": decision.score,
                "tier": tier.value if hasattr(tier, "value") else str(tier),
                "contributing_signals": (
                    dict(decision.contributing_signals)
                    if decision.contributing_signals
                    else {}
                ),
            }
            self.current_run.last_scored = scored_data
            self.current_run.emit_event("scored", scored_data)

        return super().route(
            decision, tool_name=tool_name, args=args, auto_approve=auto_approve
        )

    def _handle_human_review(self, prompt: str) -> str:
        if self.current_run is None:
            return "n"

        run = self.current_run
        scored = run.last_scored or {}
        tool_name = scored.get("tool_name", "")
        args = scored.get("args")
        score = scored.get("score")
        signals = scored.get("contributing_signals", {})
        tau2 = self.tau2
        timeout = getattr(run, "timeout_seconds", None) or self.timeout_seconds

        review_req_data = {
            "tool_name": tool_name,
            "args": args,
            "score": score,
            "signals": signals,
            "tau2": tau2,
            "timeout_seconds": timeout,
        }
        run.review_pending = True
        run.emit_event("review_required", review_req_data)
        run.review_pending_event.set()

        signaled = run.review_event.wait(timeout=timeout)
        run.review_pending = False

        if not signaled:
            run.emit_event("review_timeout", {"timeout_seconds": timeout})
            return "n"

        approved = bool(run.review_decision)
        run.emit_event("review_resolved", {"approved": approved})
        return "y" if approved else "n"
