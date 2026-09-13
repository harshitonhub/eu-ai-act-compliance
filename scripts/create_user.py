"""Provision a tenant and its first user -- the bootstrap path, since there is no public
sign-up and an empty database has nobody who could log in to create anyone.

    python scripts/create_user.py --tenant "Acme Ltd" --email you@acme.example --role admin

Prompts for the password rather than taking it as an argument: argv lands in shell
history and in `ps` output for every other user on the box.

Adding a user to an *existing* tenant: pass that tenant's id as --tenant-id instead of
--tenant. `--list-tenants` prints them.
"""

from __future__ import annotations

import argparse
import getpass
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select

from schemas.enums import UserRole
from src.auth.users import create_tenant, create_user
from src.persistence.db import SessionLocal
from src.persistence.models import Tenant, User


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--tenant", help="Name of a NEW tenant to create.")
    parser.add_argument("--tenant-id", help="Id of an EXISTING tenant to add the user to.")
    parser.add_argument("--email")
    parser.add_argument("--role", choices=[r.value for r in UserRole], default=UserRole.ADMIN.value)
    parser.add_argument("--list-tenants", action="store_true")
    args = parser.parse_args()

    with SessionLocal() as session:
        if args.list_tenants:
            for tenant in session.scalars(select(Tenant).order_by(Tenant.created_at)).all():
                user_count = len(session.scalars(select(User).where(User.tenant_id == tenant.id)).all())
                print(f"{tenant.id}  {tenant.name}  ({user_count} user(s))")
            return

        if not args.email:
            parser.error("--email is required")
        if bool(args.tenant) == bool(args.tenant_id):
            parser.error("pass exactly one of --tenant (new) or --tenant-id (existing)")

        if args.tenant_id:
            tenant = session.get(Tenant, args.tenant_id)
            if tenant is None:
                parser.error(f"no tenant with id {args.tenant_id!r} (try --list-tenants)")
        else:
            tenant = create_tenant(session, args.tenant)

        if session.scalars(select(User).where(User.email == args.email.strip().lower())).first():
            parser.error(f"a user with email {args.email!r} already exists")

        password = getpass.getpass("Password: ")
        if password != getpass.getpass("Confirm password: "):
            parser.error("passwords did not match")
        if len(password) < 12:
            parser.error("use at least 12 characters")

        user = create_user(
            session,
            tenant_id=tenant.id,
            email=args.email,
            password=password,
            role=UserRole(args.role),
        )

    print(f"Created {user.email} ({user.role.value}) in tenant {tenant.name!r} [{tenant.id}]")


if __name__ == "__main__":
    main()
