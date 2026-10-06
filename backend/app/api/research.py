"""Strategies, backtests and the position-size calculator. Nothing here calls a data provider."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.api.stocks import MIC_PATTERN, TICKER_PATTERN, _get_stock
from app.core.db import get_db
from app.engines import backtest as bt_engine
from app.engines import risk as risk_engine
from app.engines import strategy as strategy_engine
from app.engines.signals import compute
from app.models.entities import Backtest, Strategy, User
from app.services import audit
from app.services import shariah as shariah_svc
from app.services.analysis import USER_STRATEGY, default_strategy, load_bars, user_strategy

router = APIRouter(prefix="/api", tags=["research"])

MAX_STRATEGIES, MAX_UNIVERSE, MAX_BACKTESTS = 20, 10, 50

# Cost presets. Per side, in basis points (1 bp = 0.01%). NGX: a traditional-broker round trip is about
# 4.0% to 4.5% all-in (nairacompare.ng, 2026), so 200 bp a side; verify against your broker's contract note.
COST_PRESETS = {
    "ngx_typical": {"label": "NGX, typical broker (about 2% a side, estimate)", "commission_bps": 200,
                    "slippage_bps": 25},
    "ngx_low": {"label": "NGX, low-cost app (about 1.2% a side, estimate)", "commission_bps": 115,
                "slippage_bps": 25},
    "us_low": {"label": "US, commission-free broker", "commission_bps": 0, "slippage_bps": 5},
    "none": {"label": "No costs (for comparison only)", "commission_bps": 0, "slippage_bps": 0},
}


# ---------- strategies ----------


def _visible(db: Session, user: User) -> list[Strategy]:
    default_strategy(db)
    return list(db.scalars(select(Strategy).where((Strategy.is_builtin.is_(True)) | (Strategy.user_id == user.id))
                           .order_by(Strategy.is_builtin.desc(), Strategy.id)))


def _sdict(s: Strategy, active: Strategy) -> dict:
    cfg = strategy_engine.config(s.weights, s.rules)
    return {"id": s.id, "name": s.name, "description": s.description, "is_builtin": s.is_builtin,
            "is_active": s.id == active.id, "weights": cfg["weights"],
            "params": {k: cfg["params"][k] for k in strategy_engine.PARAM_LIMITS}, "disabled": cfg["disabled"],
            "entry_on": cfg["entry_on"], "exit": cfg["exit"], "created_at": s.created_at}


def _own(db: Session, user: User, sid: int) -> Strategy:
    s = db.get(Strategy, sid)
    if s is None or (not s.is_builtin and s.user_id != user.id):
        raise HTTPException(404, "Strategy not found")
    return s


@router.get("/strategies/catalogue")
def catalogue(_: User = Depends(current_user)):
    return {**strategy_engine.catalogue(), "cost_presets": COST_PRESETS}


@router.get("/strategies")
def list_strategies(user: User = Depends(current_user), db: Session = Depends(get_db)):
    active = user_strategy(db, user)
    return {"strategies": [_sdict(s, active) for s in _visible(db, user)], "active_id": active.id}


class StrategyIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(None, max_length=1000)
    weights: dict[str, float]
    params: dict[str, float] = {}
    disabled: list[str] = []
    entry_on: list[str] = ["BUY_SETUP"]
    exit: dict = {}


def _apply(s: Strategy, body: StrategyIn) -> None:
    exit_ = {**strategy_engine.EXIT_DEFAULTS, **body.exit}
    errors = strategy_engine.validate(body.weights, body.params, body.disabled, body.entry_on, exit_)
    if errors:
        raise HTTPException(422, "; ".join(errors))
    s.name, s.description = body.name.strip(), (body.description or "").strip() or None
    s.weights = {**strategy_engine.DEFAULT_WEIGHTS, **body.weights}
    s.rules = {"type": "setup_score", "params": body.params, "disabled": sorted(set(body.disabled)),
               "entry_on": body.entry_on, "exit": {k: exit_[k] for k in strategy_engine.EXIT_DEFAULTS}}


@router.post("/strategies", status_code=201)
def create_strategy(request: Request, body: StrategyIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    n = db.scalar(select(func.count(Strategy.id)).where(Strategy.user_id == user.id)) or 0
    if n >= MAX_STRATEGIES:
        raise HTTPException(409, f"You can keep up to {MAX_STRATEGIES} strategies")
    if body.name.strip() == USER_STRATEGY:
        raise HTTPException(409, f'"{USER_STRATEGY}" is reserved for the Settings weights')
    s = Strategy(user_id=user.id, is_builtin=False, weights={}, rules={}, level_method="swing_atr")
    _apply(s, body)
    db.add(s)
    db.commit()
    audit.record(db, "strategy.create", request, user.id, entity="strategy", entity_id=str(s.id),
                 details={"weights": s.weights, "rules": s.rules})
    return _sdict(s, user_strategy(db, user))


@router.put("/strategies/{sid}")
def update_strategy(request: Request, sid: int, body: StrategyIn, user: User = Depends(current_user),
                    db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    if s.is_builtin:
        raise HTTPException(403, "The built-in strategy cannot be edited. Create a copy instead.")
    _apply(s, body)
    db.commit()
    audit.record(db, "strategy.update", request, user.id, entity="strategy", entity_id=str(s.id),
                 details={"weights": s.weights, "rules": s.rules})
    return _sdict(s, user_strategy(db, user))


@router.delete("/strategies/{sid}")
def delete_strategy(request: Request, sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    if s.is_builtin:
        raise HTTPException(403, "The built-in strategy cannot be deleted")
    if user.active_strategy_id == s.id:
        user.active_strategy_id = None
    db.delete(s)
    db.commit()
    audit.record(db, "strategy.delete", request, user.id, entity="strategy", entity_id=str(sid))
    return {"deleted": sid}


@router.post("/strategies/{sid}/activate")
def activate(request: Request, sid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _own(db, user, sid)
    user.active_strategy_id = s.id
    db.commit()
    audit.record(db, "strategy.activate", request, user.id, entity="strategy", entity_id=str(sid))
    return {"active_id": s.id}


# ---------- risk calculator ----------


class RiskIn(BaseModel):
    account: float
    risk_pct: float
    entry: float
    stop: float
    target: float | None = None
    lot_size: int = 1
    cost_pct_per_side: float = 0.0
    max_position_pct: float = Field(100.0, gt=0, le=100)


@router.post("/risk/position-size")
def position_size(body: RiskIn, _: User = Depends(current_user)):
    return risk_engine.position_size(**body.model_dump())


# ---------- backtests ----------


class UniverseItem(BaseModel):
    exchange: str = Field(pattern=MIC_PATTERN)
    ticker: str = Field(pattern=TICKER_PATTERN)


class BacktestIn(BaseModel):
    strategy_id: int
    universe: list[UniverseItem] = Field(min_length=1, max_length=MAX_UNIVERSE)
    start: date
    end: date
    commission_bps: float = Field(0, ge=0, le=1000)
    slippage_bps: float = Field(0, ge=0, le=500)
    capital: float = Field(1_000_000, gt=0, le=1e13)
    sizing: str = Field("all_in", pattern="^(all_in|risk_pct)$")
    risk_pct: float = Field(1.0, gt=0, le=10)
    shariah_filter: str = Field("exclude_non_compliant", pattern="^(none|exclude_non_compliant|require_compliant)$")


def _gate(db: Session, stock, user: User):
    meth = shariah_svc.user_methodology(db, user)
    cache: dict[date, str] = {}

    def gate(d: date) -> str | None:
        if d not in cache:
            cache[d] = shariah_svc.run(db, stock, meth, as_of=d, persist=False)["status"] \
                if shariah_svc.has_inputs(db, stock) else "NOT_SCREENED"
        return cache[d]
    return gate, meth.name


@router.post("/backtests", status_code=201)
def run_backtest(request: Request, body: BacktestIn, user: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if body.end <= body.start:
        raise HTTPException(422, "The end date must be after the start date")
    if body.end - body.start > timedelta(days=3653):
        raise HTTPException(422, "The period can be at most 10 years")
    strat = _own(db, user, body.strategy_id)
    cfg = strategy_engine.config(strat.weights, strat.rules)
    per_stock, all_trades, notes = [], [], []
    meth_name = None
    for item in body.universe:
        s = _get_stock(db, item.exchange, item.ticker)
        bars = load_bars(db, s.id)
        cur = s.currency or s.exchange.currency
        if len(bars) < 60:
            per_stock.append({"ticker": s.ticker, "exchange": s.exchange.code, "currency": cur, "ok": False,
                              "error": f"Only {len(bars)} stored bars; at least 60 are needed"})
            continue
        gate, meth_name = _gate(db, s, user) if body.shariah_filter != "none" else (None, None)
        res = bt_engine.run(bars, cfg, currency=cur, start=body.start, end=body.end, capital=body.capital,
                            commission_bps=body.commission_bps, slippage_bps=body.slippage_bps, sizing=body.sizing,
                            risk_pct=body.risk_pct, shariah_gate=gate,
                            require_compliant=body.shariah_filter == "require_compliant", data=compute(bars))
        if not res["ok"]:
            per_stock.append({"ticker": s.ticker, "exchange": s.exchange.code, "currency": cur, "ok": False,
                              "error": res["error"]})
            continue
        first = bars[0]["t"]
        if first > body.start:
            notes.append(f"{s.ticker}: stored history starts {first:%d %b %Y}, after the chosen start")
        per_stock.append({"ticker": s.ticker, "exchange": s.exchange.code, "currency": cur, "ok": True,
                          "metrics": res["metrics"]})
        all_trades += [{**x, "ticker": s.ticker, "exchange": s.exchange.code, "currency": cur} for x in res["trades"]]
    ok = [p for p in per_stock if p["ok"]]
    if not ok:
        raise HTTPException(422, "No stock in the universe has enough stored history for this period. "
                                 "Open each stock first so its prices are stored.")
    wins = [x for x in all_trades if x["pl"] > 0]
    losses = [x for x in all_trades if x["pl"] <= 0]
    gl = -sum(x["pl_pct"] for x in losses)
    rs = [x["r_multiple"] for x in all_trades if x["r_multiple"] is not None]
    summary = {
        "stocks": len(ok), "trades": len(all_trades), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(all_trades) * 100 if all_trades else None,
        "avg_gain_pct": sum(x["pl_pct"] for x in wins) / len(wins) if wins else None,
        "avg_loss_pct": sum(x["pl_pct"] for x in losses) / len(losses) if losses else None,
        "profit_factor_pct_basis": sum(x["pl_pct"] for x in wins) / gl if gl > 0 else None,
        "avg_r": sum(rs) / len(rs) if rs else None,
        "avg_total_return_pct": sum(p["metrics"]["total_return_pct"] for p in ok) / len(ok),
        "avg_buy_hold_return_pct": sum(p["metrics"]["buy_hold_return_pct"] for p in ok) / len(ok),
        "worst_drawdown_pct": min(p["metrics"]["max_drawdown_pct"] for p in ok),
        "avg_exposure_pct": sum(p["metrics"]["exposure_pct"] for p in ok) / len(ok),
    }
    settings = body.model_dump(mode="json", exclude={"universe", "strategy_id"})
    record = Backtest(user_id=user.id, strategy_id=strat.id, start=body.start, end=body.end,
                      costs_bps=body.commission_bps, slippage_bps=body.slippage_bps, status="done",
                      universe={"stocks": [i.model_dump() for i in body.universe], "settings": settings,
                                "strategy": {"name": strat.name, **cfg}, "shariah_methodology": meth_name},
                      metrics={"summary": summary, "per_stock": per_stock, "notes": notes,
                               "limitations": ["The market-regime rule is not evaluated in backtests.",
                                               "Business-activity tags are today's; fundamentals are point in "
                                               "time by their published date.",
                                               "Only stocks you chose are tested; delisted stocks are not added "
                                               "automatically."]},
                      trades=all_trades[:2000])
    db.add(record)
    old = db.scalars(select(Backtest).where(Backtest.user_id == user.id).order_by(Backtest.id.desc())
                     .offset(MAX_BACKTESTS)).all()
    for o in old:
        db.delete(o)
    db.commit()
    audit.record(db, "backtest.run", request, user.id, entity="backtest", entity_id=str(record.id),
                 details={"strategy": strat.name, "stocks": len(body.universe), "trades": len(all_trades)})
    return _bdict(record)


def _bdict(b: Backtest, full: bool = True) -> dict:
    out = {"id": b.id, "strategy_id": b.strategy_id, "strategy": (b.universe or {}).get("strategy", {}).get("name"),
           "start": b.start, "end": b.end, "status": b.status, "created_at": b.created_at,
           "stocks": [f"{x['exchange']}:{x['ticker']}" for x in (b.universe or {}).get("stocks", [])],
           "summary": (b.metrics or {}).get("summary")}
    if full:
        out.update({"universe": b.universe, "metrics": b.metrics, "trades": b.trades})
    return out


@router.get("/backtests")
def list_backtests(user: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = db.scalars(select(Backtest).where(Backtest.user_id == user.id).order_by(Backtest.id.desc())).all()
    return {"backtests": [_bdict(b, full=False) for b in rows]}


@router.get("/backtests/{bid}")
def get_backtest(bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Backtest, bid)
    if b is None or b.user_id != user.id:
        raise HTTPException(404, "Backtest not found")
    return _bdict(b)


@router.delete("/backtests/{bid}")
def delete_backtest(bid: int, user: User = Depends(current_user), db: Session = Depends(get_db)):
    b = db.get(Backtest, bid)
    if b is None or b.user_id != user.id:
        raise HTTPException(404, "Backtest not found")
    db.delete(b)
    db.commit()
    return {"deleted": bid, "at": datetime.now(UTC)}
