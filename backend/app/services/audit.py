from fastapi import Request
from sqlalchemy.orm import Session

from app.models.entities import AuditLog


def record(db: Session, action: str, request: Request | None = None, user_id: int | None = None,
           entity: str | None = None, entity_id: str | None = None, details: dict | None = None) -> None:
    ip = request.client.host if request and request.client else None
    ua = request.headers.get("user-agent", "")[:255] if request else None
    db.add(AuditLog(user_id=user_id, action=action, entity=entity, entity_id=entity_id, ip=ip,
                    user_agent=ua, details=details))
    db.commit()
