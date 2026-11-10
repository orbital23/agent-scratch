from enum import StrEnum
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

ROOT = Path(__file__).resolve().parents[4]  # raíz del repo
ENV_FILE = ROOT / ".env"


class AuthProvider(StrEnum):
    API_KEY = "api_key"
    ENTRA_ID = "entra_id"


class _EnvSettings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE, env_file_encoding="utf-8", extra="ignore")


class FoundrySettings(_EnvSettings):
    """Variables FOUNDRY_*: conexión a Microsoft Foundry."""

    model_config = SettingsConfigDict(env_prefix="FOUNDRY_")

    endpoint: str = ""
    auth_provider: AuthProvider = AuthProvider.ENTRA_ID  # S1 lo fija en api_key para el mock (.env.example)
    api_key: SecretStr = SecretStr("")
    deployment: str = "gpt-5-mini"
    embedding_deployment: str = "text-embedding-3-small"
    timeout_s: float = Field(30, gt=0)
    max_retries: int = Field(2, ge=0)


class IngestSettings(_EnvSettings):
    """Variables INGEST_*: ingesta del corpus. Todo vive bajo data/, que no se versiona."""

    model_config = SettingsConfigDict(env_prefix="INGEST_")

    corpus_dir: Path = ROOT / "data" / "corpus"
    data_dir: Path = ROOT / "data"
    chunk_max_chars: int = Field(1500, ge=200)
    batch_size: int = Field(16, ge=1)


class Settings(_EnvSettings):
    # cada tema agrega su bloque: T2 ingest y search, T3 mcp, T4 cosmos y otel
    domain: str = "fraud"
    max_turns: int = Field(10, ge=1)
    foundry: FoundrySettings = Field(default_factory=FoundrySettings)
    ingest: IngestSettings = Field(default_factory=IngestSettings)