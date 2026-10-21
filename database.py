"""
Engine + session setup for FastAPI.

Usage in a route:

    from fastapi import Depends
    from database import get_session

    @app.get("/tickets/{ticket_id}")
    def read_ticket(ticket_id: str, session: Session = Depends(get_session)):
        ...
"""
import os
from collections.abc import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

DATABASE_URL = os.environ["DATABASE_URL"]  # postgresql+psycopg2://... (Supabase connection string)

engine = create_engine(DATABASE_URL, pool_pre_ping=True)


def get_session() -> Generator[Session, None, None]:
    with Session(engine) as session:
        yield session
