"""Tests for typed settings (`app.core.config.Settings`)."""

from __future__ import annotations

from app.core.config import Settings, get_settings


def test_defaults_allow_booting_without_a_dotenv_file() -> None:
    settings = Settings(_env_file=None)  # type: ignore[call-arg]

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.redis_url.startswith("redis://")
    assert settings.minio_endpoint.startswith("http://")
    assert settings.cors_allowed_origins == ["http://localhost:5173"]


def test_cors_allowed_origins_parses_comma_separated_env_string() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        cors_allowed_origins="http://localhost:5173, http://localhost:3000",  # type: ignore[arg-type]
    )

    assert settings.cors_allowed_origins == [
        "http://localhost:5173",
        "http://localhost:3000",
    ]


def test_minio_credentials_read_from_root_user_password_aliases() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        MINIO_ROOT_USER="custom-user",
        MINIO_ROOT_PASSWORD="custom-pass",
    )

    assert settings.minio_access_key == "custom-user"
    assert settings.minio_secret_key == "custom-pass"


def test_effective_celery_urls_default_to_redis_url() -> None:
    settings = Settings(_env_file=None, redis_url="redis://redis-host:6379/2")  # type: ignore[call-arg]

    assert settings.effective_celery_broker_url == "redis://redis-host:6379/2"
    assert settings.effective_celery_result_backend == "redis://redis-host:6379/2"


def test_effective_celery_urls_respect_explicit_overrides() -> None:
    settings = Settings(
        _env_file=None,  # type: ignore[call-arg]
        celery_broker_url="redis://broker:6379/1",
        celery_result_backend="redis://backend:6379/2",
    )

    assert settings.effective_celery_broker_url == "redis://broker:6379/1"
    assert settings.effective_celery_result_backend == "redis://backend:6379/2"


def test_is_production_matches_prod_and_production() -> None:
    assert Settings(_env_file=None, environment="prod").is_production is True  # type: ignore[call-arg]
    assert Settings(_env_file=None, environment="production").is_production is True  # type: ignore[call-arg]
    assert Settings(_env_file=None, environment="local").is_production is False  # type: ignore[call-arg]
    assert Settings(_env_file=None, environment="test").is_production is False  # type: ignore[call-arg]


def test_get_settings_is_cached() -> None:
    assert get_settings() is get_settings()
