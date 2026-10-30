"""Application configuration via environment variables / .env file.

All settings use the INSTITRACE_ environment prefix. A local .env file in the
backend directory (or repo root) is also read. Never commit a real .env file.
"""
from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parent.parent
REPO_ROOT = BACKEND_DIR.parent


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="INSTITRACE_",
        env_file=[str(REPO_ROOT / ".env"), str(BACKEND_DIR / ".env")],
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # Primary database URL. PostgreSQL is the intended production database,
    # e.g. postgresql+psycopg2://user:pass@localhost:5432/institrace
    # SQLite is the documented local fallback and the default for the demo.
    database_url: str = f"sqlite:///{BACKEND_DIR / 'institrace.db'}"

    # Deadline / alert configuration. These are PROTOTYPE DEFAULTS for the
    # demonstration - they are not official AICTE SLA values.
    deadline_warning_days: int = 3
    escalation_overdue_days: int = 7

    # Rule engine version - bumped whenever matching rules change so that the
    # version recorded on each assessment reflects the rules that produced it.
    rule_engine_version: str = "1.0.0"

    app_version: str = "0.1.0"

    # Demo auth. This symmetric secret signs demo session tokens. It is NOT
    # production-grade security; see docs/known-limitations.md.
    secret_key: str = "DEMO-INSECURE-SECRET-change-me"
    demo_token_ttl_hours: int = 12

    # CORS - local development origins plus the Arena preview host (regex).
    cors_origins: str = "http://localhost:5173,http://127.0.0.1:5173"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @property
    def is_sqlite(self) -> bool:
        return self.database_url.startswith("sqlite")


@lru_cache
def get_settings() -> Settings:
    return Settings()
