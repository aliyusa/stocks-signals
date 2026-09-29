"""CSRF double-submit check and security headers."""

import hmac

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import JSONResponse

from app.core.security import ACCESS_COOKIE, CSRF_COOKIE, CSRF_HEADER

UNSAFE = {"POST", "PUT", "PATCH", "DELETE"}
# Endpoints that establish a session cannot require an existing CSRF token.
CSRF_EXEMPT = {"/api/auth/login", "/api/auth/register"}


class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        if request.method in UNSAFE and request.url.path not in CSRF_EXEMPT:
            # Only cookie-authenticated requests are exposed to CSRF.
            if request.cookies.get(ACCESS_COOKIE) or request.cookies.get("hss_refresh"):
                cookie = request.cookies.get(CSRF_COOKIE, "")
                header = request.headers.get(CSRF_HEADER, "")
                if not cookie or not hmac.compare_digest(cookie, header):
                    return JSONResponse({"detail": "CSRF token missing or invalid"}, status_code=403)
        return await call_next(request)


class SecurityHeadersMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        response = await call_next(request)
        response.headers.setdefault("X-Content-Type-Options", "nosniff")
        response.headers.setdefault("X-Frame-Options", "DENY")
        response.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        response.headers.setdefault("Permissions-Policy", "geolocation=(), microphone=(), camera=()")
        if not request.url.path.startswith("/api/docs"):
            response.headers.setdefault("Content-Security-Policy", CSP)
        if request.url.scheme == "https" or request.headers.get("x-forwarded-proto") == "https":
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response


# Same policy the nginx front-end uses; the Swagger page (dev only) loads its own CDN assets, so it is skipped.
CSP = ("default-src 'self'; img-src 'self' data:; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
       "frame-ancestors 'none'; base-uri 'self'; form-action 'self'")
