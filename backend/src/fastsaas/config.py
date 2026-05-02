"""Runtime configuration via environment variables.

Defaults that point at on-disk dev secrets (`infra/dev-secrets/...`) are
expressed as absolute paths anchored on this file's location, so behaviour
does not depend on the cwd of whoever started the process (uvicorn from
`backend/`, pytest from `backend/`, scripts from repo root).
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict

# config.py lives at backend/src/fastsaas/config.py — four parents up is the repo root.
_REPO_ROOT = Path(__file__).resolve().parents[3]


class Settings(BaseSettings):
    # Anchor `.env` at the workspace root so the file is found regardless of
    # the cwd the process was started from (uvicorn from backend/, pytest
    # from backend/, scripts from repo root, alembic from backend/, ...).
    model_config = SettingsConfigDict(
        env_file=str(_REPO_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    env: str = Field(default="dev", description="dev | test | staging | prod")

    app_name: str = Field(
        default="FastSaaS",
        description="Display name rendered in email subjects, FastAPI title, etc. Override per-deployment to rebrand.",
    )

    database_url: str = Field(
        default="postgresql+asyncpg://app_user:dev@localhost:5432/fastsaas",
        description="Async Postgres URL used by the FastAPI app (role: app_user, no BYPASSRLS).",
    )
    database_url_migrator: str = Field(
        default="postgresql+asyncpg://alembic_migrator:dev@localhost:5432/fastsaas",
        description="Async Postgres URL used by Alembic migrations (role: alembic_migrator, BYPASSRLS).",
    )

    redis_url: str = Field(default="redis://localhost:6379/0")

    smtp_host: str = Field(default="localhost")
    smtp_port: int = Field(default=1025)
    smtp_user: str = Field(default="")
    smtp_password: str = Field(default="")
    smtp_from: str = Field(default="no-reply@fastsaas.local")

    app_url: str = Field(
        default="http://localhost:5173",
        description="Public-facing URL used to render magic-link URLs in emails.",
    )

    jwt_signing_kid: str = Field(
        default="dev-1",
        description="Active key id; signs new JWTs. The matching public key in jwt_public_keys_dir must verify it.",
    )
    jwt_signing_key_path: str = Field(
        default=str(_REPO_ROOT / "infra/dev-secrets/jwt/dev-1.pem"),
        description="Path to PEM-encoded RS256 private key. Override in prod via JWT_SIGNING_KEY_PATH.",
    )
    jwt_public_keys_dir: str = Field(
        default=str(_REPO_ROOT / "infra/dev-secrets/jwt"),
        description="Directory containing <kid>.pub.pem files. Override in prod via JWT_PUBLIC_KEYS_DIR.",
    )

    oauth_google_client_id: str = Field(default="")
    oauth_google_client_secret: str = Field(default="")
    oauth_microsoft_client_id: str = Field(default="")
    oauth_microsoft_client_secret: str = Field(default="")
    oauth_microsoft_tenant: str = Field(
        default="common",
        description="Microsoft Entra tenant id; 'common' supports both work and personal accounts.",
    )

    oauth_dev_bypass: bool = Field(
        default=False,
        description="When true, /auth/oauth/dev/start short-circuits the provider round-trip. Dev/CI only.",
    )


@lru_cache
def get_settings() -> Settings:
    return Settings()
