"""Shariah screening: methodologies, per-stock inputs (activities, fundamentals, reviews) and results."""

from __future__ import annotations

import re
import secrets
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import delete, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import current_user
from app.api.stocks import MIC_PATTERN, TICKER_PATTERN, _get_stock
from app.core.db import get_db
from app.engines import shariah as engine
from app.models.entities import (
    DataSource,
    Exchange,
    Fundamentals,
    Market,
    ShariahMethodology,
    ShariahScreen,
    Stock,
    User,
)
from app.services import audit
from app.services import shariah as svc

router = APIRouter(prefix="/api", tags=["shariah"])

STATUSES = ("COMPLIANT", "NON_COMPLIANT", "QUESTIONABLE", "INSUFFICIENT_DATA", "UNDER_REVIEW", "NOT_SCREENED")


def _stock(db: Session, mic: str, ticker: str) -> Stock:
    if not (re.fullmatch(MIC_PATTERN, mic) and re.fullmatch(TICKER_PATTERN, ticker)):
        raise HTTPException(422, "Invalid exchange or ticker")
    return _get_stock(db, mic, ticker)


def _sid(s: Stock) -> str:
    return f"{s.exchange.code}:{s.ticker}"


# ---------- vocabulary and methodologies ----------


@router.get("/shariah/vocabulary")
def vocabulary(_: User = Depends(current_user)):
    return {
        "prohibited": [{"tag": k, "label": v} for k, v in engine.PROHIBITED_ACTIVITIES.items()],
        "permissible": [{"tag": k, "label": v} for k, v in engine.PERMISSIBLE_ACTIVITIES.items()],
        "denominators": [{"key": k, "label": v} for k, v in engine.DENOMINATORS.items()],
        "thresholds": [{"key": k, "label": v} for k, v in engine.THRESHOLD_KEYS.items()],
        "fundamental_fields": list(engine.FUNDAMENTAL_FIELDS),
        "statuses": list(STATUSES),
    }


@router.get("/shariah/methodologies")
def list_methodologies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    default = svc.user_methodology(db, user)
    return [{**svc.methodology_dict(m, user), "is_default": m.id == default.id}
            for m in svc.visible_methodologies(db, user)]


class CloneIn(BaseModel):
    from_id: int
    name: str = Field(min_length=3, max_length=120)


class MethodologyIn(BaseModel):
    name: str = Field(min_length=3, max_length=120)
    description: str = Field(max_length=2000)
    thresholds: dict[str, float]
    denominator: str
    prohibited_activities: list[str] = Field(max_length=len(engine.PROHIBITED_ACTIVITIES))
    max_data_age_days: int


def _own(db: Session, user: User, mid: int) -> ShariahMethodology:
    m = db.get(ShariahMethodology, mid)
    if m is None or not svc.accessible(m, user):
        raise HTTPException(404, "Methodology not found")
    if m.is_builtin or m.owner_user_id != user.id:
        raise HTTPException(403, "Built-in methodologies cannot be edited. Make a copy and edit the copy.")
    return m


@router.post("/shariah/methodologies", status_code=201)
def clone_methodology(request: Request, body: CloneIn, user: User = Depends(current_user),
                      db: Session = Depends(get_db)):
    src = db.get(ShariahMethodology, body.from_id)
    if not svc.accessible(src, user):
        raise HTTPException(404, "Methodology not found")
    owned = db.scalars(select(ShariahMethodology).where(ShariahMethodology.owner_user_id == user.id)).all()
    if len(owned) >= 10:
        raise HTTPException(409, "You can keep up to 10 custom methodologies")
    m = ShariahMethodology(code=f"u{user.id}-{secrets.token_hex(4)}", name=body.name.strip(),
                           description=f"Custom copy of {src.name}. {src.description}"[:2000],
                           thresholds=dict(src.thresholds), prohibited_activities=list(src.prohibited_activities),
                           denominator=src.denominator, max_data_age_days=src.max_data_age_days,
                           owner_user_id=user.id, is_builtin=False)
    db.add(m)
    db.commit()
    audit.record(db, "shariah.methodology_create", request, user.id, entity="methodology", entity_id=str(m.id),
                 details={"from": src.code})
    return svc.methodology_dict(m, user)


@router.put("/shariah/methodologies/{mid}")
def update_methodology(request: Request, mid: int, body: MethodologyIn, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    m = _own(db, user, mid)
    errors = engine.validate_methodology(body.thresholds, body.denominator, body.prohibited_activities,
                                         body.max_data_age_days)
    if errors:
        raise HTTPException(422, "; ".join(errors))
    before = svc.methodology_dict(m, user)
    m.name, m.description = body.name.strip(), body.description.strip()
    m.thresholds, m.denominator = dict(body.thresholds), body.denominator
    m.prohibited_activities = sorted(set(body.prohibited_activities))
    m.max_data_age_days = body.max_data_age_days
    db.commit()
    audit.record(db, "shariah.methodology_update", request, user.id, entity="methodology", entity_id=str(m.id),
                 details={"before": {k: before[k] for k in ("thresholds", "denominator", "prohibited_activities",
                                                            "max_data_age_days")},
                          "after": body.model_dump(exclude={"description"})})
    return svc.methodology_dict(m, user)


@router.delete("/shariah/methodologies/{mid}")
def delete_methodology(request: Request, mid: int, user: User = Depends(current_user),
                       db: Session = Depends(get_db)):
    m = _own(db, user, mid)
    if user.shariah_methodology_id == m.id:
        user.shariah_methodology_id = None
    db.execute(delete(ShariahScreen).where(ShariahScreen.methodology_id == m.id))
    db.delete(m)
    db.commit()
    audit.record(db, "shariah.methodology_delete", request, user.id, entity="methodology", entity_id=str(mid))
    return {"deleted": mid}


class DefaultIn(BaseModel):
    methodology_id: int


@router.put("/shariah/default")
def set_default(request: Request, body: DefaultIn, user: User = Depends(current_user),
                db: Session = Depends(get_db)):
    m = db.get(ShariahMethodology, body.methodology_id)
    if not svc.accessible(m, user):
        raise HTTPException(404, "Methodology not found")
    user.shariah_methodology_id = m.id
    db.commit()
    audit.record(db, "shariah.default_set", request, user.id, entity="methodology", entity_id=str(m.id))
    return {"default": m.id}


# ---------- per-stock results ----------


@router.get("/stocks/{mic}/{ticker}/shariah")
def stock_shariah(mic: str, ticker: str, methodology_id: int | None = None, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    m = svc.resolve_methodology(db, user, methodology_id)
    if m is None:
        raise HTTPException(404, "Methodology not found")
    result = svc.run(db, s, m)
    return {
        "ticker": s.ticker, "exchange": s.exchange.code, "currency": s.currency or s.exchange.currency,
        "result": result,
        "activities": s.activity_tags or [],
        "external": s.shariah_external or [],
        "review_note": s.shariah_review_note,
        "fundamentals": [svc.fundamentals_dict(db, f) for f in svc.all_fundamentals(db, s.id)],
        "history": svc.history(db, s, user),
        "methodologies": [{"id": x.id, "name": x.name} for x in svc.visible_methodologies(db, user)],
        "disclaimer": "Screening methodologies differ. Verify compliance with a qualified Shariah scholar or a "
                      "recognised screening provider before investing.",
    }


class ActivityIn(BaseModel):
    tag: str
    label: str | None = Field(None, max_length=160)
    primary: bool = False
    revenue_share: float | None = Field(None, ge=0, le=1)
    source: str | None = Field(None, max_length=300)
    as_of: date | None = None

    @field_validator("tag")
    @classmethod
    def _tag(cls, v):
        if v not in engine.ACTIVITY_LABELS:
            raise ValueError("Unknown activity tag")
        return v


class ActivitiesIn(BaseModel):
    activities: list[ActivityIn] = Field(max_length=20)


@router.put("/stocks/{mic}/{ticker}/activities")
def put_activities(request: Request, mic: str, ticker: str, body: ActivitiesIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    before = s.activity_tags
    s.activity_tags = [a.model_dump(mode="json") for a in body.activities]
    db.commit()
    audit.record(db, "shariah.activities_update", request, user.id, entity="stock", entity_id=_sid(s),
                 details={"before": before, "after": s.activity_tags})
    return {"activities": s.activity_tags}


class FundamentalsIn(BaseModel):
    period_end: date
    period_type: str = Field(pattern="^(Q|H|A|TTM)$")
    currency: str = Field(pattern="^[A-Z]{3}$")
    source_ref: str = Field(min_length=3, max_length=500)
    reported_at: date | None = None
    is_estimate: bool = False
    note: str | None = Field(None, max_length=1000)
    revenue: float | None = Field(None, ge=0)
    net_income: float | None = None
    total_debt: float | None = Field(None, ge=0)
    interest_bearing_debt: float | None = Field(None, ge=0)
    cash: float | None = Field(None, ge=0)
    interest_bearing_securities: float | None = Field(None, ge=0)
    receivables: float | None = Field(None, ge=0)
    total_assets: float | None = Field(None, ge=0)
    total_equity: float | None = None
    interest_income: float | None = Field(None, ge=0)
    non_permissible_income: float | None = Field(None, ge=0)
    market_cap: float | None = Field(None, ge=0)
    shares_outstanding: float | None = Field(None, ge=0)
    dividend_per_share: float | None = Field(None, ge=0)

    @field_validator("period_end", "reported_at")
    @classmethod
    def _not_future(cls, v):
        if v is not None and v > datetime.now(UTC).date():
            raise ValueError("Date cannot be in the future")
        return v


def _manual_source(db: Session) -> DataSource:
    src = db.scalar(select(DataSource).where(DataSource.code == "manual_fund"))
    if src is None:
        raise HTTPException(500, "Manual fundamentals source missing; restart to re-seed reference data")
    return src


@router.post("/stocks/{mic}/{ticker}/fundamentals", status_code=201)
def add_fundamentals(request: Request, mic: str, ticker: str, body: FundamentalsIn,
                     user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    if body.reported_at and body.reported_at < body.period_end:
        raise HTTPException(422, "The report date cannot be before the period end")
    src = _manual_source(db)
    f = db.scalar(select(Fundamentals).where(Fundamentals.stock_id == s.id, Fundamentals.period_end == body.period_end,
                                             Fundamentals.period_type == body.period_type,
                                             Fundamentals.source_id == src.id))
    created = f is None
    if created:
        f = Fundamentals(stock_id=s.id, period_end=body.period_end, period_type=body.period_type, source_id=src.id)
        db.add(f)
    data = body.model_dump()
    for k in engine.FUNDAMENTAL_FIELDS:
        setattr(f, k, data[k])
    f.currency, f.source_ref, f.note, f.is_estimate = body.currency, body.source_ref.strip(), body.note, \
        body.is_estimate
    f.reported_at = datetime.combine(body.reported_at, datetime.min.time(), UTC) if body.reported_at else None
    f.entered_by_user_id = user.id
    f.ingested_at = datetime.now(UTC)
    db.commit()
    audit.record(db, "shariah.fundamentals_" + ("create" if created else "update"), request, user.id,
                 entity="stock", entity_id=_sid(s), details=body.model_dump(mode="json"))
    return svc.fundamentals_dict(db, f)


@router.delete("/stocks/{mic}/{ticker}/fundamentals/{fid}")
def delete_fundamentals(request: Request, mic: str, ticker: str, fid: int, user: User = Depends(current_user),
                        db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    f = db.get(Fundamentals, fid)
    if f is None or f.stock_id != s.id:
        raise HTTPException(404, "Fundamentals entry not found")
    if f.source_id != _manual_source(db).id:
        raise HTTPException(403, "Only manually entered figures can be deleted")
    snapshot = svc.fundamentals_dict(db, f)
    db.delete(f)
    db.commit()
    audit.record(db, "shariah.fundamentals_delete", request, user.id, entity="stock", entity_id=_sid(s),
                 details={k: (v.isoformat() if isinstance(v, date) else v) for k, v in snapshot.items()})
    return {"deleted": fid}


class ReviewIn(BaseModel):
    note: str | None = Field(None, max_length=1000)


@router.put("/stocks/{mic}/{ticker}/shariah-review")
def put_review(request: Request, mic: str, ticker: str, body: ReviewIn, user: User = Depends(current_user),
               db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    s.shariah_review_note = (body.note or "").strip() or None
    db.commit()
    audit.record(db, "shariah.review_" + ("set" if s.shariah_review_note else "clear"), request, user.id,
                 entity="stock", entity_id=_sid(s), details={"note": s.shariah_review_note})
    return {"review_note": s.shariah_review_note}


class ExternalIn(BaseModel):
    source: str = Field(min_length=2, max_length=160)
    status: str = Field(pattern="^(COMPLIANT|NON_COMPLIANT|QUESTIONABLE)$")
    as_of: date
    url: str | None = Field(None, max_length=500, pattern=r"^https://\S+$")
    note: str | None = Field(None, max_length=500)


class ExternalListIn(BaseModel):
    items: list[ExternalIn] = Field(max_length=10)


@router.put("/stocks/{mic}/{ticker}/shariah-external")
def put_external(request: Request, mic: str, ticker: str, body: ExternalListIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    s.shariah_external = [x.model_dump(mode="json") for x in body.items]
    db.commit()
    audit.record(db, "shariah.external_update", request, user.id, entity="stock", entity_id=_sid(s),
                 details={"items": s.shariah_external})
    return {"external": s.shariah_external}


# ---------- screener ----------


@router.get("/shariah/screener")
def screener(market: str = Query("NG", max_length=8), status: str = Query("", max_length=120),
             methodology_id: int | None = None, include_unscreened: bool = False,
             user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Screens every stock in the market on stored inputs. It never calls a data provider."""
    m = svc.resolve_methodology(db, user, methodology_id)
    if m is None:
        raise HTTPException(404, "Methodology not found")
    wanted = {x for x in status.split(",") if x}
    if wanted - set(STATUSES):
        raise HTTPException(422, "Unknown status filter")
    q = (select(Stock).join(Exchange).join(Market).options(joinedload(Stock.exchange).joinedload(Exchange.market))
         .where(Stock.is_active.is_(True), Stock.instrument_type != "index"))
    if market != "GLOBAL":
        q = q.where(Market.code == market)
    stocks = db.scalars(q.order_by(Stock.ticker)).unique().all()
    counts = dict.fromkeys(STATUSES, 0)
    rows = []
    with_inputs = svc.stocks_with_inputs(db)
    for s in stocks:
        if s.id not in with_inputs:
            counts["NOT_SCREENED"] += 1
            if include_unscreened and (not wanted or "NOT_SCREENED" in wanted):
                rows.append({"ticker": s.ticker, "name": s.name, "exchange": s.exchange.code,
                             "status": "NOT_SCREENED", "primary": None, "ratios": {}, "period_end": None,
                             "fresh": None, "first_reason": "No activities or fundamentals entered"})
            continue
        r = svc.run(db, s, m, persist=False)
        counts[r["status"]] += 1
        if wanted and r["status"] not in wanted:
            continue
        primary = next((a for a in (s.activity_tags or []) if a.get("primary")), None)
        rows.append({
            "ticker": s.ticker, "name": s.name, "exchange": s.exchange.code, "status": r["status"],
            "primary": (primary.get("label") or engine.ACTIVITY_LABELS.get(primary["tag"])) if primary else None,
            "ratios": {x["id"]: {"value": x["value"], "threshold": x["threshold"], "result": x["result"]}
                       for x in r["ratios"]},
            "period_end": (r["data"] or {}).get("period_end"), "fresh": (r["data"] or {}).get("fresh"),
            "first_reason": r["reasons"][0] if r["reasons"] else None,
        })
    return {"methodology": svc.methodology_dict(m, user), "market": market, "total": len(stocks),
            "counts": counts, "results": rows,
            "note": "Results use the fundamentals and activity tags stored in the platform. Stocks with nothing "
                    "entered are NOT SCREENED, never assumed compliant."}
