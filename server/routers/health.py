"""Health endpoint."""
from fastapi import APIRouter, Depends

from server.models import HealthResponse
from server.routers import get_server_state
from server.state import ServerState

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthResponse)
def get_health(state: ServerState = Depends(get_server_state)) -> HealthResponse:
    live = state.live_available
    return HealthResponse(
        status="ok",
        live_available=live,
        model=state.settings.model_name,
        mode_default="live" if live else "offline",
    )
