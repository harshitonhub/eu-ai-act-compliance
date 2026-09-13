"""Session-cookie authentication, role checks, and tenant-context binding.

Replaces the single shared HTTP Basic credential this project ran on through Phase 6.
That was documented as sufficient for a single-tenant internal tool; once tenants exist,
"who are you" has to answer with a specific user in a specific tenant, because that
answer is what scopes every subsequent query.

The one function that matters for isolation is `get_current_user`: resolving the user is
also what binds the tenant context that src/persistence/tenancy.py's listeners read.
Nothing else in the request path has to know tenancy exists.
"""

from __future__ import annotations

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from schemas.enums import UserRole
from src.auth.sessions import COOKIE_NAME, read_session
from src.auth.users import get_user
from src.persistence.db import get_session
from src.persistence.models import User
from src.persistence.tenancy import bind_tenant


class NotAuthenticated(Exception):
    """No valid session. Handled app-wide as a redirect to /login (see src/api/main.py)
    rather than a bare 401, because every guarded route here renders HTML for a browser."""


class NotAuthorised(Exception):
    """Authenticated, but the role isn't sufficient for this action."""

    def __init__(self, required: tuple[UserRole, ...], actual: UserRole) -> None:
        self.required = required
        self.actual = actual
        super().__init__(f"Requires one of {[r.value for r in required]}; you are {actual.value}.")


def get_current_user(request: Request, session: Session = Depends(get_session)) -> User:
    user_id = read_session(request.cookies.get(COOKIE_NAME))
    if user_id is None:
        raise NotAuthenticated
    user = get_user(session, user_id)
    if user is None:
        # Valid signature but the user is gone (deleted since the cookie was issued).
        raise NotAuthenticated

    # Binding the tenant here is what makes every downstream query tenant-safe. It has to
    # happen before any tenant-owned table is touched, and resolving the user is the
    # earliest point at which the tenant is known. FastAPI caches dependency results per
    # request, so the endpoint receives this same Session instance, already bound.
    bind_tenant(session, user.tenant_id)
    # Also on request.state so base.html can render "signed in as ..." without every
    # route having to thread the user through its template context.
    request.state.current_user = user
    return user


def require_role(*allowed: UserRole):
    """Dependency factory for role-gated routes. Read routes take `get_current_user`
    directly; anything that writes goes through this."""

    def _check(user: User = Depends(get_current_user)) -> User:
        if user.role not in allowed:
            raise NotAuthorised(allowed, user.role)
        return user

    return _check


# Writes require MEMBER or ADMIN -- VIEWER exists precisely so an auditor can read the
# compliance record without being able to change it.
require_writer = require_role(UserRole.ADMIN, UserRole.MEMBER)
require_admin = require_role(UserRole.ADMIN)
