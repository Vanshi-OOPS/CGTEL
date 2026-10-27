"""FastAPI application initialization for CGTEL Server."""
from contextlib import asynccontextmanager
from typing import Optional

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from server.config import Settings, get_settings
from server.routers import config, health, runs, stats
from server.chat import router as chat_router
from server.routes_lab import router as lab_router
from server.state import ServerState


@asynccontextmanager
async def lifespan(app: FastAPI):
    if not hasattr(app.state, "server_state") or app.state.server_state is None:
        settings = getattr(app.state, "settings", None) or get_settings()
        app.state.server_state = ServerState(settings)
    yield
    if hasattr(app.state, "server_state") and app.state.server_state is not None:
        app.state.server_state.shutdown()


def create_app(settings: Optional[Settings] = None) -> FastAPI:
    app_settings = settings or get_settings()
    application = FastAPI(
        title="CGTEL Server",
        version="0.1.0",
        lifespan=lifespan,
    )
    application.state.settings = app_settings
    application.state.server_state = ServerState(app_settings)

    application.add_middleware(
        CORSMiddleware,
        allow_origins=app_settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    application.include_router(health.router, prefix="/api")
    application.include_router(config.router, prefix="/api")
    application.include_router(runs.router, prefix="/api")
    application.include_router(stats.router, prefix="/api")
    application.include_router(lab_router, prefix="/api")
    application.include_router(chat_router, prefix="/api")

    return application


app = create_app()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server.app:app", host="127.0.0.1", port=8000, reload=False)
