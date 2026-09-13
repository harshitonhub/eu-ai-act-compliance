"""User and tenant provisioning. Deterministic, no LLM.

The `User` table is deliberately outside the automatic tenant filter (see
src/persistence/models.py): authenticating means finding a user *before* a tenant context
exists, so the filter would have nothing to filter on. This module is therefore the one
place allowed to query users directly, and it scopes by tenant explicitly wherever the
caller is an already-authenticated user administering their own tenant.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from schemas.enums import UserRole
from src.auth.passwords import hash_password, verify_password
from src.persistence.models import Tenant, User


def create_tenant(session: Session, name: str) -> Tenant:
    tenant = Tenant(name=name)
    session.add(tenant)
    session.commit()
    return tenant


def create_user(
    session: Session, *, tenant_id: str, email: str, password: str, role: UserRole
) -> User:
    user = User(
        tenant_id=tenant_id,
        email=email.strip().lower(),
        password_hash=hash_password(password),
        role=role,
    )
    session.add(user)
    session.commit()
    return user


def authenticate(session: Session, email: str, password: str) -> User | None:
    """None for both 'no such user' and 'wrong password' -- the caller shows one message
    for both, so enumeration can't distinguish a registered email from an unregistered one.

    The dummy verify on the missing-user path keeps the two branches comparably expensive,
    so response timing doesn't leak the distinction either.
    """
    user = session.scalars(select(User).where(User.email == email.strip().lower())).first()
    if user is None:
        verify_password(password, hash_password("timing-equalisation-dummy", iterations=1000))
        return None
    if not verify_password(password, user.password_hash):
        return None
    return user


def get_user(session: Session, user_id: str) -> User | None:
    return session.get(User, user_id)


def list_users_for_tenant(session: Session, tenant_id: str) -> list[User]:
    """Explicitly tenant-scoped: `User` isn't covered by the automatic filter, so this is
    a case where the `.where()` genuinely does have to be remembered."""
    return list(
        session.scalars(select(User).where(User.tenant_id == tenant_id).order_by(User.email)).all()
    )
