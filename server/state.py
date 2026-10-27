"""Application state container holding shared singletons and dependencies."""
import os
import json
import sqlite3
import threading
from typing import Any, Dict, List, Optional

from fastapi import HTTPException, status

from cgtel.agent.llm_agent import LLMAgent
from cgtel.logger.outcome_logger import OutcomeLogger
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.confidence import LLMConfidenceExtractor
from cgtel.signals.failure_rate import HistoricalFailureRateLookup

from server.config import Settings, get_settings
from server.runs import RunManager
from server.streaming_router import StreamingRouter


class ServerState:
    def __init__(self, settings: Optional[Settings] = None):
        self.settings = settings or get_settings()
        self.data_dir = self.settings.server_data_dir
        os.makedirs(self.data_dir, exist_ok=True)

        self.db_path = os.path.join(self.data_dir, "failure_rates.db")
        self.outcomes_path = os.path.join(self.data_dir, "outcomes.jsonl")

        # Trap 1: File-backed HistoricalFailureRateLookup
        self.failure_store = HistoricalFailureRateLookup(db_path=self.db_path)
        self._repair_missing_read_failures()
        self.confidence_extractor = LLMConfidenceExtractor(fallback_confidence=0.0)
        self.scoring_engine = RiskScoringEngine(
            confidence_extractor=self.confidence_extractor,
            failure_rate_lookup=self.failure_store,
        )
        self.router = StreamingRouter(
            timeout_seconds=self.settings.review_timeout
        )
        self.outcome_logger = OutcomeLogger(jsonl_path=self.outcomes_path)
        self.run_manager = RunManager(
            data_dir=self.data_dir, router=self.router
        )

        self._agent_offline: Optional[LLMAgent] = None
        self._agent_live: Optional[LLMAgent] = None
        self._agent_lock = threading.Lock()

    def _repair_missing_read_failures(self) -> None:
        """Remove legacy missing-file errors from the read_file risk history.

        A missing path is a valid read request whose result is "file not found";
        old versions recorded it as an execution failure and inflated F to 1.0.
        Rebuild only read_file's aggregate from the existing outcome ledger,
        excluding those misclassified records. Other tool history is untouched.
        """
        if not os.path.isfile(self.outcomes_path):
            return
        calls = 0
        failures = 0
        try:
            with open(self.outcomes_path, "r", encoding="utf-8") as source:
                for line in source:
                    try:
                        record = json.loads(line)
                    except (ValueError, TypeError):
                        continue
                    if record.get("tool") != "read_file":
                        continue
                    outcome = record.get("outcome")
                    if outcome not in {"executed_success", "executed_failure"}:
                        continue
                    if outcome == "executed_failure" and str(record.get("error", "")).casefold().startswith("sandbox file not found:"):
                        continue
                    calls += 1
                    failures += outcome == "executed_failure"
        except OSError:
            return
        connection = sqlite3.connect(self.db_path)
        try:
            with connection:
                if calls:
                    connection.execute(
                        "INSERT INTO tool_failure_rates (tool_name, total_calls, failure_rate) VALUES (?, ?, ?) "
                        "ON CONFLICT(tool_name) DO UPDATE SET total_calls=excluded.total_calls, failure_rate=excluded.failure_rate",
                        ("read_file", calls, failures / calls),
                    )
                else:
                    connection.execute("DELETE FROM tool_failure_rates WHERE tool_name = ?", ("read_file",))
        finally:
            connection.close()

    @property
    def live_available(self) -> bool:
        key = os.environ.get("GEMINI_API_KEY") or os.environ.get("GOOGLE_API_KEY")
        return bool(key and key.strip())

    def get_agent(self, mode: str) -> LLMAgent:
        if mode == "live":
            if not self.live_available:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Live mode requires GEMINI_API_KEY or GOOGLE_API_KEY",
                )
            with self._agent_lock:
                if self._agent_live is None:
                    self._agent_live = LLMAgent(
                        mode="live",
                        model_name=self.settings.model_name,
                        scoring_engine=self.scoring_engine,
                        router=self.router,
                        outcome_logger=self.outcome_logger,
                    )
                return self._agent_live
        elif mode == "offline":
            with self._agent_lock:
                if self._agent_offline is None:
                    self._agent_offline = LLMAgent(
                        mode="offline",
                        model_name=self.settings.model_name,
                        scoring_engine=self.scoring_engine,
                        router=self.router,
                        outcome_logger=self.outcome_logger,
                    )
                return self._agent_offline
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid mode: '{mode}'. Must be 'live' or 'offline'.",
            )

    def get_tool_stats(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.db_path):
            return []
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute(
            "SELECT tool_name, total_calls, failure_rate FROM tool_failure_rates ORDER BY tool_name"
        )
        rows = cursor.fetchall()
        conn.close()
        return [
            {
                "tool_name": row[0],
                "total_calls": int(row[1]),
                "failure_rate": float(row[2]),
            }
            for row in rows
        ]

    def shutdown(self) -> None:
        self.run_manager.shutdown()
        self.failure_store.close()
