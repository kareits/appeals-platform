"""Password hashing for temporary dev/local authentication.

Uses bcrypt (docs/06 "proper password hashing for temporary auth"). bcrypt embeds a per-hash random
salt and a tunable work factor in the output string, so no salt is stored separately and
verification is constant-time within the library. This scheme is for the non-production dev login
only; production moves to corporate OIDC (ADR-AUTH-OIDC, TASK_06) and stores no passwords.
"""

from __future__ import annotations

import asyncio

import bcrypt

# bcrypt truncates input beyond 72 bytes; reject longer secrets rather than silently ignoring the
# tail, which would weaken the hash.
_MAX_PASSWORD_BYTES = 72


class PasswordTooLongError(ValueError):
    """Raised when a password exceeds bcrypt's 72-byte input limit."""


def hash_password(password: str) -> str:
    """Hash a plaintext password with bcrypt.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash string (algorithm, cost, salt, and digest encoded together).

    Raises:
        PasswordTooLongError: If the password exceeds bcrypt's 72-byte input limit.
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        raise PasswordTooLongError("password exceeds bcrypt's 72-byte limit")
    return bcrypt.hashpw(encoded, bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    """Verify a plaintext password against a stored bcrypt hash.

    Args:
        password: The plaintext password to check.
        password_hash: The stored bcrypt hash.

    Returns:
        ``True`` when the password matches the hash; ``False`` otherwise (including malformed
        hashes and over-length input, which can never be a valid credential).
    """
    encoded = password.encode("utf-8")
    if len(encoded) > _MAX_PASSWORD_BYTES:
        return False
    try:
        return bcrypt.checkpw(encoded, password_hash.encode("utf-8"))
    except ValueError:
        # A malformed stored hash must fail verification rather than raise to the caller.
        return False


async def hash_password_async(password: str) -> str:
    """Hash a password off the event loop.

    bcrypt is deliberately CPU-expensive; running it on the single async event loop would let
    concurrent logins/creations stall unrelated requests (CR-IAM-MEDIUM-002). This offloads the work
    to the default thread-pool executor.

    Args:
        password: The plaintext password.

    Returns:
        The bcrypt hash string.

    Raises:
        PasswordTooLongError: If the password exceeds bcrypt's 72-byte input limit.
    """
    return await asyncio.get_running_loop().run_in_executor(None, hash_password, password)


async def verify_password_async(password: str, password_hash: str) -> bool:
    """Verify a password against a stored hash off the event loop.

    Args:
        password: The plaintext password to check.
        password_hash: The stored bcrypt hash.

    Returns:
        ``True`` when the password matches the hash; ``False`` otherwise.
    """
    return await asyncio.get_running_loop().run_in_executor(
        None, verify_password, password, password_hash
    )
