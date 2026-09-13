"""Password hashing on the stdlib, no new dependency.

PBKDF2-HMAC-SHA256 at 600,000 iterations -- the figure OWASP's Password Storage Cheat
Sheet gives for PBKDF2-SHA256. bcrypt/argon2 would be stronger per unit of CPU, but both
mean adding a compiled dependency to a project whose whole install story is `uv sync`;
PBKDF2 at a correctly-sized work factor is an accepted choice, and `hashlib` ships with
Python.

Stored format is `pbkdf2_sha256$<iterations>$<salt_hex>$<hash_hex>` -- self-describing,
so raising the work factor later doesn't invalidate existing hashes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

ALGORITHM = "pbkdf2_sha256"
ITERATIONS = 600_000
SALT_BYTES = 16


def hash_password(password: str, *, iterations: int = ITERATIONS) -> str:
    salt = secrets.token_bytes(SALT_BYTES)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, iterations)
    return f"{ALGORITHM}${iterations}${salt.hex()}${digest.hex()}"


def verify_password(password: str, stored: str) -> bool:
    """False on any malformed stored value rather than raising -- a corrupt row should
    fail the login, not 500 the endpoint."""
    try:
        algorithm, iterations_str, salt_hex, expected_hex = stored.split("$")
        if algorithm != ALGORITHM:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), int(iterations_str)
        )
    except (ValueError, AttributeError):
        return False
    # compare_digest: constant-time, so a wrong password can't be narrowed down by timing.
    return hmac.compare_digest(digest.hex(), expected_hex)
