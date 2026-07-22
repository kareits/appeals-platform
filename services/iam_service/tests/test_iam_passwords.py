"""Unit tests for bcrypt password hashing."""

from __future__ import annotations

import pytest
from iam_service.infrastructure.passwords import (
    PasswordTooLongError,
    hash_password,
    hash_password_async,
    verify_password,
    verify_password_async,
)


def test_hash_is_not_plaintext_and_verifies() -> None:
    """A hash differs from the password and verifies against it."""
    hashed = hash_password("s3cret-password")
    assert hashed != "s3cret-password"
    assert verify_password("s3cret-password", hashed)


def test_wrong_password_does_not_verify() -> None:
    """Verification fails for a different password."""
    hashed = hash_password("correct-horse")
    assert not verify_password("battery-staple", hashed)


def test_hashes_are_salted() -> None:
    """Two hashes of the same password differ (per-hash random salt)."""
    assert hash_password("same-input") != hash_password("same-input")


def test_over_length_password_is_rejected() -> None:
    """A password beyond bcrypt's 72-byte limit is rejected rather than silently truncated."""
    with pytest.raises(PasswordTooLongError):
        hash_password("a" * 73)


def test_malformed_hash_fails_closed() -> None:
    """Verifying against a malformed hash returns False rather than raising."""
    assert not verify_password("whatever", "not-a-bcrypt-hash")


async def test_async_hash_and_verify_roundtrip() -> None:
    """The off-loop async wrappers hash and verify consistently (CR-IAM-MEDIUM-002)."""
    hashed = await hash_password_async("async-secret")
    assert await verify_password_async("async-secret", hashed)
    assert not await verify_password_async("wrong", hashed)
