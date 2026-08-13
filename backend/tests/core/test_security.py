"""Argon2id password hashing round-trips and rejects mismatches/garbage."""

from __future__ import annotations

from app.core.security import hash_password, verify_password


def test_hash_and_verify_round_trip() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("correct horse battery staple", password_hash) is True


def test_verify_rejects_wrong_password() -> None:
    password_hash = hash_password("correct horse battery staple")
    assert verify_password("wrong password", password_hash) is False


def test_verify_rejects_malformed_hash() -> None:
    assert verify_password("anything", "not-an-argon2-hash") is False
