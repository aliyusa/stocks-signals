import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from app.api.deps import current_user
from app.core.db import get_db
from app.engines.signals import CATEGORY_LABELS, DEFAULT_PARAMS, DEFAULT_WEIGHTS
from app.models.entities import Exchange, Market, PriceHistory, Signal, SignalType, Stock, Strategy, User
from app.services import audit
from app.services.analysis import USER_STRATEGY, analyze, series_payload, user_strategy
from app.services.prices import RANGES

router = APIRouter(prefix="/api", tags=["analysis"])


def _stock(db: Session, mic: str, ticker: str) -> Stock:
    if not (re.fullmatch(r"[A-Z]{4}", mic) and re.fullmatch(r"[A-Za-z0-9.\-_]{1,24}", ticker)):
        raise HTTPException(422, "Invalid exchange or ticker")
    s = db.scalar(select(Stock).join(Exchange).where(Exchange.code == mic, Stock.ticker == ticker.upper()))
    if s is None:
        raise HTTPException(404, "Stock not in the local universe")
    return s


@router.get("/stocks/{mic}/{ticker}/analysis")
def stock_analysis(mic: str, ticker: str, range: str = Query("1Y", pattern="^(1M|3M|6M|1Y|5Y|MAX)$"),
                   user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _stock(db, mic, ticker)
    out = analyze(db, s, user)
    if out is None:
        return {"available": False, "reason": "At least 30 daily bars are needed for analysis."}
    data, result, strat = out
    return {"available": True, "strategy": strat.name, "signal": result.to_dict(),
            "series": series_payload(data, RANGES.get(range))}


@router.get("/signals")
def list_signals(market: str | None = Query(None, max_length=8), type: str | None = Query(None, max_length=16),
                 limit: int = Query(100, ge=1, le=500), user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    strat = user_strategy(db, user)
    latest = (select(Signal.stock_id, func.max(Signal.id).label("mx"))
              .where(Signal.strategy_id == strat.id).group_by(Signal.stock_id).subquery())
    q = (select(Signal).join(latest, Signal.id == latest.c.mx).join(Stock).join(Exchange).join(Market)
         .options(joinedload(Signal.stock).joinedload(Stock.exchange)))
    if market and market != "GLOBAL":
        q = q.where(Market.code == market)
    if type:
        try:
            q = q.where(Signal.signal_type == SignalType(type))
        except ValueError:
            raise HTTPException(422, "Unknown signal type") from None
    rows = db.scalars(q.order_by(Signal.score.desc().nullslast()).limit(limit)).unique().all()
    return {"strategy": strat.name, "results": [_sig_row(r) for r in rows]}


def _sig_row(r: Signal) -> dict:
    return {"ticker": r.stock.ticker, "name": r.stock.name, "exchange": r.stock.exchange.code,
            "currency": r.stock.currency or r.stock.exchange.currency, "signal": r.signal_type.value,
            "score": r.score, "coverage": r.coverage, "entry_low": r.entry_low, "entry_high": r.entry_high,
            "stop": r.stop, "target1": r.target1, "risk_reward": r.risk_reward, "data_as_of": r.data_as_of,
            "created_at": r.created_at, "warnings": r.warnings[:3]}


class ScanIn(BaseModel):
    market: str = Field("GLOBAL", max_length=8)
    signal_types: list[str] = []
    min_score: float | None = Field(None, ge=0, le=100)
    rsi_min: float | None = Field(None, ge=0, le=100)
    rsi_max: float | None = Field(None, ge=0, le=100)
    price_min: float | None = Field(None, ge=0)
    price_max: float | None = Field(None, ge=0)
    above_sma50: bool = False
    above_sma200: bool = False
    sma50_gt_sma200: bool = False
    macd_positive: bool = False
    volume_above_avg: bool = False
    volume_spike: bool = False  # at least 2x the 20-day average
    breakout: bool = False
    near_52w_high: bool = False  # within 5 %
    max_atr_pct: float | None = Field(None, ge=0)
    exclude_illiquid: bool = True
    shariah: list[str] = []  # empty = any status, including not yet screened

    @field_validator("signal_types")
    @classmethod
    def _types(cls, v):
        for x in v:
            SignalType(x)
        return v


@router.post("/scanner")
def scan(request: Request, body: ScanIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Runs only on stored bars; it never calls a data provider."""
    q = (select(Stock).join(Exchange).join(Market).options(joinedload(Stock.exchange).joinedload(Exchange.market))
         .where(Stock.is_active.is_(True), Stock.instrument_type != "index")
         .where(Stock.id.in_(select(PriceHistory.stock_id).distinct())))
    if body.market != "GLOBAL":
        q = q.where(Market.code == body.market)
    stocks = db.scalars(q).unique().all()
    regime_cache: dict = {}
    matches, skipped = [], 0
    for s in stocks:
        out = analyze(db, s, user, regime_cache=regime_cache)
        if out is None:
            skipped += 1
            continue
        _, r, _ = out
        sn = r.snapshot
        reasons = []

        def check(cond, label, reasons=reasons):
            if cond:
                reasons.append(label)
            return cond

        ok = True
        ok &= not body.signal_types or r.signal_type in body.signal_types
        ok &= body.min_score is None or (r.score is not None and r.score >= body.min_score)
        ok &= body.rsi_min is None or (sn["rsi"] is not None and sn["rsi"] >= body.rsi_min)
        ok &= body.rsi_max is None or (sn["rsi"] is not None and sn["rsi"] <= body.rsi_max)
        ok &= body.price_min is None or sn["close"] >= body.price_min
        ok &= body.price_max is None or sn["close"] <= body.price_max
        ok &= not body.above_sma50 or check(sn["sma50"] is not None and sn["close"] > sn["sma50"], "above SMA50")
        ok &= not body.above_sma200 or check(sn["sma200"] is not None and sn["close"] > sn["sma200"], "above SMA200")
        ok &= not body.sma50_gt_sma200 or check(sn["sma50"] is not None and sn["sma200"] is not None
                                                 and sn["sma50"] > sn["sma200"], "SMA50 > SMA200")
        ok &= not body.macd_positive or check(sn["macd"] is not None and sn["macd_signal"] is not None
                                               and sn["macd"] > sn["macd_signal"], "MACD > signal")
        ok &= not body.volume_above_avg or check((sn["volume_ratio"] or 0) > 1, "volume above average")
        ok &= not body.volume_spike or check((sn["volume_ratio"] or 0) >= 2, "volume spike")
        ok &= not body.breakout or check(bool(sn["breakout"]), "20-day breakout")
        ok &= not body.near_52w_high or check(sn["high_52w"] and sn["close"] >= 0.95 * sn["high_52w"], "near 52w high")
        ok &= body.max_atr_pct is None or (sn["atr_pct"] is not None and sn["atr_pct"] <= body.max_atr_pct)
        ok &= not body.exclude_illiquid or not (r.signal_type == "AVOID"
                                                and any("Liquidity" in x for x in r.reasons))
        sh = next((w for w in r.warnings if w.startswith("Shariah")), None)
        shariah = "NOT_SCREENED" if sh else None
        ok &= not body.shariah or (shariah or "NOT_SCREENED") in body.shariah
        if not ok:
            continue
        matches.append({
            "ticker": s.ticker, "name": s.name, "exchange": s.exchange.code, "market": s.exchange.market.code,
            "currency": s.currency or s.exchange.currency, "close": sn["close"], "as_of": r.as_of.isoformat(),
            "signal": r.signal_type, "score": r.score, "coverage": r.coverage, "rsi": sn["rsi"],
            "trend": r.timeframes.get("daily"), "volume_ratio": sn["volume_ratio"], "risk_reward": r.risk_reward,
            "shariah": shariah or "NOT_SCREENED", "matched": reasons,
        })
    matches.sort(key=lambda m: (m["score"] is None, -(m["score"] or 0)))
    audit.record(db, "scanner.run", request, user.id, details={"filters": body.model_dump(), "matches": len(matches)})
    return {"scanned": len(stocks), "skipped_short_history": skipped, "results": matches,
            "note": "Only stocks with stored price history are scanned. Open a stock or refresh it to add history."}


class WeightsIn(BaseModel):
    weights: dict[str, float]

    @field_validator("weights")
    @classmethod
    def _valid(cls, v):
        unknown = set(v) - set(DEFAULT_WEIGHTS)
        if unknown:
            raise ValueError(f"Unknown categories: {', '.join(sorted(unknown))}")
        if any(x < 0 or x > 100 for x in v.values()):
            raise ValueError("Each weight must be between 0 and 100")
        if sum(v.values()) <= 0:
            raise ValueError("At least one weight must be positive")
        return v


@router.get("/scoring")
def get_scoring(user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = user_strategy(db, user)
    return {"strategy": s.name, "custom": not s.is_builtin, "weights": {**DEFAULT_WEIGHTS, **s.weights},
            "defaults": DEFAULT_WEIGHTS, "labels": CATEGORY_LABELS,
            "params": {k: v for k, v in DEFAULT_PARAMS.items() if k != "min_traded_value"},
            "liquidity_thresholds": DEFAULT_PARAMS["min_traded_value"]}


@router.put("/scoring")
def put_scoring(request: Request, body: WeightsIn, user: User = Depends(current_user), db: Session = Depends(get_db)):
    weights = {**DEFAULT_WEIGHTS, **body.weights}
    s = db.scalar(select(Strategy).where(Strategy.user_id == user.id, Strategy.name == USER_STRATEGY))
    if s is None:
        s = Strategy(user_id=user.id, name=USER_STRATEGY, description="User-defined category weights",
                     rules={"type": "setup_score"}, weights=weights)
        db.add(s)
    else:
        s.weights = weights
    db.commit()
    audit.record(db, "scoring.update", request, user.id, details={"weights": weights})
    return {"strategy": s.name, "weights": weights}


@router.delete("/scoring")
def reset_scoring(request: Request, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = db.scalar(select(Strategy).where(Strategy.user_id == user.id, Strategy.name == USER_STRATEGY))
    if s is not None:
        db.delete(s)
        db.commit()
    audit.record(db, "scoring.reset", request, user.id)
    return {"weights": DEFAULT_WEIGHTS}
