"""
Bootstraps a real app_user to log into the FastAPI app with -- none exist
yet, since Phases 1-7 only ever ran as scripts, never through an
authenticated request.

Usage:
    python create_admin_user.py admin@novapay.test somepassword
    python create_admin_user.py admin@novapay.test somepassword --role admin
"""
from __future__ import annotations

import argparse
import os

from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

load_dotenv()
from api.auth import hash_password
from models import AppUser, Org, UserRole


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("email")
    parser.add_argument("password")
    parser.add_argument("--role", default="admin", choices=[r.value for r in UserRole])
    args = parser.parse_args()

    engine = create_engine(os.environ["DATABASE_URL"])
    with Session(engine) as session:
        org = session.scalar(select(Org))
        if org is None:
            raise SystemExit("No org found -- run seed_data.py first.")

        existing = session.scalar(select(AppUser).where(AppUser.email == args.email))
        if existing:
            existing.hashed_password = hash_password(args.password)
            existing.role = UserRole(args.role)
            session.commit()
            print(f"Updated existing user {args.email} (role={args.role}).")
            return

        user = AppUser(
            org_id=org.id,
            email=args.email,
            hashed_password=hash_password(args.password),
            role=UserRole(args.role),
        )
        session.add(user)
        session.commit()
        print(f"Created user {args.email} (role={args.role}) for org {org.name}.")


if __name__ == "__main__":
    main()
