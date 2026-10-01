"""Vercel entrypoint. Vercel looks for a FastAPI instance named `app` in server.py at the project root.

It serves the API and the built React app (frontend/dist) from one function on one address, so the
httpOnly SameSite cookies work without CORS. Locally, keep using start-windows.bat or Docker instead.
"""

import logging
import os
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / "backend"))

# Hosted defaults; any value set in the Vercel dashboard wins.
os.environ.setdefault("ENVIRONMENT", "production")
os.environ.setdefault("COOKIE_SECURE", "true")
os.environ.setdefault("CORS_ORIGINS", "[]")
os.environ.setdefault("STATIC_DIR", str(ROOT / "frontend" / "dist"))

if os.environ.get("AUTO_MIGRATE", "1") != "0":
    try:
        from app.migrate import run as _migrate

        _migrate()
    except (Exception, SystemExit):  # the app still starts; /api/health then reports the database as down
        logging.getLogger("hss").exception("Automatic migration failed")

from app.main import app  # noqa: E402

__all__ = ["app"]
