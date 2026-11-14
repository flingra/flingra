from collections.abc import Iterator

from fastapi import Request
from sqlalchemy.orm import Session

from app.database import get_db


def db_session(request: Request) -> Iterator[Session]:
    yield from get_db(request.app.state.settings)
