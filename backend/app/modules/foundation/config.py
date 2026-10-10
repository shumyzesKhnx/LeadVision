"""Read validated configuration without exposing it in API responses."""

from pathlib import Path
from typing import Literal
from urllib.parse import urlsplit

from pydantic import Field, field_validator, model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_ROOT = Path(__file__).resolve().parents[3]
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
    job_deadline_seconds: int = Field(default=300, ge=1, le=3600)
    stage_deadline_seconds: int = Field(default=120, ge=1, le=300)
    worker_poll_seconds: float = Field(default=0.5, ge=0.05, le=5)
    saved_upload_ttl_seconds: int = Field(default=3600, ge=60, le=86400)
    generation_model: str = Field(default='qwen2.5:3b', min_length=1, max_length=200, pattern=r'^[A-Za-z0-9_.:/-]+$')
    nlp_context_tokens: int = Field(default=4096, ge=2048, le=32768)
    nlp_output_tokens: int = Field(default=768, ge=256, le=2048)
    nlp_evidence_bytes: int = Field(default=1600, ge=100, le=16000)
    nlp_timeout_seconds: int = Field(default=110, ge=1, le=120)
    outreach_context_tokens: int = Field(default=8192, ge=4096, le=32768)
    outreach_output_tokens: int = Field(default=1536, ge=768, le=2048)
    ollama_base_url: str = "http://127.0.0.1:11434"
    embedding_model_dir: Path = PROJECT_ROOT / 'models' / 'all-minilm-l6-v2'
    browser_channel: Literal['chrome', 'msedge', 'chromium'] = 'chrome'

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
        embedding_path = self.embedding_model_dir.expanduser()
        self.embedding_model_dir = embedding_path if embedding_path.is_absolute() else PROJECT_ROOT / embedding_path
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
