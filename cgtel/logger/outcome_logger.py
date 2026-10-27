"""Deterministic in-memory and optional JSONL outcome log."""
import json
import os
from typing import Any, Dict, Optional

from cgtel.types import RiskDecision, ToolCallRequest


def _redact_api_keys(value: Any) -> Any:
    secrets = [os.environ.get("GEMINI_API_KEY"), os.environ.get("GOOGLE_API_KEY")]
    secrets = [secret for secret in secrets if secret]
    if isinstance(value, str):
        for secret in secrets:
            value = value.replace(secret, "[redacted]")
        return value
    if isinstance(value, dict):
        return {key: _redact_api_keys(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_redact_api_keys(item) for item in value]
    return value


class OutcomeLogger:
    def __init__(self, jsonl_path: Optional[str] = None):
        self.jsonl_path = jsonl_path
        self.entries = []

    def log_outcome(self, request: ToolCallRequest, decision: RiskDecision,
                    success: bool, error: Optional[Exception] = None,
                    metadata: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        metadata = metadata or {}
        if metadata.get("outcome"):
            outcome = metadata["outcome"]
        elif metadata.get("llm_error"):
            outcome = "llm_error"
        elif metadata.get("rejected_invalid"):
            outcome = "rejected_invalid"
        elif metadata.get("denied"):
            outcome = "denied"
        else:
            outcome = "executed_success" if success else "executed_failure"
        entry = {
            "tool": request.tool_name, "args": _redact_api_keys(request.args),
            "tier": decision.tier.value if decision.tier is not None else None,
            "score": decision.score,
            "signals": dict(decision.contributing_signals),
            "confidence_source": decision.contributing_signals.get("confidence_source"),
            "llm_mode": metadata.get("llm_mode"), "outcome": outcome,
            "error": _redact_api_keys(str(error)) if error else None,
        }
        if metadata.get("score_breakdown") is not None:
            entry["score_breakdown"] = metadata["score_breakdown"]
        if "degraded" in metadata:
            entry["degraded"] = bool(metadata["degraded"])
        self.entries.append(entry)
        if self.jsonl_path:
            with open(self.jsonl_path, "a", encoding="utf-8") as stream:
                stream.write(json.dumps(entry, default=str) + "\n")
        return entry
