"""Tenant isolation enforced at the ORM layer, not by route-handler discipline.

`.claude/rules/security.md` names cross-tenant leakage a primary risk, and
`.claude/rules/architecture.md` requires isolation be enforced "at the ORM/repository
layer, not left to route handlers to remember". A convention like "always remember to
add .where(tenant_id == ...)" fails the first time somebody forgets, and fails silently
-- the query just returns more rows than it should.

So the filter is applied by a SQLAlchemy event listener instead: every ORM SELECT that
touches a tenant-owned table gets the current tenant's criteria injected automatically,
and every write is stamped and verified against it. Forgetting is not possible, because
there is nothing to remember.

**The tenant is bound to the Session, not to a ContextVar.** That is a deliberate choice
made after a ContextVar version failed: FastAPI runs each *sync* dependency in its own
`run_in_threadpool` context copy, so a ContextVar set inside the auth dependency is
discarded before the endpoint body runs, and every query then raises. Binding to the
Session avoids the entire question -- the tenant travels on the object actually issuing
the queries, which works identically in sync code, async code, threads, and scripts.

Three failure modes, all closed rather than open:

1. **No tenant bound** while a tenant-owned table is queried -> `TenantContextError`.
   Not "return everything" (a leak), and not "return nothing" (a silent wrong answer).
2. **A query shape the filter cannot attach to** -> `TenantContextError`. `with_loader_criteria`
   binds to entities in the columns clause; `session.query(X).count()` and
   `select(func.count()).select_from(X)` bury the entity in a subquery, so the criteria
   silently does nothing and the count spans every tenant. That shape is rejected outright
   -- use `select(func.count(X.id))`, which keeps the entity in the columns clause.
3. **A write carrying someone else's tenant_id** -> `CrossTenantWriteError`, on flush.

Non-tenant tables (the legal corpus: SourceDocument, LegalProvision, Requirement, ...)
are untouched by all of this and keep working with no tenant bound at all -- which is
what lets the public /ai-risk-check endpoint run unauthenticated.
"""

from __future__ import annotations

from contextlib import contextmanager
from collections.abc import Iterator

from sqlalchemy import String, Table, event
from sqlalchemy.orm import Mapped, Session, mapped_column, with_loader_criteria
from sqlalchemy.sql import visitors

_TENANT_KEY = "tenant_id"
_CROSS_TENANT_KEY = "cross_tenant"


class TenantIsolationError(Exception):
    """Base for isolation failures. Never caught to 'recover' -- these are bugs."""


class TenantContextError(TenantIsolationError):
    """A tenant-owned table was queried without usable tenant scoping."""


class CrossTenantWriteError(TenantIsolationError):
    """A write targeted a tenant other than the bound one."""


class TenantScoped:
    """Mixin marking a table as tenant-owned. Inheriting it is the *only* thing a model
    has to do -- the listeners below pick it up from there."""

    tenant_id: Mapped[str] = mapped_column(String(36), index=True)


def bind_tenant(session: Session, tenant_id: str) -> None:
    """Scope every subsequent query on this session to `tenant_id`. Called once per
    request, from the authentication dependency."""
    session.info[_TENANT_KEY] = tenant_id


def bound_tenant_id(session: Session) -> str | None:
    return session.info.get(_TENANT_KEY)


@contextmanager
def tenant_context(session: Session, tenant_id: str) -> Iterator[None]:
    """Scoped form of `bind_tenant`, restoring whatever was bound before. For scripts and
    tests, where one session is reused while acting as different tenants."""
    previous = session.info.get(_TENANT_KEY)
    session.info[_TENANT_KEY] = tenant_id
    try:
        yield
    finally:
        if previous is None:
            session.info.pop(_TENANT_KEY, None)
        else:
            session.info[_TENANT_KEY] = previous


@contextmanager
def cross_tenant_context(session: Session) -> Iterator[None]:
    """Escape hatch for the few jobs that are genuinely tenant-agnostic: the retention
    purge (cron, no logged-in user) and test setup spanning tenants. Deliberately noisy
    to grep for -- each use is a deliberate exemption. Nothing reachable from an HTTP
    request may use this."""
    previous = session.info.get(_CROSS_TENANT_KEY, False)
    session.info[_CROSS_TENANT_KEY] = True
    try:
        yield
    finally:
        session.info[_CROSS_TENANT_KEY] = previous


def _is_cross_tenant(session: Session) -> bool:
    return bool(session.info.get(_CROSS_TENANT_KEY, False))


def _tenant_scoped_tablenames() -> set[str]:
    """Resolved lazily: models.py imports this module, so the subclasses don't exist yet
    at import time."""
    return {
        cls.__tablename__
        for cls in TenantScoped.__subclasses__()
        if hasattr(cls, "__tablename__")
    }


def _tables_in(statement) -> set[str]:
    """Every table named anywhere in the statement tree -- including inside the subquery
    that `.count()` wraps things in, which is exactly the case a top-level mapper check
    misses."""
    return {el.name for el in visitors.iterate(statement) if isinstance(el, Table)}


@event.listens_for(Session, "do_orm_execute")
def _apply_tenant_filter(execute_state) -> None:
    if not execute_state.is_select or execute_state.is_column_load or execute_state.is_relationship_load:
        return
    session = execute_state.session
    if _is_cross_tenant(session):
        return
    if not (_tables_in(execute_state.statement) & _tenant_scoped_tablenames()):
        return  # legal corpus and other shared reference data -- no tenant concept

    # `with_loader_criteria` can only attach to entities present in the columns clause.
    # When a tenant table appears only inside a subquery, SQLAlchemy reports no top-level
    # mappers -- the criteria would be accepted and then quietly do nothing.
    if not any(issubclass(mapper.class_, TenantScoped) for mapper in execute_state.all_mappers):
        raise TenantContextError(
            "This query references a tenant-owned table in a form the isolation filter "
            "cannot attach to (the entity is buried in a subquery). This is how "
            "session.query(X).count() and select(func.count()).select_from(X) behave -- "
            "both would silently count every tenant's rows. Use select(func.count(X.id)) "
            "instead, which keeps the entity in the columns clause."
        )

    tenant_id = bound_tenant_id(session)
    if tenant_id is None:
        raise TenantContextError(
            "A tenant-owned table was queried on a session with no tenant bound. Call "
            "bind_tenant(session, ...), or cross_tenant_context(session) if the caller is "
            "genuinely tenant-agnostic."
        )

    execute_state.statement = execute_state.statement.options(
        with_loader_criteria(
            TenantScoped,
            lambda cls: cls.tenant_id == tenant_id,
            include_aliases=True,
        )
    )


@event.listens_for(Session, "before_flush")
def _stamp_and_verify_writes(session: Session, _flush_context, _instances) -> None:
    """Stamps tenant_id on inserts so callers can't forget it, and blocks any write
    aimed at another tenant -- the read filter alone wouldn't stop an object constructed
    with an explicit foreign tenant_id."""
    if _is_cross_tenant(session):
        return

    tenant_id = bound_tenant_id(session)
    for obj in session.new:
        if not isinstance(obj, TenantScoped):
            continue
        if tenant_id is None:
            raise TenantContextError(
                f"Cannot insert {type(obj).__name__} on a session with no tenant bound."
            )
        if getattr(obj, "tenant_id", None) is None:
            obj.tenant_id = tenant_id
        elif obj.tenant_id != tenant_id:
            raise CrossTenantWriteError(
                f"Refusing to insert {type(obj).__name__} for tenant {obj.tenant_id!r} "
                f"while acting as {tenant_id!r}."
            )

    for obj in list(session.dirty) + list(session.deleted):
        if not isinstance(obj, TenantScoped):
            continue
        if tenant_id is None:
            raise TenantContextError(
                f"Cannot modify {type(obj).__name__} on a session with no tenant bound."
            )
        if obj.tenant_id != tenant_id:
            raise CrossTenantWriteError(
                f"Refusing to modify {type(obj).__name__} owned by tenant "
                f"{obj.tenant_id!r} while acting as {tenant_id!r}."
            )
