"""Read validated configuration without exposing it in API responses."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[2]
PROJECT_ROOT = BACKEND_ROOT.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="LEADVISION_",
        env_file=BACKEND_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="forbid",
        hide_input_in_errors=True,
    )

    data_dir: Path = Path("data")
    database_name: str = "leadvision.sqlite3"
    database_must_exist: bool = False
    sqlite_busy_timeout_ms: int = Field(default=5000, ge=0, le=30000)
    api_host: Literal["127.0.0.1"] = "127.0.0.1"
    api_port: int = Field(default=8000, ge=1024, le=65535)
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    ollama_base_url: str = "http://127.0.0.1:11434"

    @field_validator("database_name")
    @classmethod
    def database_is_a_filename(cls, value: str) -> str:
        if not value or any(char in value for char in '/\\:') or value in {".", ".."}:
            raise ValueError("database_name must be a plain filename.")
        if not value.endswith(".sqlite3"):
            raise ValueError("database_name must end with .sqlite3.")
        return value

    @field_validator("ollama_base_url")
    @classmethod
    def runtime_is_local(cls, value: str) -> str:
        url = urlsplit(value)
        if (
            url.scheme != "http"
            or url.hostname not in {"127.0.0.1", "localhost", "::1"}
            or url.username is not None
            or url.password is not None
            or url.query
            or url.fragment
            or url.path not in {"", "/"}
        ):
            raise ValueError("Ollama must use a local HTTP origin without credentials.")
        try:
            url.port
        except ValueError:
            raise ValueError("Ollama port is invalid.") from None
        return value.rstrip("/")

    @model_validator(mode="after")
    def anchor_data_directory(self) -> "Settings":
        path = self.data_dir.expanduser()
        self.data_dir = path if path.is_absolute() else PROJECT_ROOT / path
        return self

    @property
    def database_path(self) -> Path:
        return self.data_dir / self.database_name

    @property
    def allowed_origins(self) -> set[str]:
        return {
            f"http://127.0.0.1:{self.api_port}",
            f"http://localhost:{self.api_port}",
        }
