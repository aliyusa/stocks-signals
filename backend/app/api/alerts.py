"""Alerts, alert events and the daily job."""

from __future__ import annotations

import hmac
import logging
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator, model_validator
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.stocks import MIC_PATTERN, TICKER_PATTERN, _get_stock
from app.core.config import get_settings
from app.core.db import get_db
from app.models.entities import (
    Alert,
    AlertEvent,
    Portfolio,
    PortfolioPosition,
    SignalType,
    Stock,
    User,
    WatchlistStock,
)
from app.providers.registry import ProviderRegistry
from app.services import alerts as svc
from app.services import audit
from app.services.prices import refresh_bars
from app.services.usage import usage_summary

router = APIRouter(prefix="/api", tags=["alerts"])
log = logging.getLogger("hss.cron")
MAX_ALERTS = 50


class ConditionIn(BaseModel):
    type: str
    level: float | None = Field(None, gt=0)
    value: float | None = Field(None, ge=0, le=100)
    signal: str | None = None

    @model_validator(mode="after")
    def _check(self):
        spec = svc.CONDITIONS.get(self.type)
        if spec is None:
            raise ValueError("Unknown alert condition")
        need = spec["param"]
        if need == "level" and self.level is None:
            raise ValueError("This condition needs a price level")
        if need == "value" and self.value is None:
            raise ValueError("This condition needs a value between 0 and 100")
        if need == "signal":
            if self.signal is None:
                raise ValueError("This condition needs a signal type")
            SignalType(self.signal)
        return self

    def clean(self) -> dict:
        need = svc.CONDITIONS[self.type]["param"]
        return {"type": self.type, **({need: getattr(self, need)} if need else {})}


class AlertIn(BaseModel):
    exchange: str = Field(pattern=MIC_PATTERN)
    ticker: str = Field(pattern=TICKER_PATTERN)
    name: str | None = Field(None, max_length=120)
    condition: ConditionIn
    channels: list[str] = ["in_app"]
    cooldown_minutes: int = Field(1440, ge=60, le=10080)

    @field_validator("channels")
    @classmethod
    def _channels(cls, v):
        if not v or set(v) - set(svc.CHANNELS):
            raise ValueError(f"Channels must be some of {', '.join(svc.CHANNELS)}")
        return sorted(set(v) | {"in_app"})


class AlertEdit(BaseModel):
    name: str | None = Field(None, max_length=120)
    condition: ConditionIn | None = None
    channels: list[str] | None = None
    cooldown_minutes: int | None = Field(None, ge=60, le=10080)
    is_active: bool | None = None

    @field_validator("channels")
    @classmethod
    def _channels(cls, v):
        return None if v is None else AlertIn._channels(v)


def _row(a: Alert) -> dict:
    s = a.stock
    return {"id": a.id, "name": a.name, "condition": a.condition, "description": svc.describe(a.condition),
            "channels": a.channels, "cooldown_minutes": a.cooldown_minutes, "is_active": a.is_active,
            "last_triggered_at": a.last_triggered_at, "last_evaluated_at": a.last_evaluated_at,
            "last_result": (a.state or {}).get("last_result"), "last_message": (a.state or {}).get("last_message"),
            "created_at": a.created_at,
            "stock": None if s is None else {"ticker": s.ticker, "name": s.name, "exchange": s.exchange.code}}


def _own(db: Session, user: User, aid: int) -> Alert:
    a = db.get(Alert, aid)
    if a is None or a.user_id != user.id:
        raise HTTPException(404, "Alert not found")
    return a


@router.get("/alerts/options")
def options(_: User = Depends(current_user)):
    s = get_settings()
    return {"conditions": [{"type": k, **v} for k, v in svc.CONDITIONS.items()],
            "signal_types": [t.value for t in SignalType],
            "channels": {"in_app": True, "browser": True, "email": svc.email_configured()},
            "daily_job": bool(s.cron_secret),
            "note": "Alerts are checked on stored data when a stock is opened or refreshed, when you press "
                    "Check now, and by the daily job after the close if it is configured."}


@router.get("/alerts")
def list_alerts(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Alert).where(Alert.user_id == user.id).order_by(Alert.id.desc())).all()
    unread = db.scalar(select(func.count(AlertEvent.id)).join(Alert).where(
        Alert.user_id == user.id, AlertEvent.is_read.is_(False))) or 0
    return {"alerts": [_row(a) for a in rows], "unread": unread}


@router.post("/alerts", status_code=201)
def create_alert(request: Request, body: AlertIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    n = db.scalar(select(func.count(Alert.id)).where(Alert.user_id == user.id)) or 0
    if n >= MAX_ALERTS:
        raise HTTPException(409, f"You can keep up to {MAX_ALERTS} alerts")
    s = _get_stock(db, body.exchange, body.ticker)
    cond = body.condition.clean()
    a = Alert(user_id=user.id, stock_id=s.id, name=(body.name or svc.describe(cond)).strip(), condition=cond,
              channels=body.channels, cooldown_minutes=body.cooldown_minutes, is_active=True, state={})
    db.add(a)
    db.commit()
    audit.record(db, "alert.create", request, user.id, entity="alert", entity_id=str(a.id),
                 details={"stock": f"{s.exchange.code}:{s.ticker}", "condition": cond, "channels": a.channels})
    svc.evaluate(db, [a])  # first check on stored data straight away
    return _row(a)


@router.put("/alerts/{aid}")
def edit_alert(request: Request, aid: int, body: AlertEdit, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    a = _own(db, user, aid)
    if body.condition is not None:
        a.condition = body.condition.clean()
        a.state = {}
    if body.name is not None:
        a.name = body.name.strip() or svc.describe(a.condition)
    if body.channels is not None:
        a.channels = body.channels
    if body.cooldown_minutes is not None:
        a.cooldown_minutes = body.cooldown_minutes
    if body.is_active is not None:
        a.is_active = body.is_active
    db.commit()
    audit.record(db, "alert.update", request, user.id, entity="alert", entity_id=str(a.id),
                 details=body.model_dump(exclude_none=True))
    return _row(a)


@router.delete("/alerts/{aid}")
def delete_alert(request: Request, aid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    a = _own(db, user, aid)
    db.delete(a)
    db.commit()
    audit.record(db, "alert.delete", request, user.id, entity="alert", entity_id=str(aid))
    return {"deleted": aid}


@router.post("/alerts/check")
def check_now(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Evaluates your alerts on stored data. It never calls a data provider."""
    fired = svc.evaluate_for_user(db, user)
    return {"fired": len(fired), "checked_at": datetime.now(UTC)}


@router.get("/alerts/events")
def events(unread_only: bool = False, limit: int = Query(50, ge=1, le=200), since_id: int = 0,
           user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = (select(AlertEvent, Alert).join(Alert).where(Alert.user_id == user.id, AlertEvent.id > since_id)
         .order_by(AlertEvent.id.desc()).limit(limit))
    if unread_only:
        q = q.where(AlertEvent.is_read.is_(False))
    rows = db.execute(q).all()
    return {"events": [{"id": e.id, "alert_id": a.id, "triggered_at": e.triggered_at, "payload": e.payload,
                        "delivered": e.delivered, "is_read": e.is_read, "browser": "browser" in a.channels}
                       for e, a in rows]}


class ReadIn(BaseModel):
    ids: list[int] = Field(default_factory=list, max_length=500)
    all: bool = False


@router.post("/alerts/events/read")
def mark_read(body: ReadIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    mine = select(Alert.id).where(Alert.user_id == user.id)
    q = update(AlertEvent).where(AlertEvent.alert_id.in_(mine))
    if not body.all:
        q = q.where(AlertEvent.id.in_(body.ids or [-1]))
    n = db.execute(q.values(is_read=True)).rowcount
    db.commit()
    return {"marked": n}


# ---------- daily job ----------


def _authorised(request: Request) -> bool:
    secret = get_settings().cron_secret
    if not secret:
        return False
    given = request.headers.get("authorization", "")
    return hmac.compare_digest(given.encode(), f"Bearer {secret}".encode())


@router.get("/cron/daily")
def daily_job(request: Request, db: Session = Depends(get_db)):
    """Called by Vercel Cron once a day: refreshes held, alerted and watched stocks within the EODHD
    budget (keeping a reserve for your own browsing), then evaluates every active alert."""
    if not _authorised(request):
        raise HTTPException(404, "Not found")
    s = get_settings()
    priority: list[int] = []
    for q in (select(Alert.stock_id).where(Alert.is_active.is_(True), Alert.stock_id.is_not(None)),
              select(PortfolioPosition.stock_id).join(Portfolio).where(PortfolioPosition.closed_at.is_(None)),
              select(WatchlistStock.stock_id)):
        for sid in db.scalars(q):
            if sid not in priority:
                priority.append(sid)
    registry = ProviderRegistry(db=db)
    refreshed, skipped = [], 0
    for sid in priority:
        remaining = usage_summary(db, "eodhd", s.eodhd_daily_call_limit)["remaining"]
        if len(refreshed) >= s.cron_refresh_max or remaining <= s.cron_call_reserve:
            skipped += 1
            continue
        stock = db.get(Stock, sid)
        if stock is None:
            continue
        r = refresh_bars(db, stock, registry)
        refreshed.append({"ticker": stock.ticker, "status": r.status, "new_bars": r.new_bars})
    fired = svc.evaluate_all(db)
    summary = {"refreshed": refreshed, "skipped_for_budget": skipped, "alerts_fired": len(fired),
               "usage": usage_summary(db, "eodhd", s.eodhd_daily_call_limit)}
    audit.record(db, "cron.daily", request, None, details={k: v for k, v in summary.items() if k != "refreshed"}
                 | {"refreshed": len(refreshed)})
    return summary
