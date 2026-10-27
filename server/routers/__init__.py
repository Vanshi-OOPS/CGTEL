"""API routers for CGTEL Server."""
from fastapi import Request
from server.state import ServerState


def get_server_state(request: Request) -> ServerState:
    return request.app.state.server_state
