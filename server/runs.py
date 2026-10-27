"""Run manager and run session handling task lifecycle and SSE events."""
import asyncio
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
import json
import os
import threading
from typing import Any, Callable, Dict, List, Optional, Tuple
import uuid

from fastapi import HTTPException, status
from cgtel.types import RiskDecision


def serialize_decision(
    decision: Optional[RiskDecision], status_str: str
) -> Dict[str, Any]:
    if decision is None:
        return {
            "score": None,
            "tier": None,
            "signals": {},
            "assessed": False,
        }

    score = decision.score
    tier_val = (
        decision.tier.value
        if (decision.tier is not None and hasattr(decision.tier, "value"))
        else (str(decision.tier) if decision.tier is not None else None)
    )
    signals = (
        dict(decision.contributing_signals)
        if decision.contributing_signals
        else {}
    )

    # Trap 6: REJECTED_* results carry a placeholder decision with score 0.0 and tier HUMAN_REVIEW
    # LLM_ERROR / NO_TOOL_CALL have score=None and tier=None (NOT_ASSESSED)
    st = str(status_str)
    if (
        st.startswith("REJECTED")
        or st in ("LLM_ERROR", "NO_TOOL_CALL")
        or score is None
        or tier_val is None
    ):
        assessed = False
    else:
        assessed = True

    return {
        "score": score if assessed else None,
        "tier": tier_val if assessed else None,
        "signals": signals,
        "assessed": assessed,
    }


class RunSession:
    def __init__(
        self,
        run_id: str,
        task: str,
        mode: str,
        llm_mode: str,
        created_at: Optional[str] = None,
        status_val: str = "RUNNING",
        timeout_seconds: float = 120.0,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ):
        self.run_id = run_id
        self.task = task
        self.mode = mode
        self.llm_mode = llm_mode
        self.created_at = (
            created_at or datetime.now(timezone.utc).isoformat()
        )
        self.status = status_val
        self.timeout_seconds = timeout_seconds
        self.loop = loop

        self.lock = threading.Lock()
        self.events_history: List[Tuple[str, Dict[str, Any]]] = []
        self.queues: List[asyncio.Queue] = []
        self.is_finished: bool = False

        self.review_event = threading.Event()
        self.review_pending_event = threading.Event()
        self.review_pending: bool = False
        self.review_decision: Optional[bool] = None
        self.last_scored: Optional[Dict[str, Any]] = None

        self.done_event = threading.Event()

        self.tool_name: Optional[str] = None
        self.tool_args: Optional[Dict[str, Any]] = None
        self.result: Optional[Any] = None
        self.error: Optional[str] = None
        self.extracted_confidence: Optional[float] = None
        self.serialized_decision: Optional[Dict[str, Any]] = None
        self.outcome_log: Optional[Dict[str, Any]] = None
        self.ignored_calls: Optional[List[Dict[str, Any]]] = None

    def emit_event(self, event_type: str, data: Dict[str, Any]) -> None:
        with self.lock:
            self.events_history.append((event_type, data))
            if event_type in ("run_finished", "run_error"):
                self.is_finished = True
            for q in list(self.queues):
                if self.loop and self.loop.is_running():
                    self.loop.call_soon_threadsafe(
                        q.put_nowait, (event_type, data)
                    )
                else:
                    try:
                        q.put_nowait((event_type, data))
                    except Exception:
                        pass

    def subscribe(self, queue: asyncio.Queue) -> List[Tuple[str, Dict[str, Any]]]:
        with self.lock:
            snapshot = list(self.events_history)
            if not self.is_finished:
                self.queues.append(queue)
            return snapshot

    def unsubscribe(self, queue: asyncio.Queue) -> None:
        with self.lock:
            if queue in self.queues:
                self.queues.remove(queue)

    def resolve_review(self, approved: bool) -> None:
        self.review_decision = approved
        self.review_event.set()

    def to_record(self) -> Dict[str, Any]:
        return {
            "run_id": self.run_id,
            "created_at": self.created_at,
            "task": self.task,
            "mode": self.mode,
            "llm_mode": self.llm_mode,
            "status": self.status,
            "tool_name": self.tool_name,
            "args": self.tool_args,
            "result": self.result,
            "error": self.error,
            "extracted_confidence": self.extracted_confidence,
            "decision": self.serialized_decision,
            "outcome_log": self.outcome_log,
            "ignored_calls": self.ignored_calls or [],
        }


class RunManager:
    def __init__(self, data_dir: str, router: Any):
        self.data_dir = data_dir
        self.runs_file = os.path.join(data_dir, "runs.jsonl")
        self.router = router
        self._runs_lock = threading.Lock()
        self._runs_dict: Dict[str, RunSession] = {}
        self._runs_order: List[str] = []
        self._active_run_id: Optional[str] = None
        self._active_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(
            max_workers=1, thread_name_prefix="cgtel_worker"
        )
        self.load_persisted_runs()

    def load_persisted_runs(self) -> None:
        if not os.path.exists(self.runs_file):
            return
        with open(self.runs_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                    run_id = record.get("run_id")
                    if not run_id:
                        continue
                    session = RunSession(
                        run_id=run_id,
                        task=record.get("task", ""),
                        mode=record.get("mode", "offline"),
                        llm_mode=record.get("llm_mode", "offline_fallback"),
                        created_at=record.get("created_at"),
                        status_val=record.get("status", "UNKNOWN"),
                    )
                    session.is_finished = True
                    session.tool_name = record.get("tool_name")
                    session.tool_args = record.get("args")
                    session.result = record.get("result")
                    session.error = record.get("error")
                    session.extracted_confidence = record.get(
                        "extracted_confidence"
                    )
                    session.serialized_decision = record.get("decision")
                    session.outcome_log = record.get("outcome_log")
                    session.ignored_calls = record.get("ignored_calls", [])
                    session.events_history = [("run_finished", session.to_record())]

                    with self._runs_lock:
                        if run_id not in self._runs_dict:
                            self._runs_order.append(run_id)
                        self._runs_dict[run_id] = session
                except Exception:
                    pass

    def persist_run(self, session: RunSession) -> None:
        record = session.to_record()
        with open(self.runs_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, default=str) + "\n")

    def start_run(
        self,
        task: str,
        mode: str,
        agent_getter: Callable[[str], Any],
        timeout_seconds: float = 120.0,
        loop: Optional[asyncio.AbstractEventLoop] = None,
    ) -> RunSession:
        with self._active_lock:
            if self._active_run_id is not None:
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Another task run ({self._active_run_id}) is currently active.",
                )
            run_id = f"run_{uuid.uuid4().hex[:12]}"
            llm_mode = "live" if mode == "live" else "offline_fallback"
            session = RunSession(
                run_id=run_id,
                task=task,
                mode=mode,
                llm_mode=llm_mode,
                timeout_seconds=timeout_seconds,
                loop=loop,
            )
            with self._runs_lock:
                self._runs_dict[run_id] = session
                self._runs_order.append(run_id)
            self._active_run_id = run_id

        self._executor.submit(self._worker, session, agent_getter)
        return session

    def _worker(
        self, session: RunSession, agent_getter: Callable[[str], Any]
    ) -> None:
        try:
            self.router.set_current_run(session)
            session.emit_event(
                "run_started",
                {
                    "run_id": session.run_id,
                    "task": session.task,
                    "mode": session.mode,
                    "llm_mode": session.llm_mode,
                },
            )
            agent = agent_getter(session.mode)
            raw_result = agent.run_task(session.task)

            session.status = raw_result.get("status", "UNKNOWN")
            session.tool_name = raw_result.get("tool_name")
            session.tool_args = raw_result.get("args")
            session.result = raw_result.get("result")
            session.error = raw_result.get("error")
            session.extracted_confidence = raw_result.get("extracted_confidence")
            session.outcome_log = raw_result.get("outcome_log")
            session.ignored_calls = raw_result.get("ignored_calls", [])
            session.llm_mode = raw_result.get("llm_mode", session.llm_mode)
            raw_decision = raw_result.get("decision")
            session.serialized_decision = serialize_decision(
                raw_decision, session.status
            )

            run_finished_data = {
                "run_id": session.run_id,
                "task_instruction": session.task,
                "status": session.status,
                "llm_mode": session.llm_mode,
                "tool_name": session.tool_name,
                "args": session.tool_args,
                "result": session.result,
                "error": session.error,
                "extracted_confidence": session.extracted_confidence,
                "decision": session.serialized_decision,
                "outcome_log": session.outcome_log,
                "ignored_calls": session.ignored_calls,
            }
            session.emit_event("run_finished", run_finished_data)
            self.persist_run(session)
        except Exception as exc:
            session.status = "EXECUTION_ERROR"
            session.error = str(exc)
            session.serialized_decision = serialize_decision(None, session.status)
            session.emit_event("run_error", {"error": str(exc)})
            self.persist_run(session)
        finally:
            session.done_event.set()
            with self._active_lock:
                if self._active_run_id == session.run_id:
                    self._active_run_id = None
            if self.router.current_run is session:
                self.router.set_current_run(None)

    def get_run(self, run_id: str) -> Optional[RunSession]:
        with self._runs_lock:
            return self._runs_dict.get(run_id)

    def list_runs(self, limit: int = 100) -> List[Dict[str, Any]]:
        with self._runs_lock:
            # Newest first
            ordered_ids = list(reversed(self._runs_order))
            records = [
                self._runs_dict[rid].to_record()
                for rid in ordered_ids[: max(1, limit)]
                if rid in self._runs_dict
            ]
            return records

    def get_session_totals(self) -> Dict[str, int]:
        totals = {"executed": 0, "denied": 0, "rejected": 0, "errors": 0}
        with self._runs_lock:
            for session in self._runs_dict.values():
                st = session.status
                if st == "EXECUTED":
                    totals["executed"] += 1
                elif st == "DENIED_BY_HUMAN_REVIEW":
                    totals["denied"] += 1
                elif st.startswith("REJECTED"):
                    totals["rejected"] += 1
                elif st in ("RUNNING", "PENDING"):
                    continue
                else:
                    totals["errors"] += 1
        return totals

    def shutdown(self) -> None:
        self._executor.shutdown(wait=False)
