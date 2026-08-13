"""Password hashing (spec §5.1: `users.password_hash` is an Argon2id hash) and
JWT access-token / opaque refresh-token primitives (`TSC-AUTH-001`, spec §7.1).

Password hashing is centralized here (rather than in `TSC-AUTH-*`) because the
seed script and factories in `TSC-DATA-001` already need to create users with
real, verifiable password hashes for demo login. `TSC-AUTH-*` reuses these two
functions instead of re-implementing hashing, and adds the token helpers below.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

from app.core.config import Settings

_hasher = PasswordHasher()

#: JWT claim identifying an access token, so a refresh token (never a JWT)
#: or a token minted for a different purpose can't be replayed as one.
ACCESS_TOKEN_TYPE = "access"


class InvalidTokenError(Exception):
    """Raised when an access token is missing, malformed, expired, or was
    signed for a different purpose. Callers map this to a `401` envelope.
    """


def hash_password(password: str) -> str:
    """Hash `password` with Argon2id, returning the encoded hash string."""
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    """Return whether `password` matches `password_hash`. Never raises on a
    mismatch/malformed hash — both are simply "not a match".
    """
    try:
        return _hasher.verify(password_hash, password)
    except VerifyMismatchError:
        return False
    except Exception:  # noqa: BLE001 - malformed/foreign hash ⇒ no match
        return False


def create_access_token(user_id: UUID, settings: Settings) -> tuple[str, int]:
    """Mint a short-lived JWT access token for `user_id`.

    Returns `(token, expires_in_seconds)`. The token is never persisted
    (spec §7.1: "kept in memory on the client") — only its signature is
    verified on each request via `decode_access_token`.
    """
    now = datetime.now(UTC)
    expires_in = settings.access_token_expires_minutes * 60
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "type": ACCESS_TOKEN_TYPE,
        "iat": now,
        "exp": now + timedelta(seconds=expires_in),
    }
    token = jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)
    return token, expires_in


def decode_access_token(token: str, settings: Settings) -> UUID:
    """Verify `token` and return the `user_id` it was issued for.

    Raises `InvalidTokenError` for any failure (expired, bad signature,
    malformed, wrong `type`) — deliberately not distinguishing *why* in the
    exception so callers return the same generic `401` either way.
    """
    try:
        payload = jwt.decode(token, settings.jwt_secret_key, algorithms=[settings.jwt_algorithm])
    except jwt.PyJWTError as exc:
        raise InvalidTokenError("Invalid or expired access token.") from exc
    if payload.get("type") != ACCESS_TOKEN_TYPE:
        raise InvalidTokenError("Invalid or expired access token.")
    try:
        return UUID(str(payload.get("sub")))
    except (TypeError, ValueError) as exc:
        raise InvalidTokenError("Invalid or expired access token.") from exc


def generate_refresh_token() -> str:
    """Generate a new opaque, high-entropy refresh token (spec §7.1: "opaque/
    long-lived"). This raw value is only ever handed to the client as the
    httpOnly cookie — the database stores only its hash (see
    `hash_refresh_token`).
    """
    return secrets.token_urlsafe(48)


def hash_refresh_token(raw_token: str, settings: Settings) -> str:
    """Deterministically hash a raw refresh token for storage/lookup.

    Keyed (HMAC) rather than a bare `sha256(token)` so a database leak of
    `token_hash` values alone can't be used to brute-force-confirm a guessed
    raw token offline without also knowing `jwt_secret_key`. Deterministic
    (unlike Argon2id) so the server can look the token up by its hash on
    `/auth/refresh`/`/auth/logout` instead of re-hashing every stored token.
    """
    return hmac.new(
        settings.jwt_secret_key.encode("utf-8"),
        raw_token.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()
