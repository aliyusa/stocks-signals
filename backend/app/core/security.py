"""Password hashing (Argon2) and JWT handling."""

import secrets
import uuid
from datetime import UTC, datetime, timedelta

import jwt
from pwdlib import PasswordHash

from app.core.config import get_settings

ALGORITHM = "HS256"
ACCESS_COOKIE = "hss_access"
REFRESH_COOKIE = "hss_refresh"
CSRF_COOKIE = "hss_csrf"
CSRF_HEADER = "X-CSRF-Token"

_hasher = PasswordHash.recommended()  # Argon2id


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return _hasher.verify(password, password_hash)
    except Exception:  # malformed hash
        return False


def _encode(sub: str, kind: str, ttl: timedelta, token_version: int) -> str:
    now = datetime.now(UTC)
    payload = {
        "sub": sub,
        "type": kind,
        "ver": token_version,
        "iat": now,
        "exp": now + ttl,
        "jti": uuid.uuid4().hex,
    }
    return jwt.encode(payload, get_settings().secret_key, algorithm=ALGORITHM)


def create_access_token(user_id: int, token_version: int) -> str:
    return _encode(str(user_id), "access", timedelta(minutes=get_settings().access_token_minutes), token_version)


def create_refresh_token(user_id: int, token_version: int) -> str:
    return _encode(str(user_id), "refresh", timedelta(days=get_settings().refresh_token_days), token_version)


def decode_token(token: str, expected_type: str) -> dict | None:
    try:
        payload = jwt.decode(token, get_settings().secret_key, algorithms=[ALGORITHM])
    except jwt.PyJWTError:
        return None
    if payload.get("type") != expected_type:
        return None
    return payload


def new_csrf_token() -> str:
    return secrets.token_urlsafe(32)
