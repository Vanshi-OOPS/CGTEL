"""Pytest fixtures for CGTEL server tests."""
import pytest
from starlette.testclient import TestClient

from server.app import create_app
from server.config import Settings


@pytest.fixture
def temp_settings(tmp_path):
    data_dir = tmp_path / "server_data"
    return Settings(
        server_data_dir=str(data_dir),
        review_timeout=5.0,
    )


@pytest.fixture
def app(temp_settings):
    application = create_app(temp_settings)
    yield application
    if hasattr(application.state, "server_state") and application.state.server_state:
        application.state.server_state.shutdown()


@pytest.fixture
def client(app):
    with TestClient(app) as test_client:
        yield test_client
