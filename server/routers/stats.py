"""Stats endpoint exposing per-tool metrics and session execution totals."""
from fastapi import APIRouter, Depends

from server.models import SessionTotals, StatsResponse, ToolStat
from server.routers import get_server_state
from server.state import ServerState

router = APIRouter(tags=["stats"])


@router.get("/stats", response_model=StatsResponse)
def get_stats(state: ServerState = Depends(get_server_state)) -> StatsResponse:
    raw_tools = state.get_tool_stats()
    tools = [
        ToolStat(
            tool_name=t["tool_name"],
            total_calls=t["total_calls"],
            failure_rate=t["failure_rate"],
        )
        for t in raw_tools
    ]
    raw_totals = state.run_manager.get_session_totals()
    totals = SessionTotals(
        executed=raw_totals.get("executed", 0),
        denied=raw_totals.get("denied", 0),
        rejected=raw_totals.get("rejected", 0),
        errors=raw_totals.get("errors", 0),
    )
    return StatsResponse(tools=tools, totals=totals, session_totals=totals)
