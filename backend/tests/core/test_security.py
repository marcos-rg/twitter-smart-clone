"""Argon2id password hashing round-trips and rejects mismatches/garbage; JWT
access tokens and opaque refresh-token hashing (`TSC-AUTH-001`, spec §7.1).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
import pytest

from app.core.config import Settings
from app.core.security import (
    ACCESS_TOKEN_TYPE,
    InvalidTokenError,
    create_access_token,
    decode_access_token,
    generate_refresh_token,
    hash_password,
    hash_refresh_token,
    verify_password,
)


def test_hash_and_verify_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", password_hash) is True


def test_verify_rejects_wrong_password() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("wrong password", password_hash) is False


def test_verify_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-an-argon2-hash") is False


def test_create_access_token_round_trips_to_the_same_user_id() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    user_id = uuid4()
    token, expires_in = create_access_token(user_id, settings)
    assert expires_in == settings.access_token_expires_minutes * 60
    assert decode_access_token(token, settings) == user_id


def test_decode_access_token_rejects_expired_token() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": ACCESS_TOKEN_TYPE,
            "iat": now - timedelta(minutes=20),
            "exp": now - timedelta(minutes=5),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(expired, settings)


def test_decode_access_token_rejects_bad_signature() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    other_settings = Settings(jwt_secret_key="a-different-secret")
    token, _ = create_access_token(uuid4(), other_settings)
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)


def test_decode_access_token_rejects_wrong_token_type() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": str(uuid4()),
            "type": "refresh",  # not "access" — e.g. a forged/misused token
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)


def test_decode_access_token_rejects_malformed_token() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    with pytest.raises(InvalidTokenError):
        decode_access_token("not-a-jwt", settings)


def test_decode_access_token_rejects_a_non_uuid_subject() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    now = datetime.now(UTC)
    token = jwt.encode(
        {
            "sub": "not-a-uuid",
            "type": ACCESS_TOKEN_TYPE,
            "iat": now,
            "exp": now + timedelta(minutes=15),
        },
        settings.jwt_secret_key,
        algorithm=settings.jwt_algorithm,
    )
    with pytest.raises(InvalidTokenError):
        decode_access_token(token, settings)


def test_generate_refresh_token_is_high_entropy_and_unique() -> None:
    tokens = {generate_refresh_token() for _ in range(20)}
    assert len(tokens) == 20
    assert all(len(token) >= 32 for token in tokens)


def test_hash_refresh_token_is_deterministic_and_keyed() -> None:
    settings = Settings(jwt_secret_key="unit-test-secret")
    other_settings = Settings(jwt_secret_key="a-different-secret")
    raw = generate_refresh_token()

    assert hash_refresh_token(raw, settings) == hash_refresh_token(raw, settings)
    assert hash_refresh_token(raw, settings) != hash_refresh_token(raw, other_settings)
    assert hash_refresh_token(raw, settings) != raw
