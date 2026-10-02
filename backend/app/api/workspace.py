"""Watchlists and manually entered portfolios. The platform never places trades."""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import UTC, date, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.stocks import MIC_PATTERN, TICKER_PATTERN, _get_stock
from app.core.db import get_db
from app.models.entities import (
    Alert,
    Portfolio,
    PortfolioPosition,
    Signal,
    Stock,
    User,
    Watchlist,
    WatchlistStock,
)
from app.services import audit
from app.services import shariah as shariah_svc
from app.services.analysis import analyze, user_strategy
from app.services.prices import quote

router = APIRouter(prefix="/api", tags=["workspace"])

MAX_WATCHLISTS, MAX_ITEMS, MAX_PORTFOLIOS, MAX_POSITIONS = 20, 200, 10, 300


class StockRef(BaseModel):
    exchange: str = Field(pattern=MIC_PATTERN)
    ticker: str = Field(pattern=TICKER_PATTERN)


def _stock(db: Session, ref: StockRef) -> Stock:
    return _get_stock(db, ref.exchange, ref.ticker)


def _stock_row(db: Session, s: Stock, user: User, meth) -> dict:
    strat = user_strategy(db, user)
    sig = db.scalar(select(Signal).where(Signal.stock_id == s.id, Signal.strategy_id == strat.id)
                    .order_by(Signal.id.desc()).limit(1))
    return {"ticker": s.ticker, "name": s.name, "exchange": s.exchange.code, "market": s.exchange.market.code,
            "currency": s.currency or s.exchange.currency, "sector": s.sector.name if s.sector else None,
            "quote": quote(db, s), "shariah": shariah_svc.status_for(db, s, meth),
            "signal": None if sig is None else {"type": sig.signal_type.value, "score": sig.score,
                                                "data_as_of": sig.data_as_of, "computed_at": sig.created_at}}


# ---------- watchlists ----------


def _own_list(db: Session, user: User, wid: int) -> Watchlist:
    w = db.get(Watchlist, wid)
    if w is None or w.user_id != user.id:
        raise HTTPException(404, "Watchlist not found")
    return w


@router.get("/watchlists")
def list_watchlists(user: User = Depends(current_user), db: Session = Depends(get_db)):
    meth = shariah_svc.user_methodology(db, user)
    lists = db.scalars(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.id)).all()
    out = []
    for w in lists:
        items = []
        for it in sorted(w.items, key=lambda x: x.added_at.timestamp() if x.added_at else 0):
            s = db.get(Stock, it.stock_id)
            if s is not None:
                items.append({**_stock_row(db, s, user, meth), "note": it.note, "added_at": it.added_at})
        out.append({"id": w.id, "name": w.name, "created_at": w.created_at, "items": items})
    return {"watchlists": out, "methodology": meth.name}


class NameIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)


@router.post("/watchlists", status_code=201)
def create_watchlist(request: Request, body: NameIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    n = db.scalar(select(func.count(Watchlist.id)).where(Watchlist.user_id == user.id)) or 0
    if n >= MAX_WATCHLISTS:
        raise HTTPException(409, f"You can keep up to {MAX_WATCHLISTS} watchlists")
    name = body.name.strip()
    if db.scalar(select(Watchlist).where(Watchlist.user_id == user.id, Watchlist.name == name)):
        raise HTTPException(409, "A watchlist with that name already exists")
    w = Watchlist(user_id=user.id, name=name)
    db.add(w)
    db.commit()
    audit.record(db, "watchlist.create", request, user.id, entity="watchlist", entity_id=str(w.id))
    return {"id": w.id, "name": w.name}


@router.put("/watchlists/{wid}")
def rename_watchlist(request: Request, wid: int, body: NameIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    w = _own_list(db, user, wid)
    w.name = body.name.strip()
    db.commit()
    return {"id": w.id, "name": w.name}


@router.delete("/watchlists/{wid}")
def delete_watchlist(request: Request, wid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _own_list(db, user, wid)
    db.delete(w)
    db.commit()
    audit.record(db, "watchlist.delete", request, user.id, entity="watchlist", entity_id=str(wid))
    return {"deleted": wid}


class ItemIn(StockRef):
    note: str | None = Field(None, max_length=500)


@router.post("/watchlists/{wid}/items", status_code=201)
def add_item(request: Request, wid: int, body: ItemIn, user: User = Depends(current_user),
             db: Session = Depends(get_db)):
    w = _own_list(db, user, wid)
    s = _stock(db, body)
    if len(w.items) >= MAX_ITEMS:
        raise HTTPException(409, f"A watchlist holds up to {MAX_ITEMS} stocks")
    it = db.get(WatchlistStock, (w.id, s.id))
    if it is None:
        db.add(WatchlistStock(watchlist_id=w.id, stock_id=s.id, note=body.note))
    else:
        it.note = body.note
    db.commit()
    return {"watchlist": w.id, "ticker": s.ticker}


@router.delete("/watchlists/{wid}/items/{mic}/{ticker}")
def remove_item(wid: int, mic: str, ticker: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    w = _own_list(db, user, wid)
    if not (re.fullmatch(MIC_PATTERN, mic) and re.fullmatch(TICKER_PATTERN, ticker)):
        raise HTTPException(422, "Invalid exchange or ticker")
    s = _get_stock(db, mic, ticker)
    it = db.get(WatchlistStock, (w.id, s.id))
    if it is not None:
        db.delete(it)
        db.commit()
    return {"removed": s.ticker}


@router.get("/stocks/{mic}/{ticker}/membership")
def membership(mic: str, ticker: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not (re.fullmatch(MIC_PATTERN, mic) and re.fullmatch(TICKER_PATTERN, ticker)):
        raise HTTPException(422, "Invalid exchange or ticker")
    s = _get_stock(db, mic, ticker)
    lists = db.scalars(select(Watchlist).where(Watchlist.user_id == user.id).order_by(Watchlist.id)).all()
    positions = db.scalar(select(func.count(PortfolioPosition.id)).join(Portfolio).where(
        Portfolio.user_id == user.id, PortfolioPosition.stock_id == s.id, PortfolioPosition.closed_at.is_(None))) or 0
    alerts = db.scalar(select(func.count(Alert.id)).where(Alert.user_id == user.id, Alert.stock_id == s.id)) or 0
    return {"watchlists": [{"id": w.id, "name": w.name, "contains": any(i.stock_id == s.id for i in w.items)}
                           for w in lists],
            "open_positions": positions, "alerts": alerts}


# ---------- portfolios ----------


def _own_portfolio(db: Session, user: User, pid: int) -> Portfolio:
    p = db.get(Portfolio, pid)
    if p is None or p.user_id != user.id:
        raise HTTPException(404, "Portfolio not found")
    return p


def _own_position(db: Session, user: User, pos_id: int) -> PortfolioPosition:
    pos = db.get(PortfolioPosition, pos_id)
    if pos is None or db.get(Portfolio, pos.portfolio_id).user_id != user.id:
        raise HTTPException(404, "Position not found")
    return pos


def _f(v):
    return None if v is None else float(v)


def _dist(level, price) -> float | None:
    return None if price is None or level is None else (float(level) / price - 1) * 100


def _position_row(db: Session, pos: PortfolioPosition, user: User, meth, signals: dict) -> dict:
    s = pos.stock
    q = quote(db, s)
    qty, entry = float(pos.quantity), float(pos.avg_entry)
    cost = qty * entry
    row = {"id": pos.id, "ticker": s.ticker, "name": s.name, "exchange": s.exchange.code,
           "market": s.exchange.market.code, "sector": s.sector.name if s.sector else None,
           "currency": s.currency or s.exchange.currency, "quantity": qty, "avg_entry": entry, "cost": cost,
           "stop": _f(pos.stop), "target": _f(pos.target), "opened_at": pos.opened_at, "note": pos.note,
           "closed_at": pos.closed_at, "exit_price": _f(pos.exit_price), "quote": q,
           "shariah": shariah_svc.status_for(db, s, meth)}
    if pos.closed_at is not None:
        ex = float(pos.exit_price)
        row.update({"value": qty * ex, "pl": (ex - entry) * qty, "pl_pct": (ex / entry - 1) * 100})
        return row
    price = q["price"]
    row.update({"value": None if price is None else qty * price,
                "pl": None if price is None else (price - entry) * qty,
                "pl_pct": None if price is None else (price / entry - 1) * 100,
                "to_stop_pct": _dist(pos.stop, price), "to_target_pct": _dist(pos.target, price)})
    if s.id not in signals:
        out = analyze(db, s, user)
        signals[s.id] = None if out is None else {
            "type": out[1].signal_type, "summary": out[1].summary, "as_of": out[1].as_of.isoformat(),
            "triggered": [x for x in out[1].exit_checks if x["triggered"]]}
    row["signal"] = signals[s.id]
    return row


def _portfolio_payload(db: Session, p: Portfolio, user: User, meth) -> dict:
    signals: dict = {}
    rows = [_position_row(db, x, user, meth, signals) for x in sorted(p.positions, key=lambda x: x.id)]
    open_rows = [r for r in rows if r["closed_at"] is None]
    closed = [r for r in rows if r["closed_at"] is not None]
    totals: dict[str, dict] = defaultdict(lambda: {"cost": 0.0, "value": 0.0, "unrealised": 0.0, "realised": 0.0,
                                                   "priced": 0, "unpriced": 0})
    exposure: dict[str, dict] = defaultdict(lambda: {"sector": defaultdict(float), "market": defaultdict(float)})
    for r in open_rows:
        t = totals[r["currency"]]
        if r["value"] is None:
            t["unpriced"] += 1
            continue
        t["priced"] += 1
        t["cost"] += r["cost"]
        t["value"] += r["value"]
        t["unrealised"] += r["pl"]
        exposure[r["currency"]]["sector"][r["sector"] or "Unclassified"] += r["value"]
        exposure[r["currency"]]["market"][r["market"]] += r["value"]
    for r in closed:
        totals[r["currency"]]["realised"] += r["pl"]
    exp_out = {}
    for cur, e in exposure.items():
        total = totals[cur]["value"] or 1
        exp_out[cur] = {k: sorted(({"name": n, "value": v, "share": v / total} for n, v in d.items()),
                                  key=lambda x: -x["value"]) for k, d in e.items()}
    warnings = []
    if len(totals) > 1 or any(c != p.base_currency for c in totals):
        warnings.append("Totals are shown per currency. No FX rates are connected, so nothing is converted to "
                        f"{p.base_currency}.")
    if any(r["shariah"] == "NON_COMPLIANT" for r in open_rows):
        warnings.append("At least one holding is NON-COMPLIANT under your methodology.")
    if any(r["value"] is None for r in open_rows):
        warnings.append("Some holdings have no stored price; their value and P/L are not counted.")
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency, "created_at": p.created_at,
            "open": open_rows, "closed": closed, "totals": dict(totals), "exposure": exp_out, "warnings": warnings}


@router.get("/portfolios")
def list_portfolios(user: User = Depends(current_user), db: Session = Depends(get_db)):
    meth = shariah_svc.user_methodology(db, user)
    ps = db.scalars(select(Portfolio).where(Portfolio.user_id == user.id).order_by(Portfolio.id)).all()
    return {"portfolios": [_portfolio_payload(db, p, user, meth) for p in ps], "methodology": meth.name,
            "note": "Positions are entered by you. Values use the latest stored close; nothing is executed."}


class PortfolioIn(BaseModel):
    name: str = Field(min_length=1, max_length=80)
    base_currency: str = Field("NGN", pattern="^[A-Z]{3}$")


@router.post("/portfolios", status_code=201)
def create_portfolio(request: Request, body: PortfolioIn, user: User = Depends(current_user),
                     db: Session = Depends(get_db)):
    n = db.scalar(select(func.count(Portfolio.id)).where(Portfolio.user_id == user.id)) or 0
    if n >= MAX_PORTFOLIOS:
        raise HTTPException(409, f"You can keep up to {MAX_PORTFOLIOS} portfolios")
    p = Portfolio(user_id=user.id, name=body.name.strip(), base_currency=body.base_currency)
    db.add(p)
    db.commit()
    audit.record(db, "portfolio.create", request, user.id, entity="portfolio", entity_id=str(p.id))
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency}


@router.put("/portfolios/{pid}")
def update_portfolio(pid: int, body: PortfolioIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _own_portfolio(db, user, pid)
    p.name, p.base_currency = body.name.strip(), body.base_currency
    db.commit()
    return {"id": p.id, "name": p.name, "base_currency": p.base_currency}


@router.delete("/portfolios/{pid}")
def delete_portfolio(request: Request, pid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    p = _own_portfolio(db, user, pid)
    n = len(p.positions)
    db.delete(p)
    db.commit()
    audit.record(db, "portfolio.delete", request, user.id, entity="portfolio", entity_id=str(pid),
                 details={"positions_deleted": n})
    return {"deleted": pid}


class PositionIn(StockRef):
    quantity: float = Field(gt=0)
    avg_entry: float = Field(gt=0)
    stop: float | None = Field(None, gt=0)
    target: float | None = Field(None, gt=0)
    opened_at: date | None = None
    note: str | None = Field(None, max_length=500)

    @field_validator("opened_at")
    @classmethod
    def _past(cls, v):
        if v is not None and v > datetime.now(UTC).date():
            raise ValueError("Date cannot be in the future")
        return v


class PositionEdit(BaseModel):
    quantity: float = Field(gt=0)
    avg_entry: float = Field(gt=0)
    stop: float | None = Field(None, gt=0)
    target: float | None = Field(None, gt=0)
    opened_at: date | None = None
    note: str | None = Field(None, max_length=500)


def _check_levels(entry: float, stop: float | None, target: float | None) -> None:
    if target is not None and stop is not None and stop >= target:
        raise HTTPException(422, "The stop must be below the target")


@router.post("/portfolios/{pid}/positions", status_code=201)
def add_position(request: Request, pid: int, body: PositionIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    p = _own_portfolio(db, user, pid)
    s = _stock(db, body)
    if len(p.positions) >= MAX_POSITIONS:
        raise HTTPException(409, f"A portfolio holds up to {MAX_POSITIONS} positions")
    _check_levels(body.avg_entry, body.stop, body.target)
    pos = PortfolioPosition(portfolio_id=p.id, stock_id=s.id, quantity=body.quantity, avg_entry=body.avg_entry,
                            stop=body.stop, target=body.target, opened_at=body.opened_at, note=body.note)
    db.add(pos)
    db.commit()
    audit.record(db, "position.create", request, user.id, entity="position", entity_id=str(pos.id),
                 details=body.model_dump(mode="json"))
    return {"id": pos.id}


@router.put("/positions/{pos_id}")
def edit_position(request: Request, pos_id: int, body: PositionEdit, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    pos = _own_position(db, user, pos_id)
    _check_levels(body.avg_entry, body.stop, body.target)
    for k, v in body.model_dump().items():
        setattr(pos, k, v)
    db.commit()
    audit.record(db, "position.update", request, user.id, entity="position", entity_id=str(pos.id),
                 details=body.model_dump(mode="json"))
    return {"id": pos.id}


class CloseIn(BaseModel):
    exit_price: float = Field(gt=0)
    closed_at: date


@router.post("/positions/{pos_id}/close")
def close_position(request: Request, pos_id: int, body: CloseIn, user: User = Depends(current_user),
                   db: Session = Depends(get_db)):
    pos = _own_position(db, user, pos_id)
    if pos.closed_at is not None:
        raise HTTPException(409, "Position already closed")
    if body.closed_at > datetime.now(UTC).date() or (pos.opened_at and body.closed_at < pos.opened_at):
        raise HTTPException(422, "The close date must be between the open date and today")
    pos.closed_at, pos.exit_price = body.closed_at, body.exit_price
    db.commit()
    audit.record(db, "position.close", request, user.id, entity="position", entity_id=str(pos.id),
                 details=body.model_dump(mode="json"))
    return {"id": pos.id, "closed_at": pos.closed_at}


@router.delete("/positions/{pos_id}")
def delete_position(request: Request, pos_id: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    pos = _own_position(db, user, pos_id)
    db.delete(pos)
    db.commit()
    audit.record(db, "position.delete", request, user.id, entity="position", entity_id=str(pos_id))
    return {"deleted": pos_id}
