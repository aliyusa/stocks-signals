"""Copy everything in the local SQLite database (dev.db) into an empty PostgreSQL database, e.g. Supabase.

Usage (from backend/, with the target already migrated by `alembic upgrade head`):
    python -m app.copy_to_postgres "postgresql://postgres.xxxx:PASSWORD@aws-0-REGION.pooler.supabase.com:5432/postgres"

Keeps your account, imported NGX list, stored price bars and signals, so no EODHD calls are spent re-fetching.
It refuses to write into a target that already holds users or price bars.
"""

import sys

from sqlalchemy import create_engine, func, select, text

import app.models  # noqa: F401  (registers tables)
from app.core.db import Base, normalise_url

SOURCE = "sqlite:///./dev.db"


def main(target_url: str) -> None:
    src = create_engine(SOURCE)
    # SQLite datetimes are naive UTC, so the session time zone must be UTC too.
    dst = create_engine(normalise_url(target_url),
                        connect_args={"prepare_threshold": None, "options": "-c timezone=UTC"})
    tables = Base.metadata.sorted_tables  # parents before children
    with dst.begin() as d:
        for t in tables:
            if t.name in ("users", "price_history") and d.scalar(select(func.count()).select_from(t)):
                sys.exit(f"Target table '{t.name}' is not empty; nothing copied.")
        # Reference rows written by the seed on first start are replaced by the local copies (same ids).
        for t in reversed(tables):
            d.execute(t.delete())
        with src.connect() as s:
            for t in tables:
                rows = [dict(r._mapping) for r in s.execute(select(t))]
                if rows:
                    for i in range(0, len(rows), 1000):
                        d.execute(t.insert(), rows[i:i + 1000])
                print(f"{t.name}: {len(rows)} rows")
        # Move each id sequence past the copied ids so new rows do not collide.
        for t in tables:
            if "id" in t.c and t.c.id.autoincrement is not False:
                d.execute(text(
                    f"SELECT setval(pg_get_serial_sequence('{t.name}', 'id'), "
                    f"COALESCE((SELECT MAX(id) FROM {t.name}), 0) + 1, false) "
                    f"WHERE pg_get_serial_sequence('{t.name}', 'id') IS NOT NULL"))
    print("Done. Sign in on the hosted site with your existing email and password.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        sys.exit(__doc__)
    main(sys.argv[1])
