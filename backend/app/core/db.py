from collections.abc import Iterator

from sqlalchemy import JSON, create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.core.config import get_settings

# JSONB on PostgreSQL, plain JSON elsewhere (SQLite in tests)
JSONType = JSON().with_variant(JSONB(), "postgresql")


class Base(DeclarativeBase):
    pass


def normalise_url(url: str) -> str:
    """Accept the URL exactly as Supabase or Render show it (postgres:// or postgresql://) and use psycopg 3."""
    for prefix in ("postgres://", "postgresql://"):
        if url.startswith(prefix):
            return "postgresql+psycopg://" + url[len(prefix):]
    return url


def _make_engine(url: str):
    url = normalise_url(url)
    kwargs: dict = {"pool_pre_ping": True, "pool_recycle": 300, "pool_size": 5, "max_overflow": 5}
    if url.startswith("postgresql"):
        # Supabase's pooler (Supavisor) in transaction mode cannot keep server-side prepared statements.
        kwargs["connect_args"] = {"prepare_threshold": None}
    if url.startswith("sqlite"):
        # SQLite drops tzinfo on round-trip, which breaks batched-insert sentinel matching.
        kwargs = {"connect_args": {"check_same_thread": False}, "use_insertmanyvalues": False}
    return create_engine(url, **kwargs)


engine = _make_engine(get_settings().database_url)
SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
