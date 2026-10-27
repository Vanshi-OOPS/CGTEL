"""Lab endpoints: /api/score, /api/benchmark, /api/reset-history."""
import asyncio
import sqlite3
import tempfile
import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field

from cgtel.config import DEFAULT_WEIGHTS, TAU_1, TAU_2
from cgtel.router.decision_router import DecisionRouter
from cgtel.scoring.engine import RiskScoringEngine
from cgtel.signals.failure_rate import HistoricalFailureRateLookup

from benchmark.evaluator import BenchmarkEvaluator
from benchmark.loader import load_scenarios

from server.routers import get_server_state
from server.state import ServerState

router = APIRouter(tags=["lab"])


# ── helpers ──────────────────────────────────────────────────────────────────

def _default_w1() -> float:
    return float(DEFAULT_WEIGHTS["w1"])

def _default_w2() -> float:
    return float(DEFAULT_WEIGHTS["w2"])

def _default_w3() -> float:
    return float(DEFAULT_WEIGHTS["w3"])


def _validate_weights(w1: float, w2: float, w3: float) -> None:
    for name, val in [("w1", w1), ("w2", w2), ("w3", w3)]:
        if not (0.0 <= val <= 1.0):
            raise HTTPException(
                status_code=422,
                detail=f"{name} must be in [0, 1], got {val}",
            )


def _validate_taus(tau1: float, tau2: float) -> None:
    if tau1 >= tau2:
        raise HTTPException(
            status_code=422,
            detail=(
                f"tau1 ({tau1}) must be strictly less than tau2 ({tau2}). "
                "tau1 is the AUTO_ALLOW/LOG_AND_MONITOR boundary; "
                "tau2 is the LOG_AND_MONITOR/HUMAN_REVIEW boundary."
            ),
        )


# ── /api/score ────────────────────────────────────────────────────────────────

class ScoreRequest(BaseModel):
    tool_name: str
    args: Dict[str, Any] = Field(default_factory=dict)
    confidence: Optional[float] = None
    w1: Optional[float] = None
    w2: Optional[float] = None
    w3: Optional[float] = None
    tau1: Optional[float] = None
    tau2: Optional[float] = None
    severity_prior: Optional[float] = None
    minimum_decision: Optional[str] = None


class ScoreTerms(BaseModel):
    reversibility: float
    confidence_gap: float
    failure_rate: float


class ScoreResponse(BaseModel):
    score: float
    tier: str
    signals: Dict[str, Any]
    terms: ScoreTerms
    clamped: bool
    score_based_tier: str
    floor: Optional[str] = None
    floor_applied: bool


@router.post("/score", response_model=ScoreResponse)
def what_if_score(
    payload: ScoreRequest,
    state: ServerState = Depends(get_server_state),
) -> ScoreResponse:
    w1 = payload.w1 if payload.w1 is not None else _default_w1()
    w2 = payload.w2 if payload.w2 is not None else _default_w2()
    w3 = payload.w3 if payload.w3 is not None else _default_w3()
    tau1 = payload.tau1 if payload.tau1 is not None else TAU_1
    tau2 = payload.tau2 if payload.tau2 is not None else TAU_2

    _validate_weights(w1, w2, w3)
    _validate_taus(tau1, tau2)

    if payload.confidence is not None and not (0.0 <= payload.confidence <= 1.0):
        raise HTTPException(
            status_code=422,
            detail=f"confidence must be in [0, 1], got {payload.confidence}",
        )
    if payload.severity_prior is not None and not (0.0 <= payload.severity_prior <= 1.0):
        raise HTTPException(status_code=422, detail="severity_prior must be in [0, 1]")
    if payload.minimum_decision not in (None, "NONE", "AUTO_ALLOW", "LOG_AND_MONITOR", "HUMAN_REVIEW"):
        raise HTTPException(status_code=422, detail="minimum_decision must be NONE, AUTO_ALLOW, LOG_AND_MONITOR, or HUMAN_REVIEW")

    severity_priors = ({payload.tool_name: payload.severity_prior}
                       if payload.severity_prior is not None else None)
    minimum_decisions = None
    if payload.minimum_decision is not None:
        minimum_decisions = {
            payload.tool_name: None if payload.minimum_decision == "NONE" else payload.minimum_decision
        }

    # Throwaway engine using the SHARED failure-rate lookup (read-only: get_failure_rate only)
    engine = RiskScoringEngine(
        w1=w1,
        w2=w2,
        w3=w3,
        failure_rate_lookup=state.failure_store,
        severity_priors=severity_priors,
        minimum_decisions=minimum_decisions,
        tau1=tau1,
        tau2=tau2,
    )
    decision = engine.compute_decision(
        payload.tool_name,
        payload.args,
        confidence=payload.confidence,
    )
    score = decision.score
    signals = decision.contributing_signals

    tier = decision.tier.value

    # Compute unclamped weighted sum for terms
    rev = signals["reversibility"]
    conf_gap = signals["confidence_gap"]
    fail = signals["failure_rate"]
    raw_score = w1 * rev + w2 * conf_gap + w3 * fail
    clamped = bool(raw_score < 0.0 or raw_score > 1.0)

    return ScoreResponse(
        score=round(score, 4),
        tier=tier,
        signals=signals,
        terms=ScoreTerms(
            reversibility=round(w1 * rev, 6),
            confidence_gap=round(w2 * conf_gap, 6),
            failure_rate=round(w3 * fail, 6),
        ),
        clamped=clamped,
        score_based_tier=signals["score_based_decision"],
        floor=signals.get("floor"),
        floor_applied=signals["floor_applied"],
    )


# ── /api/benchmark ────────────────────────────────────────────────────────────

class BenchmarkRequest(BaseModel):
    w1: Optional[float] = None
    w2: Optional[float] = None
    w3: Optional[float] = None
    tau1: Optional[float] = None
    tau2: Optional[float] = None


class BenchmarkScenarioResult(BaseModel):
    scenario_id: str
    task_instruction: str
    ground_truth: str
    assigned_tiers: List[str]
    is_unsafe_execution: bool
    is_false_positive: bool
    baseline_latency_ms: float
    cgtel_latency_ms: float


class BenchmarkSummary(BaseModel):
    total_scenarios: int
    low_risk_count: int
    medium_risk_count: int
    high_risk_count: int
    unsafe_execution_rate: float
    false_positive_rate: float
    avg_baseline_latency_ms: float
    avg_cgtel_latency_ms: float
    avg_latency_overhead_ms: float


class BenchmarkConfigUsed(BaseModel):
    w1: float
    w2: float
    w3: float
    tau1: float
    tau2: float


class BenchmarkResponse(BaseModel):
    results: List[BenchmarkScenarioResult]
    summary: BenchmarkSummary
    config_used: BenchmarkConfigUsed


@router.post("/benchmark", response_model=BenchmarkResponse)
async def run_benchmark(
    payload: BenchmarkRequest,
) -> BenchmarkResponse:
    w1 = payload.w1 if payload.w1 is not None else _default_w1()
    w2 = payload.w2 if payload.w2 is not None else _default_w2()
    w3 = payload.w3 if payload.w3 is not None else _default_w3()
    tau1 = payload.tau1 if payload.tau1 is not None else TAU_1
    tau2 = payload.tau2 if payload.tau2 is not None else TAU_2

    _validate_weights(w1, w2, w3)
    _validate_taus(tau1, tau2)

    def _run_in_thread() -> BenchmarkResponse:
        # Isolated fresh failure-rate DB so shared DB is never modified
        tmp_db = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        tmp_db.close()
        try:
            isolated_lookup = HistoricalFailureRateLookup(db_path=tmp_db.name)
            bench_engine = RiskScoringEngine(
                w1=w1, w2=w2, w3=w3,
                failure_rate_lookup=isolated_lookup,
            )
            bench_router = DecisionRouter(
                tau1=tau1, tau2=tau2,
                input_func=lambda _: "y",
            )
            evaluator = BenchmarkEvaluator(
                scoring_engine=bench_engine,
                router=bench_router,
            )
            scenarios = load_scenarios()
            scenario_map = {s.scenario_id: s.task_instruction for s in scenarios}

            results_raw, summary_raw = evaluator.evaluate_all(scenarios)
        finally:
            try:
                os.unlink(tmp_db.name)
            except OSError:
                pass

        results_out = [
            BenchmarkScenarioResult(
                scenario_id=r.scenario_id,
                task_instruction=scenario_map.get(r.scenario_id, ""),
                ground_truth=r.ground_truth_risk_label,
                assigned_tiers=[
                    t.value if hasattr(t, "value") else str(t)
                    for t in r.assigned_tiers
                ],
                is_unsafe_execution=r.is_unsafe_execution,
                is_false_positive=r.is_false_positive,
                baseline_latency_ms=r.baseline_latency_ms,
                cgtel_latency_ms=r.cgtel_latency_ms,
            )
            for r in results_raw
        ]

        summary_out = BenchmarkSummary(
            total_scenarios=summary_raw.total_scenarios,
            low_risk_count=summary_raw.low_risk_count,
            medium_risk_count=summary_raw.medium_risk_count,
            high_risk_count=summary_raw.high_risk_count,
            unsafe_execution_rate=summary_raw.unsafe_execution_rate,
            false_positive_rate=summary_raw.false_positive_rate,
            avg_baseline_latency_ms=summary_raw.avg_baseline_latency_ms,
            avg_cgtel_latency_ms=summary_raw.avg_cgtel_latency_ms,
            avg_latency_overhead_ms=summary_raw.avg_latency_overhead_ms,
        )

        return BenchmarkResponse(
            results=results_out,
            summary=summary_out,
            config_used=BenchmarkConfigUsed(
                w1=w1, w2=w2, w3=w3, tau1=tau1, tau2=tau2
            ),
        )

    return await asyncio.to_thread(_run_in_thread)


# ── /api/reset-history ────────────────────────────────────────────────────────

class ResetRequest(BaseModel):
    confirm: bool = False


class ResetResponse(BaseModel):
    cleared: bool
    default_failure_rate: float


@router.post("/reset-history", response_model=ResetResponse)
def reset_history(
    payload: ResetRequest,
    state: ServerState = Depends(get_server_state),
) -> ResetResponse:
    if not payload.confirm:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Set {"confirm": true} to clear the failure-rate history.',
        )

    # Refuse while a run is active
    run_manager = state.run_manager
    with run_manager._active_lock:
        if run_manager._active_run_id is not None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Cannot reset while run '{run_manager._active_run_id}' is active."
                ),
            )

    # Clear ONLY the tool_failure_rates table in the shared SQLite file
    conn = sqlite3.connect(state.db_path)
    try:
        with conn:
            conn.execute("DELETE FROM tool_failure_rates")
    finally:
        conn.close()

    return ResetResponse(
        cleared=True,
        default_failure_rate=state.failure_store.default_failure_rate,
    )
