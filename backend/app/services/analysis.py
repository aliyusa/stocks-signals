"""Glue between stored data and the pure engines. Reads the database only: no provider calls."""

from __future__ import annotations

import hashlib
import json
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.engines import regime as regime_engine
from app.engines.signals import (
    DEFAULT_PARAMS,
    DEFAULT_WEIGHTS,
    SignalResult,
    agreement,
    compute,
    evaluate,
    weekly_trend,
)
from app.models.entities import (
    Exchange,
    Portfolio,
    PortfolioPosition,
    PriceHistory,
    Signal,
    SignalType,
    Stock,
    Strategy,
    User,
)
from app.services import shariah as shariah_svc
from app.services.prices import freshness

DEFAULT_STRATEGY = "Default setup score"
USER_STRATEGY = "My scoring weights"

# market code -> key in settings.index_symbols used for the regime
MARKET_INDEX = {"US": "SPX", "NG": "NGXASI"}

_cache: dict[tuple, tuple[dict, SignalResult]] = {}


def load_bars(db: Session, stock_id: int, interval: str = "1d") -> list[dict]:
    rows = db.scalars(select(PriceHistory).where(PriceHistory.stock_id == stock_id, PriceHistory.interval == interval)
                      .order_by(PriceHistory.ts)).all()
    return [{"t": r.ts.date(), "o": r.open, "h": r.high, "l": r.low, "c": r.close, "v": r.volume} for r in rows]


def default_strategy(db: Session) -> Strategy:
    s = db.scalar(select(Strategy).where(Strategy.is_builtin.is_(True), Strategy.name == DEFAULT_STRATEGY))
    if s is None:
        s = Strategy(name=DEFAULT_STRATEGY, description="Built-in transparent setup score (docs/ARCHITECTURE.md §3)",
                     rules={"type": "setup_score"}, weights=DEFAULT_WEIGHTS, is_builtin=True)
        db.add(s)
        db.commit()
    return s


def user_strategy(db: Session, user: User | None) -> Strategy:
    if user is not None:
        s = db.scalar(select(Strategy).where(Strategy.user_id == user.id, Strategy.name == USER_STRATEGY))
        if s is not None:
            return s
    return default_strategy(db)


def market_regime(db: Session, market: str) -> dict | None:
    key = MARKET_INDEX.get(market)
    sym = get_settings().index_symbols.get(key or "", "") if key else ""
    if not sym:
        return None
    ex = db.scalar(select(Exchange).where(Exchange.code == "INDX"))
    stock = db.scalar(select(Stock).where(Stock.exchange_id == ex.id, Stock.ticker == sym.split(".")[0].upper())) \
        if ex else None
    if stock is None:
        return None
    bars = load_bars(db, stock.id)
    if not bars:
        return None
    out = regime_engine.classify(bars)
    out["index"] = stock.name
    out["as_of"] = bars[-1]["t"].isoformat()
    return out


def shariah_status(db: Session, stock: Stock, user: User | None) -> str | None:
    """Current status under the user's chosen methodology; None when nothing has been entered yet."""
    st = shariah_svc.status_for(db, stock, shariah_svc.user_methodology(db, user))
    return None if st == "NOT_SCREENED" else st


def open_position(db: Session, stock: Stock, user: User | None) -> dict | None:
    """The user's open holding in a stock, combined across portfolios: summed quantity, weighted average
    entry, the highest stop (the first to be hit) and the lowest target. None when nothing is open."""
    if user is None:
        return None
    rows = db.scalars(select(PortfolioPosition).join(Portfolio).where(
        Portfolio.user_id == user.id, PortfolioPosition.stock_id == stock.id,
        PortfolioPosition.closed_at.is_(None))).all()
    if not rows:
        return None
    qty = sum(float(r.quantity) for r in rows)
    if qty <= 0:
        return None
    entry = sum(float(r.quantity) * float(r.avg_entry) for r in rows) / qty
    stops = [float(r.stop) for r in rows if r.stop is not None]
    targets = [float(r.target) for r in rows if r.target is not None]
    return {"quantity": qty, "avg_entry": entry, "stop": max(stops) if stops else None,
            "target": min(targets) if targets else None, "positions": len(rows)}


def analyze(db: Session, stock: Stock, user: User | None = None, persist: bool = True,
            regime_cache: dict | None = None) -> tuple[dict, SignalResult, Strategy] | None:
    bars = load_bars(db, stock.id)
    if len(bars) < 30:
        return None
    strat = user_strategy(db, user)
    market = stock.exchange.market.code
    if regime_cache is not None and market in regime_cache:
        rg = regime_cache[market]
    else:
        rg = market_regime(db, market)
        if regime_cache is not None:
            regime_cache[market] = rg
    sh = shariah_status(db, stock, user)
    pos = open_position(db, stock, user)
    status, note = freshness(stock, bars[-1]["t"])
    extra = [f"Price data is {status.value.replace('_', '-')}: {note}"] if status.value == "STALE" and note else []
    key = (stock.id, bars[-1]["t"], len(bars), json.dumps(strat.weights, sort_keys=True),
           (rg or {}).get("label"), sh, status.value, json.dumps(pos, sort_keys=True))
    if key in _cache:
        data, result = _cache[key]
    else:
        data = compute(bars)
        result = evaluate(data, weights=strat.weights, params=DEFAULT_PARAMS,
                          currency=stock.currency or stock.exchange.currency, market_regime=rg,
                          shariah_status=sh, extra_warnings=extra, position=pos)
        result.timeframes["weekly"] = weekly_trend(bars)
        result.timeframes["agreement"] = agreement(result.timeframes)
        result.snapshot["regime"] = rg
        if len(_cache) > 2000:
            _cache.clear()
        _cache[key] = (data, result)
    if persist:
        _persist(db, stock, strat, result)
    return data, result, strat


def _persist(db: Session, stock: Stock, strat: Strategy, r: SignalResult) -> Signal:
    ts = datetime.combine(r.as_of, datetime.min.time(), UTC)
    digest = hashlib.sha256(json.dumps(r.to_dict(), sort_keys=True, default=str).encode()).hexdigest()[:16]
    existing = db.scalar(select(Signal).where(Signal.stock_id == stock.id, Signal.strategy_id == strat.id,
                                              Signal.ts == ts).order_by(Signal.id.desc()).limit(1))
    if existing and existing.score_breakdown.get("_digest") == digest:
        return existing
    tg = [t.price for t in r.targets] + [None, None, None]
    sig = Signal(
        stock_id=stock.id, strategy_id=strat.id, interval="1d", ts=ts, signal_type=SignalType(r.signal_type),
        score=r.score, coverage=r.coverage, score_breakdown={**r.breakdown, "_digest": digest},
        reasons=r.reasons, warnings=r.warnings, entry_low=r.entry_low, entry_high=r.entry_high, stop=r.stop,
        target1=tg[0], target2=tg[1], target3=tg[2], risk_reward=r.risk_reward, data_as_of=ts,
    )
    db.add(sig)
    db.commit()
    return sig


def series_payload(data: dict, days: int | None) -> dict:
    """Indicator series for chart overlays, trimmed to the same window as the price chart."""
    n = len(data["c"])
    start = 0
    if days:
        last = data["t"][-1]
        start = next((k for k, t in enumerate(data["t"]) if (last - t).days <= days), 0)
    keys = ("sma20", "sma50", "sma200", "ema21", "bb_up", "bb_mid", "bb_lo", "rsi", "macd", "macd_signal", "macd_hist")
    out = {"t": [t.isoformat() for t in data["t"][start:n]]}
    for k in keys:
        out[k] = [None if v is None else round(v, 6) for v in data[k][start:n]]
    return out
