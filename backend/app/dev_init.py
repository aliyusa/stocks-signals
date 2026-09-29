"""Quick-start for local development WITHOUT Docker/PostgreSQL.

Creates tables directly (no Alembic) and seeds reference data. Intended for
DATABASE_URL=sqlite:///./dev.db only; production always uses PostgreSQL + Alembic.

Run: python -m app.dev_init
"""

import app.models  # noqa: F401
from app.core.config import get_settings
from app.core.db import Base, SessionLocal, engine
from app.seed import seed

if __name__ == "__main__":
    url = get_settings().database_url
    if not url.startswith("sqlite"):
        raise SystemExit("dev_init is for SQLite only. Use 'alembic upgrade head' for PostgreSQL.")
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    print(f"Initialised {url} with reference data (no market data).")
