"""Runs router handling run creation, SSE events, human review, and history."""
import asyncio
import json
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from server.models import (
    ReviewRequest,
    ReviewResponse,
    RunCreateRequest,
    RunCreateResponse,
    RunRecord,
)
from server.routers import get_server_state
from server.state import ServerState

router = APIRouter(tags=["runs"])


@router.post("/runs", response_model=RunCreateResponse)
def create_run(
    payload: RunCreateRequest,
    state: ServerState = Depends(get_server_state),
) -> RunCreateResponse:
    target_mode = payload.mode
    if not target_mode:
        target_mode = "live" if state.live_available else "offline"

    if target_mode == "live" and not state.live_available:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Live mode requires GEMINI_API_KEY or GOOGLE_API_KEY",
        )

    if target_mode not in ("live", "offline"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid mode: '{target_mode}'. Must be 'live' or 'offline'.",
        )

    try:
        loop = asyncio.get_running_loop()
    except RuntimeError:
        loop = None

    session = state.run_manager.start_run(
        task=payload.task,
        mode=target_mode,
        agent_getter=state.get_agent,
        timeout_seconds=state.settings.review_timeout,
        loop=loop,
    )
    return RunCreateResponse(run_id=session.run_id)


@router.get("/runs/{run_id}/events")
async def run_events(
    run_id: str,
    request: Request,
    state: ServerState = Depends(get_server_state),
):
    session = state.run_manager.get_run(run_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    async def sse_generator():
        queue: asyncio.Queue = asyncio.Queue()
        session.loop = asyncio.get_running_loop()
        snapshot = session.subscribe(queue)
        try:
            for event_type, data in snapshot:
                yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
                if event_type in ("run_finished", "run_error"):
                    return

            while True:
                if await request.is_disconnected():
                    break
                try:
                    event_type, data = await asyncio.wait_for(
                        queue.get(), timeout=15.0
                    )
                    yield f"event: {event_type}\ndata: {json.dumps(data, default=str)}\n\n"
                    if event_type in ("run_finished", "run_error"):
                        break
                except asyncio.TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            session.unsubscribe(queue)

    return StreamingResponse(
        sse_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/runs/{run_id}/review", response_model=ReviewResponse)
def resolve_review(
    run_id: str,
    payload: ReviewRequest,
    state: ServerState = Depends(get_server_state),
) -> ReviewResponse:
    session = state.run_manager.get_run(run_id)
    if not session:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Run '{run_id}' not found",
        )

    if not session.review_pending:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Run '{run_id}' has no review pending",
        )

    if getattr(session, "gated_call_pending", False):
        from server.gated_executor import resolve_pending

        resolve_pending(run_id, payload.approve, state=state)
        return ReviewResponse(status="ok", run_id=run_id, approved=payload.approve)

    session.resolve_review(payload.approve)
    return ReviewResponse(status="ok", run_id=run_id, approved=payload.approve)


@router.get("/runs", response_model=List[RunRecord])
def list_runs(
    limit: int = Query(default=100, ge=1, le=1000),
    state: ServerState = Depends(get_server_state),
) -> List[RunRecord]:
    records = state.run_manager.list_runs(limit=limit)
    return [RunRecord(**r) for r in records]
