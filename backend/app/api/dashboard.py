from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.api.deps import current_user
from app.core.db import get_db
from app.models.entities import DataSource, Market, ShariahMethodology, User
from app.services.dashboard import build_dashboard

router = APIRouter(prefix="/api", tags=["dashboard"])


@router.get("/dashboard")
def dashboard(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return build_dashboard(db, user.id)


@router.get("/markets")
def markets(_: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Market).options(selectinload(Market.exchanges)).order_by(Market.id)).all()
    return [
        {"code": m.code, "name": m.name,
         "exchanges": [{"code": e.code, "name": e.name, "currency": e.currency, "timezone": e.timezone}
                       for e in m.exchanges]}
        for m in rows
    ]


@router.get("/data-sources")
def data_sources(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return [
        {"code": d.code, "name": d.name, "kind": d.kind.value, "tier": d.tier, "frequency": d.frequency,
         "delay_minutes": d.delay_minutes, "website": d.website, "notes": d.notes, "enabled": d.is_enabled,
         "last_success_at": d.last_success_at, "last_error": d.last_error}
        for d in db.scalars(select(DataSource).order_by(DataSource.id)).all()
    ]


@router.get("/shariah/methodologies")
def methodologies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(
        select(ShariahMethodology).where(
            (ShariahMethodology.is_builtin.is_(True)) | (ShariahMethodology.owner_user_id == user.id)
        )
    ).all()
    return [
        {"code": m.code, "name": m.name, "description": m.description, "thresholds": m.thresholds,
         "prohibited_activities": m.prohibited_activities, "denominator": m.denominator,
         "max_data_age_days": m.max_data_age_days, "is_builtin": m.is_builtin}
        for m in rows
    ]
