"""Glue between stored fundamentals, activity tags and the pure Shariah engine. No provider calls."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from app.engines import shariah as engine
from app.models.entities import (
    DataSource,
    Fundamentals,
    PriceHistory,
    ShariahMethodology,
    ShariahScreen,
    ShariahStatus,
    Stock,
    User,
)

DEFAULT_CODE = "aaoifi_based"
PERIOD_RANK = {"A": 0, "TTM": 1, "H": 2, "Q": 3}  # tie-break for the same period end


def methodology_dict(m: ShariahMethodology, user: User | None = None) -> dict:
    return {"id": m.id, "code": m.code, "name": m.name, "description": m.description, "thresholds": m.thresholds,
            "prohibited_activities": m.prohibited_activities, "denominator": m.denominator,
            "max_data_age_days": m.max_data_age_days, "is_builtin": m.is_builtin,
            "owned": user is not None and m.owner_user_id == user.id}


def visible_methodologies(db: Session, user: User) -> list[ShariahMethodology]:
    return list(db.scalars(select(ShariahMethodology).where(
        or_(ShariahMethodology.is_builtin.is_(True), ShariahMethodology.owner_user_id == user.id))
        .order_by(ShariahMethodology.is_builtin.desc(), ShariahMethodology.id)))


def accessible(m: ShariahMethodology | None, user: User | None) -> bool:
    return m is not None and (m.is_builtin or (user is not None and m.owner_user_id == user.id))


def builtin_default(db: Session) -> ShariahMethodology:
    m = db.scalar(select(ShariahMethodology).where(ShariahMethodology.code == DEFAULT_CODE))
    if m is None:
        m = db.scalar(select(ShariahMethodology).where(ShariahMethodology.is_builtin.is_(True)))
    return m


def user_methodology(db: Session, user: User | None) -> ShariahMethodology:
    if user is not None and user.shariah_methodology_id:
        m = db.get(ShariahMethodology, user.shariah_methodology_id)
        if accessible(m, user):
            return m
    return builtin_default(db)


def resolve_methodology(db: Session, user: User | None, methodology_id: int | None) -> ShariahMethodology | None:
    if methodology_id is None:
        return user_methodology(db, user)
    m = db.get(ShariahMethodology, methodology_id)
    return m if accessible(m, user) else None


# ---------- inputs ----------


def _d(v) -> date | None:
    if v is None:
        return None
    return v.date() if isinstance(v, datetime) else v


def available_on(f: Fundamentals) -> date | None:
    """Date from which the figures were public (point in time), or entered when the report date is unknown."""
    return _d(f.reported_at) or _d(f.ingested_at)


def all_fundamentals(db: Session, stock_id: int) -> list[Fundamentals]:
    rows = db.scalars(select(Fundamentals).where(Fundamentals.stock_id == stock_id)).all()
    return sorted(rows, key=lambda f: (f.period_end, -PERIOD_RANK.get(f.period_type, 9),
                                       f.ingested_at.timestamp() if f.ingested_at else 0, f.id), reverse=True)


def pick_fundamentals(db: Session, stock_id: int, as_of: date) -> Fundamentals | None:
    for f in all_fundamentals(db, stock_id):
        avail = available_on(f)
        if f.period_end <= as_of and (avail is None or avail <= as_of):
            return f
    return None


def fundamentals_dict(db: Session, f: Fundamentals) -> dict:
    src = db.get(DataSource, f.source_id)
    out = {k: (None if getattr(f, k) is None else float(getattr(f, k))) for k in engine.FUNDAMENTAL_FIELDS}
    out.update({"id": f.id, "period_end": f.period_end, "period_type": f.period_type, "currency": f.currency,
                "source": src.name if src else None, "source_code": src.code if src else None,
                "source_ref": f.source_ref, "note": f.note, "is_estimate": f.is_estimate,
                "reported_at": _d(f.reported_at).isoformat() if f.reported_at else None,
                "entered_at": f.ingested_at.isoformat() if f.ingested_at else None})
    return out


def _close_on_or_before(db: Session, stock_id: int, day: date) -> PriceHistory | None:
    end = datetime.combine(day, datetime.max.time(), UTC)
    return db.scalar(select(PriceHistory).where(PriceHistory.stock_id == stock_id, PriceHistory.interval == "1d",
                                                PriceHistory.ts <= end).order_by(PriceHistory.ts.desc()).limit(1))


def denominator(db: Session, stock: Stock, f: dict | None, key: str, as_of: date) -> dict:
    if f is None:
        return {"value": None, "reason": "no fundamentals stored"}
    if key == "total_assets":
        v = f.get("total_assets")
        return {"value": v, "method": f"Total assets, period ending {f['period_end']:%d %b %Y}",
                "as_of": f["period_end"].isoformat(), "reason": None if v else "total assets not entered"}
    shares = f.get("shares_outstanding")
    if key == "market_cap":
        if f.get("market_cap"):
            return {"value": f["market_cap"], "as_of": f["period_end"].isoformat(),
                    "method": f"Market capitalisation as reported for {f['period_end']:%d %b %Y}"}
        if not shares:
            return {"value": None, "reason": "enter shares outstanding or market capitalisation"}
        bar = _close_on_or_before(db, stock.id, as_of)
        if bar is None:
            return {"value": None, "reason": "no stored closing price to value the shares"}
        day = bar.ts.date()
        return {"value": bar.close * shares, "as_of": day.isoformat(),
                "method": f"Close of {day:%d %b %Y} ({bar.close:,.2f}) × {shares:,.0f} shares outstanding"}
    if key == "avg_market_cap_36m":
        if not shares:
            return {"value": None, "reason": "enter shares outstanding"}
        start = datetime.combine(as_of - timedelta(days=36 * 31), datetime.min.time(), UTC)
        end = datetime.combine(as_of, datetime.max.time(), UTC)
        rows = db.execute(select(PriceHistory.ts, PriceHistory.close).where(
            PriceHistory.stock_id == stock.id, PriceHistory.interval == "1d",
            PriceHistory.ts >= start, PriceHistory.ts <= end).order_by(PriceHistory.ts)).all()
        month_end: dict[tuple[int, int], float] = {}
        for ts, close in rows:
            month_end[(ts.year, ts.month)] = close
        months = sorted(month_end)[-36:]
        if len(months) < 36:
            return {"value": None, "reason": f"only {len(months)} months of stored prices; 36 are needed"}
        avg = sum(month_end[m] for m in months) / 36 * shares
        return {"value": avg, "as_of": as_of.isoformat(),
                "method": f"Average of 36 month-end closes × {shares:,.0f} shares (current share count assumed)"}
    return {"value": None, "reason": f"unknown denominator {key}"}


def _activities(stock: Stock) -> list[dict]:
    return list(stock.activity_tags or [])


def has_inputs(db: Session, stock: Stock) -> bool:
    return bool(stock.activity_tags or stock.shariah_review_note or stock.shariah_external
                or db.scalar(select(Fundamentals.id).where(Fundamentals.stock_id == stock.id).limit(1)))


def stocks_with_inputs(db: Session) -> set[int]:
    """Ids of stocks with anything entered for screening, in two queries (no per-stock round trips)."""
    ids = set(db.scalars(select(Fundamentals.stock_id).distinct()))
    for sid, tags, ext, note in db.execute(select(Stock.id, Stock.activity_tags, Stock.shariah_external,
                                                  Stock.shariah_review_note)):
        if tags or ext or note:
            ids.add(sid)
    return ids


def compliant_stock_ids(db: Session, user: User | None) -> set[int]:
    m = user_methodology(db, user)
    ids = stocks_with_inputs(db)
    stocks = db.scalars(select(Stock).where(Stock.id.in_(ids))).all() if ids else []
    return {s.id for s in stocks if run(db, s, m, persist=False)["status"] == "COMPLIANT"}


def run(db: Session, stock: Stock, m: ShariahMethodology, as_of: date | None = None,
        persist: bool = True) -> dict:
    as_of = as_of or datetime.now(UTC).date()
    f = pick_fundamentals(db, stock.id, as_of)
    fd = fundamentals_dict(db, f) if f else None
    den = {m.denominator: denominator(db, stock, fd, m.denominator, as_of)}
    meth = methodology_dict(m)
    result = engine.screen(fundamentals=fd, denominators=den, activities=_activities(stock), methodology=meth,
                           as_of=as_of, external=stock.shariah_external, review_note=stock.shariah_review_note)
    result["not_screened"] = not has_inputs(db, stock)
    if persist and not result["not_screened"]:
        stable = {k: v for k, v in result.items() if k not in ("as_of", "not_screened")}
        if stable.get("data"):
            stable["data"] = {k: v for k, v in stable["data"].items() if k != "age_days"}
        digest = hashlib.sha256(json.dumps(stable, sort_keys=True, default=str).encode()).hexdigest()[:32]
        last = db.scalar(select(ShariahScreen).where(ShariahScreen.stock_id == stock.id,
                                                     ShariahScreen.methodology_id == m.id)
                         .order_by(ShariahScreen.computed_at.desc(), ShariahScreen.id.desc()).limit(1))
        if last is None or last.inputs_digest != digest:
            last = ShariahScreen(stock_id=stock.id, methodology_id=m.id, status=ShariahStatus(result["status"]),
                                 business_result=result["business"], ratio_results=result["ratios"],
                                 fundamentals_id=f.id if f else None, data_as_of=f.period_end if f else None,
                                 reviewer_note=stock.shariah_review_note, details=result, inputs_digest=digest)
            db.add(last)
            db.commit()
        result["screen_id"] = last.id
        result["computed_at"] = last.computed_at
    return result


def status_for(db: Session, stock: Stock, m: ShariahMethodology) -> str:
    """Current status without writing a screen record; NOT_SCREENED when nothing has been entered."""
    if not has_inputs(db, stock):
        return "NOT_SCREENED"
    return run(db, stock, m, persist=False)["status"]


def history(db: Session, stock: Stock, user: User, limit: int = 20) -> list[dict]:
    rows = db.execute(select(ShariahScreen, ShariahMethodology).join(ShariahMethodology)
                      .where(ShariahScreen.stock_id == stock.id)
                      .where(or_(ShariahMethodology.is_builtin.is_(True),
                                 ShariahMethodology.owner_user_id == user.id))
                      .order_by(ShariahScreen.computed_at.desc(), ShariahScreen.id.desc()).limit(limit)).all()
    return [{"id": s.id, "status": s.status.value, "methodology": m.name, "computed_at": s.computed_at,
             "data_as_of": s.data_as_of} for s, m in rows]
