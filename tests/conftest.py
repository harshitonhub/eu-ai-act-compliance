import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from src.persistence.models import Base, Tenant
from src.persistence.tenancy import bind_tenant, cross_tenant_context, tenant_context

PRIMARY_TENANT_ID = "11111111-1111-1111-1111-111111111111"
OTHER_TENANT_ID = "22222222-2222-2222-2222-222222222222"


def seed_tenants(session: Session) -> None:
    """Both tenants exist in every test database, so an isolation test can reference the
    other one without extra setup."""
    session.add_all(
        [
            Tenant(id=PRIMARY_TENANT_ID, name="Primary Tenant"),
            Tenant(id=OTHER_TENANT_ID, name="Other Tenant"),
        ]
    )
    session.commit()


@pytest.fixture
def session():
    """A session already acting as PRIMARY_TENANT_ID.

    Tenant context is mandatory, not incidental: src/persistence/tenancy.py refuses to
    run a query against a tenant-owned table without it. Tests get a real tenant for the
    same reason production code does -- there is no unscoped mode to fall back to.
    """
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as s:
        seed_tenants(s)
        bind_tenant(s, PRIMARY_TENANT_ID)
        yield s


def as_tenant(session: Session, tenant_id: str):
    """Act as a specific tenant for a block -- for isolation tests that populate one
    tenant then read as another."""
    return tenant_context(session, tenant_id)


def as_cross_tenant(session: Session):
    """Bypass isolation for a block, for test setup that spans tenants."""
    return cross_tenant_context(session)
