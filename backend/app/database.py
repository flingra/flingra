from functools import lru_cache

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from app.config import Settings
from app.errors import ServiceUnavailable


@lru_cache(maxsize=4)
def _engine_for_url(database_url: str) -> Engine:
    return create_engine(database_url, pool_pre_ping=True)


def get_engine(settings: Settings) -> Engine:
    if not settings.database_url:
        raise ServiceUnavailable("Database is not configured.")
    return _engine_for_url(settings.database_url)


def check_database(settings: Settings) -> bool:
    try:
        with get_engine(settings).connect() as connection:
            connection.execute(text("SELECT 1"))
        return True
    except ServiceUnavailable:
        raise
    except SQLAlchemyError as exc:
        raise ServiceUnavailable("Database is unavailable.") from exc
