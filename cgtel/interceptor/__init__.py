import functools
import inspect
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from cgtel.logger import logger
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.types import RiskDecision, ToolCallRequest


def gated_tool(
    func: Optional[Callable] = None,
    *,
    task_context: str = "",
    scoring_engine: Optional[RiskScoringEngine] = None,
    router: Optional[DecisionRouter] = None,
    auto_approve: Optional[bool] = None,
):
    """
    Decorator wrapping tool functions.
    
    Execution Flow:
      1. Interceptor: captures call arguments and constructs a ToolCallRequest.
      2. Signals & Risk Scoring: extracts risk signals and calculates composite risk score.
      3. Router: evaluates risk score against policy thresholds (AUTO_ALLOW, LOG_AND_MONITOR, HUMAN_REVIEW).
      4. Execute or Block: executes function if permitted, or blocks/raises PermissionError if human review denies it.
    """
    engine = scoring_engine or RiskScoringEngine()
    decision_router = router or DecisionRouter()

    def decorator(fn: Callable) -> Callable:
        @functools.wraps(fn)
        def wrapper(*args, **kwargs) -> Any:
            # Extract framework control kwargs prior to binding to target function signature
            ctx = kwargs.pop("_task_context", task_context)
            call_auto_approve = kwargs.pop("_auto_approve", auto_approve)

            # Bind target function signature
            sig = inspect.signature(fn)
            bound = sig.bind(*args, **kwargs)
            bound.apply_defaults()
            args_dict = dict(bound.arguments)

            request = ToolCallRequest(
                tool_name=fn.__name__,
                args=args_dict,
                task_context=ctx,
                timestamp=datetime.now(timezone.utc),
            )

            # 2. Risk scoring step
            decision = engine.compute_decision(fn.__name__, args=args_dict)

            # 3. Decision routing step
            decision = decision_router.route(
                decision,
                tool_name=fn.__name__,
                args=args_dict,
                auto_approve=call_auto_approve,
            )

            # Attach metadata for inspection/testing
            wrapper.last_request = request
            wrapper.last_decision = decision

            # 4. Target function execution
            return fn(*args, **kwargs)

        wrapper.last_request = None
        wrapper.last_decision = None
        return wrapper

    if func is None:
        return decorator
    return decorator(func)


__all__ = ["gated_tool"]
