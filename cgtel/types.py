from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict


class RiskTier(str, Enum):
    AUTO_ALLOW = "AUTO_ALLOW"
    LOG_AND_MONITOR = "LOG_AND_MONITOR"
    HUMAN_REVIEW = "HUMAN_REVIEW"


@dataclass
class ToolCallRequest:
    tool_name: str
    args: Dict[str, Any]
    task_context: str = ""
    timestamp: datetime = field(default_factory=lambda: datetime.now(timezone.utc))


@dataclass
class RiskDecision:
    score: float
    tier: RiskTier
    contributing_signals: Dict[str, Any] = field(default_factory=dict)
