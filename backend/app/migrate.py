"""Bring the database schema and reference data up to date. Used by serverless hosting (Vercel), where there is
no start-up shell script. Safe to call on every cold start: it is a no-op when nothing changed.

Everything runs in ONE transaction that first takes a transaction-scoped advisory lock, so two instances never
migrate at once. Transaction-scoped (not session) locks also work through Supabase's transaction pooler, where
consecutive statements outside a transaction may land on different server connections.
"""

import logging  # noqa: I001  (ruff sees the local alembic/ folder as first-party)
from pathlib import Path

from alembic import command
from alembic.config import Config
from sqlalchemy import text
from sqlalchemy.orm import Session

from app.core.db import engine

log = logging.getLogger("hss.migrate")
BACKEND = Path(__file__).resolve().parent.parent
LOCK_ID = 834_221  # arbitrary constant shared by every instance of this app


def run() -> None:
    from app.seed import seed

    if engine.dialect.name != "postgresql":
        raise SystemExit("app.migrate is for PostgreSQL (Supabase). On SQLite use: python -m app.dev_init")
    cfg = Config()
    cfg.set_main_option("script_location", str(BACKEND / "alembic"))
    with engine.begin() as conn:
        conn.execute(text("SELECT pg_advisory_xact_lock(:id)"), {"id": LOCK_ID})
        cfg.attributes["connection"] = conn
        command.upgrade(cfg, "head")
        with Session(bind=conn, join_transaction_mode="create_savepoint") as db:
            seed(db)
    log.info("Database schema and reference data are up to date")


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run()
