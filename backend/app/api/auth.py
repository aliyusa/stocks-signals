from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.ratelimit import limiter
from app.core.security import (
    ACCESS_COOKIE,
    CSRF_COOKIE,
    REFRESH_COOKIE,
    create_access_token,
    create_refresh_token,
    decode_token,
    hash_password,
    new_csrf_token,
    verify_password,
)
from app.models.entities import User
from app.schemas.auth import LoginIn, RegisterIn, UserOut
from app.services import audit

router = APIRouter(prefix="/api/auth", tags=["auth"])
settings = get_settings()

MAX_FAILED = 5
LOCK_MINUTES = 15
# Constant-time-ish path for unknown emails so response time does not reveal accounts.
_DUMMY_HASH = hash_password("dummy-password-0")


def _set_session(response: Response, user: User) -> None:
    common = {"httponly": True, "secure": settings.cookie_secure, "samesite": "lax"}
    response.set_cookie(ACCESS_COOKIE, create_access_token(user.id, user.token_version),
                        max_age=settings.access_token_minutes * 60, path="/", **common)
    response.set_cookie(REFRESH_COOKIE, create_refresh_token(user.id, user.token_version),
                        max_age=settings.refresh_token_days * 86400, path="/api/auth", **common)
    # CSRF token must be readable by the SPA (double-submit pattern)
    response.set_cookie(CSRF_COOKIE, new_csrf_token(), max_age=settings.refresh_token_days * 86400,
                        path="/", httponly=False, secure=settings.cookie_secure, samesite="lax")


def _clear_session(response: Response) -> None:
    response.delete_cookie(ACCESS_COOKIE, path="/")
    response.delete_cookie(REFRESH_COOKIE, path="/api/auth")
    response.delete_cookie(CSRF_COOKIE, path="/")


@router.post("/register", response_model=UserOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.login_rate_limit)
def register(request: Request, body: RegisterIn, response: Response, db: Session = Depends(get_db)):
    email = body.email.lower()
    allowed = {e.lower() for e in settings.allowed_emails}
    if allowed and email not in allowed:
        audit.record(db, "auth.register_blocked", request, None, details={"reason": "not on ALLOWED_EMAILS"})
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Registration is by invitation only on this site")
    if db.scalar(select(User).where(User.email == email)):
        raise HTTPException(status.HTTP_409_CONFLICT, "An account with this email already exists")
    user = User(email=email, password_hash=hash_password(body.password), full_name=body.full_name)
    db.add(user)
    db.commit()
    audit.record(db, "auth.register", request, user.id)
    _set_session(response, user)
    return user


@router.post("/login", response_model=UserOut)
@limiter.limit(settings.login_rate_limit)
def login(request: Request, body: LoginIn, response: Response, db: Session = Depends(get_db)):
    user = db.scalar(select(User).where(User.email == body.email.lower()))
    now = datetime.now(UTC)
    if not user:
        verify_password(body.password, _DUMMY_HASH)
        audit.record(db, "auth.login_failed", request, details={"reason": "unknown_email"})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    locked = user.locked_until
    if locked and locked.tzinfo is None:  # SQLite returns naive datetimes
        locked = locked.replace(tzinfo=UTC)
    if locked and locked > now:
        raise HTTPException(status.HTTP_423_LOCKED, "Account temporarily locked. Try again later.")
    if not verify_password(body.password, user.password_hash) or not user.is_active:
        user.failed_logins += 1
        if user.failed_logins >= MAX_FAILED:
            user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
            user.failed_logins = 0
        db.commit()
        audit.record(db, "auth.login_failed", request, user.id)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid email or password")
    user.failed_logins = 0
    user.locked_until = None
    db.commit()
    audit.record(db, "auth.login", request, user.id)
    _set_session(response, user)
    return user


@router.post("/refresh", response_model=UserOut)
def refresh(request: Request, response: Response, db: Session = Depends(get_db)):
    token = request.cookies.get(REFRESH_COOKIE)
    payload = decode_token(token, "refresh") if token else None
    user = db.get(User, int(payload["sub"])) if payload else None
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        _clear_session(response)
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session expired")
    _set_session(response, user)
    return user


@router.post("/logout")
def logout(request: Request, response: Response, user: User = Depends(current_user), db: Session = Depends(get_db)):
    audit.record(db, "auth.logout", request, user.id)
    _clear_session(response)
    return {"detail": "Logged out"}


@router.post("/logout-all")
def logout_all(request: Request, response: Response, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    user.token_version += 1  # invalidates every issued token
    db.commit()
    audit.record(db, "auth.logout_all", request, user.id)
    _clear_session(response)
    return {"detail": "All sessions revoked"}


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(current_user)):
    return user
