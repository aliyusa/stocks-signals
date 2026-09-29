from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.core.db import get_db
from app.core.security import ACCESS_COOKIE, decode_token
from app.models.entities import User


def current_user(request: Request, db: Session = Depends(get_db)) -> User:
    token = request.cookies.get(ACCESS_COOKIE)
    payload = decode_token(token, "access") if token else None
    if not payload:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Not authenticated")
    user = db.get(User, int(payload["sub"]))
    if not user or not user.is_active or user.token_version != payload.get("ver"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Session no longer valid")
    return user
