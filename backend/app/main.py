import logging
from pathlib import Path

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from sqlalchemy import text

from app.api import analysis, auth, dashboard, shariah, stocks
from app.core import log_redact
from app.core.config import get_settings
from app.core.db import engine
from app.core.middleware import CSRFMiddleware, SecurityHeadersMiddleware
from app.core.ratelimit import limiter

DISCLAIMER = (
    "This platform provides market research, technical analysis and Shariah-screening information for "
    "educational and decision-support purposes. Signals are not guarantees of future performance and are not "
    "personalised investment advice. Users are responsible for their own investment decisions. Shariah "
    "screening methodologies differ; verify religious compliance with an appropriately qualified authority."
)

settings = get_settings()
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
log = logging.getLogger("hss")
log_redact.install()

app = FastAPI(title=settings.app_name, version="0.1.0",
              docs_url="/api/docs" if settings.environment != "production" else None, redoc_url=None)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)
app.add_middleware(CSRFMiddleware)
app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=settings.cors_origins, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"], allow_headers=["Content-Type", "X-CSRF-Token"],
)


@app.exception_handler(Exception)
async def unhandled(request: Request, exc: Exception):  # never leak internals
    log.exception("Unhandled error on %s", request.url.path)
    return JSONResponse({"detail": "Internal server error"}, status_code=500)


app.include_router(auth.router)
app.include_router(dashboard.router)
app.include_router(stocks.router)
app.include_router(analysis.router)
app.include_router(shariah.router)


@app.get("/api/health", tags=["system"])
def health():
    db_ok = True
    try:
        with engine.connect() as c:
            c.execute(text("SELECT 1"))
    except Exception:
        db_ok = False
    return {"status": "ok" if db_ok else "degraded", "database": db_ok, "version": app.version}


@app.get("/api/disclaimer", tags=["system"])
def disclaimer():
    return {"text": DISCLAIMER}


# Hosted mode: serve the built React app from the same origin, so cookies stay SameSite and no CORS is needed.
if settings.static_dir and Path(settings.static_dir, "index.html").is_file():
    _static = Path(settings.static_dir).resolve()
    app.mount("/assets", StaticFiles(directory=_static / "assets"), name="assets")

    @app.api_route("/{path:path}", methods=["GET", "HEAD"], include_in_schema=False)
    def spa(path: str):
        if path.startswith("api/"):
            return JSONResponse({"detail": "Not Found"}, status_code=404)
        f = (_static / path).resolve()
        if path and f.is_file() and f.is_relative_to(_static):  # no path traversal outside the build folder
            return FileResponse(f)
        return FileResponse(_static / "index.html", headers={"Cache-Control": "no-cache"})
