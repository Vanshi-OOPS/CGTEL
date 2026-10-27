"""Server configuration settings."""
import os
from typing import List


class Settings:
    def __init__(
        self,
        server_data_dir: str = "",
        review_timeout: float = 0.0,
        host: str = "",
        port: int = 0,
        cors_origins: List[str] = None,
    ):
        self.server_data_dir = (
            server_data_dir
            or os.environ.get("CGTEL_SERVER_DATA_DIR", "server_data")
        )
        env_timeout = os.environ.get("CGTEL_REVIEW_TIMEOUT")
        if review_timeout > 0.0:
            self.review_timeout = float(review_timeout)
        elif env_timeout is not None:
            self.review_timeout = float(env_timeout)
        else:
            self.review_timeout = 120.0

        self.host = host or os.environ.get("CGTEL_HOST", "127.0.0.1")
        env_port = os.environ.get("CGTEL_PORT")
        self.port = port if port > 0 else (int(env_port) if env_port else 8000)

        self.cors_origins = cors_origins or [
            "http://localhost:5173",
            "http://127.0.0.1:5173",
        ]
        self.model_name = os.environ.get("CGTEL_GEMINI_MODEL", "gemini-flash-latest")


_settings: Settings = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()
    return _settings
