"""Execute chat tools through CGTEL scoring and the server's run/review ledger."""

from __future__ import annotations

import threading
import uuid
import json
from typing import Any, Mapping, Optional

from cgtel.logger import logger
from cgtel.types import RiskDecision, ToolCallRequest
from server.chat_tools import CHAT_TOOLS
from server.runs import RunSession, serialize_decision


_TOOLS = {tool["name"]: tool["execute"] for tool in CHAT_TOOLS}
_PENDING_LOCK = threading.RLock()


def _get_state(state: Any = None) -> Any:
    if state is not None:
        return state
    # Lazy import avoids coupling module initialization to the global FastAPI app.
    from server.app import app

    return app.state.server_state


def _score_breakdown(state: Any, decision: RiskDecision, degraded: bool) -> dict[str, Any]:
    signals = decision.contributing_signals or {}
    engine = state.scoring_engine
    return {
        "V": signals.get("reversibility"),
        "C": signals.get("confidence"),
        "F": signals.get("failure_rate"),
        "severity_prior": signals.get("severity_prior"),
        "historical_failure_rate": signals.get("historical_failure_rate"),
        "weights": {"w1": engine.w1, "w2": engine.w2, "w3": engine.w3},
        "R": decision.score,
        "score_based_decision": signals.get("score_based_decision"),
        "floor": signals.get("floor"),
        "floor_applied": bool(signals.get("floor_applied", False)),
        "decision": decision.tier.value if decision.tier is not None else None,
        "degraded": bool(degraded),
    }


def _new_session(
    state: Any,
    tool_name: str,
    args: dict[str, Any],
    decision: RiskDecision,
    breakdown: dict[str, Any],
    degraded: bool,
) -> RunSession:
    manager = state.run_manager
    run_id = f"run_{uuid.uuid4().hex[:12]}"
    session = RunSession(
        run_id=run_id,
        task=f"Execute tool: {tool_name}",
        mode="offline",
        llm_mode="direct_tool",
        timeout_seconds=state.settings.review_timeout,
    )
    session.tool_name = tool_name
    session.tool_args = args
    session.extracted_confidence = decision.contributing_signals.get("confidence")
    session.score_breakdown = breakdown
    session.degraded = degraded
    session.serialized_decision = serialize_decision(decision, "RUNNING")
    session.last_scored = {
        "tool_name": tool_name,
        "args": args,
        "score": decision.score,
        "tier": decision.tier.value,
        "contributing_signals": dict(decision.contributing_signals),
    }
    # Register through the existing in-memory manager so GET /api/runs and
    # POST /api/runs/{run_id}/review can find the same RunSession.
    with manager._runs_lock:
        manager._runs_dict[run_id] = session
        manager._runs_order.append(run_id)
    session.emit_event("run_started", {
        "run_id": run_id,
        "task": session.task,
        "mode": session.mode,
        "llm_mode": session.llm_mode,
    })
    session.emit_event("scored", session.last_scored)
    return session


def _finish(state: Any, session: RunSession, approved: Optional[bool] = None) -> dict[str, Any]:
    decision = _decision_from_session(session)
    result: Any = None
    error: Optional[Exception] = None
    status: str

    if approved is False:
        status = "DENIED_BY_HUMAN_REVIEW"
        session.outcome_log = state.outcome_logger.log_outcome(
            ToolCallRequest(session.tool_name or "", session.tool_args or {}, session.task),
            decision,
            False,
            metadata={"denied": True, "llm_mode": session.llm_mode,
                      "score_breakdown": getattr(session, "score_breakdown", None),
                      "degraded": getattr(session, "degraded", False)},
        )
    else:
        try:
            result = _TOOLS[session.tool_name or ""](**(session.tool_args or {}))
            status = "EXECUTED"
            state.scoring_engine.failure_rate_lookup.update(session.tool_name or "", False)
            session.outcome_log = state.outcome_logger.log_outcome(
                ToolCallRequest(session.tool_name or "", session.tool_args or {}, session.task),
                decision,
                True,
                metadata={"llm_mode": session.llm_mode,
                          "score_breakdown": getattr(session, "score_breakdown", None),
                          "degraded": getattr(session, "degraded", False)},
            )
        except Exception as exc:  # Preserve execution failures in the existing ledger.
            error = exc
            status = "EXECUTION_ERROR"
            state.scoring_engine.failure_rate_lookup.update(session.tool_name or "", True)
            session.outcome_log = state.outcome_logger.log_outcome(
                ToolCallRequest(session.tool_name or "", session.tool_args or {}, session.task),
                decision,
                False,
                error=exc,
            metadata={"llm_mode": session.llm_mode,
                      "score_breakdown": getattr(session, "score_breakdown", None),
                      "degraded": getattr(session, "degraded", False)},
            )

    session.status = status
    session.result = result
    session.error = str(error) if error else None
    session.serialized_decision = serialize_decision(decision, status)
    session.review_pending = False
    session.done_event.set()
    run_finished = {
        "run_id": session.run_id,
        "task_instruction": session.task,
        "status": status,
        "llm_mode": session.llm_mode,
        "tool_name": session.tool_name,
        "args": session.tool_args,
        "result": result,
        "error": session.error,
        "extracted_confidence": session.extracted_confidence,
        "decision": session.serialized_decision,
        "outcome_log": session.outcome_log,
        "ignored_calls": [],
    }
    session.emit_event("run_finished", run_finished)
    state.run_manager.persist_run(session)

    if status == "DENIED_BY_HUMAN_REVIEW":
        return {"status": "denied", "risk": decision.score, "decision": decision.tier.value}
    if status == "EXECUTION_ERROR":
        return {"status": "execution_error", "risk": decision.score, "decision": decision.tier.value, "error": session.error}
    return {"status": "executed", "result": result, "risk": decision.score, "decision": decision.tier.value}


def _decision_from_session(session: RunSession) -> RiskDecision:
    saved = session.serialized_decision or {}
    from cgtel.types import RiskTier

    tier_value = saved.get("tier")
    return RiskDecision(
        score=saved.get("score"),
        tier=RiskTier(tier_value) if tier_value else None,
        contributing_signals=dict(saved.get("signals") or {}),
    )


def gated_call(
    tool_name: str,
    args: Mapping[str, Any],
    *,
    state: Any = None,
    confidence: Optional[float] = None,
    confidence_source: Optional[str] = None,
    degraded: bool = False,
) -> dict[str, Any]:
    """Score a proposed chat tool call, then execute or register it for review."""
    if tool_name not in _TOOLS:
        raise ValueError(f"Unknown chat tool: {tool_name}")
    if not isinstance(args, Mapping):
        raise TypeError("args must be a mapping")

    server_state = _get_state(state)
    call_args = dict(args)
    decision = server_state.scoring_engine.compute_decision(
        tool_name,
        call_args,
        confidence=confidence,
        confidence_source=confidence_source,
    )
    breakdown = _score_breakdown(server_state, decision, degraded)
    logger.info("Chat tool risk breakdown: %s", json.dumps({"tool": tool_name, **breakdown}, default=str))
    session = _new_session(server_state, tool_name, call_args, decision, breakdown, degraded)

    if decision.tier.value == "HUMAN_REVIEW":
        session.review_pending = True
        session.gated_call_pending = True
        session.review_pending_event.set()
        session.emit_event("review_required", {
            "tool_name": tool_name,
            "args": call_args,
            "score": decision.score,
            "signals": dict(decision.contributing_signals),
            "tau2": server_state.router.tau2,
            "timeout_seconds": session.timeout_seconds,
        })
        timer = threading.Timer(session.timeout_seconds, _expire_pending, args=(session.run_id, server_state))
        timer.daemon = True
        session.pending_timer = timer
        timer.start()
        return {"status": "pending_approval", "run_id": session.run_id, "risk": decision.score, "decision": decision.tier.value, "score_breakdown": breakdown}

    result = _finish(server_state, session)
    result["score_breakdown"] = breakdown
    return result


def _expire_pending(run_id: str, state: Any) -> None:
    session = state.run_manager.get_run(run_id)
    if session is None:
        return
    with _PENDING_LOCK:
        if not session.review_pending or not getattr(session, "gated_call_pending", False):
            return
        session.gated_call_pending = False
        session.resolve_review(False)
        session.emit_event("review_timeout", {"timeout_seconds": session.timeout_seconds})
        _finish(state, session, approved=False)


def resolve_pending(run_id: str, approved: bool, *, state: Any = None) -> dict[str, Any]:
    """Resolve a pending chat-tool review, executing only when explicitly approved."""
    if not isinstance(approved, bool):
        raise TypeError("approved must be a boolean")
    server_state = _get_state(state)
    session = server_state.run_manager.get_run(run_id)
    if session is None or not getattr(session, "gated_call_pending", False):
        raise ValueError(f"No gated tool review exists for run '{run_id}'")
    with _PENDING_LOCK:
        if not session.review_pending:
            raise ValueError(f"No review is pending for run '{run_id}'")
        session.gated_call_pending = False
        timer = getattr(session, "pending_timer", None)
        if timer is not None and timer is not threading.current_thread():
            timer.cancel()
        session.resolve_review(approved)
        session.emit_event("review_resolved", {"approved": approved})
        return _finish(server_state, session, approved=approved)


__all__ = ["gated_call", "resolve_pending"]
