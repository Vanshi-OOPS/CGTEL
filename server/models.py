"""Pydantic data models for server requests and responses."""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: str
    live_available: bool
    model: str
    mode_default: str


class ToolParam(BaseModel):
    name: str
    type: str
    required: bool


class ToolSpec(BaseModel):
    name: str
    description: str
    params: List[ToolParam]


class WeightsConfig(BaseModel):
    w1: float
    w2: float
    w3: float


class ToolPolicyConfig(BaseModel):
    severity_prior: float
    minimum_decision: Optional[str] = None


class ConfigResponse(BaseModel):
    weights: WeightsConfig
    tau1: float
    tau2: float
    tools: List[ToolSpec]
    tool_policies: Dict[str, ToolPolicyConfig]


class RunCreateRequest(BaseModel):
    task: str
    mode: Optional[str] = None


class RunCreateResponse(BaseModel):
    run_id: str


class ReviewRequest(BaseModel):
    approve: bool


class ReviewResponse(BaseModel):
    status: str
    run_id: str
    approved: bool


class DecisionModel(BaseModel):
    score: Optional[float] = None
    tier: Optional[str] = None
    signals: Dict[str, Any] = Field(default_factory=dict)
    assessed: bool


class RunRecord(BaseModel):
    run_id: str
    created_at: str
    task: str
    mode: str
    llm_mode: str
    status: str
    tool_name: Optional[str] = None
    args: Optional[Dict[str, Any]] = None
    result: Optional[Any] = None
    error: Optional[str] = None
    extracted_confidence: Optional[float] = None
    decision: Optional[DecisionModel] = None
    outcome_log: Optional[Dict[str, Any]] = None
    ignored_calls: Optional[List[Dict[str, Any]]] = None


class ToolStat(BaseModel):
    tool_name: str
    total_calls: int
    failure_rate: float


class SessionTotals(BaseModel):
    executed: int = 0
    denied: int = 0
    rejected: int = 0
    errors: int = 0


class StatsResponse(BaseModel):
    tools: List[ToolStat]
    totals: SessionTotals
    session_totals: SessionTotals
