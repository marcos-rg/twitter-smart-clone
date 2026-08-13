"""Password hashing (spec §5.1: `users.password_hash` is an Argon2id hash).

Centralized here (rather than in `TSC-AUTH-*`) because the seed script and
factories in this task already need to create users with real, verifiable
password hashes for demo login. `TSC-AUTH-*` reuses these two functions
instead of re-implementing hashing.
"""

from __future__ import annotations

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError

_hasher = PasswordHasher()


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
