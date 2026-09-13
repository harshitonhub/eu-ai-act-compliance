"""Signed session cookies on the stdlib, no new dependency.

A session is `<user_id>|<expiry_epoch>` plus an HMAC-SHA256 tag over that payload, keyed
on SESSION_SECRET. The cookie is signed, not encrypted: the user id inside is readable by
the client, which is fine (it's an opaque UUID and the client already knows who they are)
-- what matters is that it cannot be *altered*, and the tag prevents that.

Fails closed on an unset SESSION_SECRET, matching how the rest of the app treats missing
configuration: refuse to serve rather than fall back to a default key that would make
every deployment forgeable with the same forged cookie.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
import time

COOKIE_NAME = "session"
DEFAULT_MAX_AGE_SECONDS = 12 * 60 * 60


class SessionConfigError(RuntimeError):
    """SESSION_SECRET is missing. Not recoverable at request time."""


def _secret() -> bytes:
    secret = os.environ.get("SESSION_SECRET")
    if not secret:
        raise SessionConfigError("SESSION_SECRET is not configured.")
    return secret.encode()


def _sign(payload: str) -> str:
    return hmac.new(_secret(), payload.encode(), hashlib.sha256).hexdigest()


def issue_session(user_id: str, *, max_age_seconds: int = DEFAULT_MAX_AGE_SECONDS) -> str:
    payload = f"{user_id}|{int(time.time()) + max_age_seconds}"
    token = f"{payload}|{_sign(payload)}"
    return base64.urlsafe_b64encode(token.encode()).decode()


def read_session(cookie_value: str | None) -> str | None:
    """Returns the user id, or None if the cookie is absent, malformed, tampered with, or
    expired. Callers treat None as 'not logged in' -- there is no partial trust here."""
    if not cookie_value:
        return None
    try:
        token = base64.urlsafe_b64decode(cookie_value.encode()).decode()
        user_id, expiry_str, provided_tag = token.rsplit("|", 2)
        payload = f"{user_id}|{expiry_str}"
    except (ValueError, UnicodeDecodeError):
        return None

    # Signature first: don't act on any field of an unverified payload.
    if not hmac.compare_digest(provided_tag, _sign(payload)):
        return None
    try:
        if int(expiry_str) < time.time():
            return None
    except ValueError:
        return None
    return user_id
