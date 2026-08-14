"""Typed application settings loaded from environment variables (12-factor).

Every value has a safe local-development default so the app boots without a
`.env` file, matching the non-secret defaults in `.env.example` /
`docker-compose.yml`. Real deployments override these via the environment.
"""

from __future__ import annotations

from functools import lru_cache
from typing import Annotated

from pydantic import BeforeValidator, Field
from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict


def _split_csv(value: object) -> object:
    """Allow `CORS_ALLOWED_ORIGINS` to be a comma-separated string in env/.env."""
    if isinstance(value, str):
        return [origin.strip() for origin in value.split(",") if origin.strip()]
    return value


class Settings(BaseSettings):
    """Application configuration sourced from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # --- App metadata -----------------------------------------------------
    app_name: str = "Twitter Smart Clone API"
    app_version: str = "0.1.0"
    environment: str = Field(default="local", description="local|test|prod")
    log_level: str = "INFO"

    # --- PostgreSQL ---------------------------------------------------------
    database_url: str = (
        "postgresql+asyncpg://twitter_smart_clone:twitter_smart_clone_dev"
        "@postgres:5432/twitter_smart_clone"
    )
    database_pool_size: int = 5
    database_max_overflow: int = 10

    # --- Redis ---------------------------------------------------------------
    redis_url: str = "redis://redis:6379/0"

    # --- MinIO / S3-compatible object storage ---------------------------------
    minio_endpoint: str = "http://minio:9000"
    minio_bucket: str = "twitter-smart-clone-media"
    minio_access_key: str = Field(default="minioadmin", alias="MINIO_ROOT_USER")
    minio_secret_key: str = Field(default="minioadmin-dev-secret", alias="MINIO_ROOT_PASSWORD")
    minio_region: str = "us-east-1"

    # --- Media uploads (spec §8.4) ----------------------------------------------
    #: Max size of a single presigned image upload. Spec §8.4: "max ~5MB each".
    media_max_image_bytes: int = 5 * 1024 * 1024
    #: Max tweet images per batch presign/confirm call (spec §8.4: "max 4
    #: images/tweet"). There is no `Tweet` row yet at presign/confirm time
    #: (TSC-TWEET-001 creates it later), so this caps the size of a single
    #: presign/confirm request batch instead.
    media_max_tweet_images: int = 4
    #: How long a presigned PUT URL remains valid. Long enough for a normal
    #: upload, short enough that a leaked URL is only exploitable briefly.
    media_presign_expires_seconds: int = 300
    #: A `pending_uploads` row still `pending` (never confirmed) after this
    #: many hours is an abandoned upload: the client got a URL but never
    #: finished/confirmed the upload. `app.workers.media_cleanup` reaps rows
    #: (and their objects, if any landed in storage) older than this.
    media_abandoned_upload_ttl_hours: int = 24

    # --- Celery ----------------------------------------------------------------
    celery_broker_url: str | None = None
    celery_result_backend: str | None = None

    # --- Security / auth ---------------------------------------------------------
    jwt_secret_key: str = "dev-only-change-me"
    jwt_algorithm: str = "HS256"
    access_token_expires_minutes: int = 15
    refresh_token_expires_days: int = 7
    refresh_cookie_name: str = "refresh_token"
    auth_rate_limit_per_minute: int = 10
    #: Per-user sliding-window limit for follow/unfollow (spec §10.3
    #: suggested default: "likes/follows 60/min/user").
    follow_rate_limit_per_minute: int = 60

    # --- CORS --------------------------------------------------------------------
    cors_allowed_origins: Annotated[list[str], NoDecode, BeforeValidator(_split_csv)] = Field(
        default_factory=lambda: ["http://localhost:5173"]
    )

    # --- Request handling ---------------------------------------------------------
    request_id_header: str = "X-Request-ID"

    # --- Readiness -----------------------------------------------------------------
    readiness_check_timeout_seconds: float = 2.0

    # --- WebSocket / realtime (spec §4.2) -------------------------------------------
    #: How often the server sends an application-level `{"type": "ping"}` frame to
    #: every open connection, and how often the reaper sweeps for stale ones.
    ws_heartbeat_interval_seconds: float = 20.0
    #: A connection with no inbound activity (client message, including a `pong`)
    #: for longer than this is considered dead and is closed + deregistered.
    ws_heartbeat_timeout_seconds: float = 45.0

    @property
    def effective_celery_broker_url(self) -> str:
        """Celery broker URL, defaulting to the shared Redis instance."""
        return self.celery_broker_url or self.redis_url

    @property
    def effective_celery_result_backend(self) -> str:
        """Celery result backend URL, defaulting to the shared Redis instance."""
        return self.celery_result_backend or self.redis_url

    @property
    def is_production(self) -> bool:
        """Whether the app is running in a production-like environment."""
        return self.environment.lower() in {"prod", "production"}


@lru_cache
def get_settings() -> Settings:
    """Return a cached `Settings` instance (env is read once per process)."""
    return Settings()
