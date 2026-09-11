"""HTTP Basic Auth gate for the assessment endpoints.

Deliberately basic, not a full user-management system: this is a single-tenant
internal tool (see docs/security-model.md) where "gate access at all" closes the actual
gap, not "support multiple users with roles." Upgrade to real session-based auth if/when
multi-tenancy is added.

Fails closed: if APP_USERNAME/APP_PASSWORD aren't configured, every request is rejected
rather than falling back to an insecure default credential.
"""

from __future__ import annotations

import os
import secrets

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials

security = HTTPBasic()


def require_auth(credentials: HTTPBasicCredentials = Depends(security)) -> str:
    expected_username = os.environ.get("APP_USERNAME")
    expected_password = os.environ.get("APP_PASSWORD")
    if not expected_username or not expected_password:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Server is not configured with APP_USERNAME/APP_PASSWORD.",
        )

    # compare_digest avoids leaking credential-length/content via timing.
    username_ok = secrets.compare_digest(credentials.username, expected_username)
    password_ok = secrets.compare_digest(credentials.password, expected_password)
    if not (username_ok and password_ok):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid credentials",
            headers={"WWW-Authenticate": "Basic"},
        )
    return credentials.username
