"""Dashboard assembly. Reads only what is stored; missing data is reported as UNAVAILABLE."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import (
    Alert,
    AlertEvent,
    DataSource,
    DataStatus,
    Exchange,
    Signal,
    SignalType,
    Stock,
    User,
    Watchlist,
    WatchlistStock,
)
from app.providers.registry import ProviderRegistry
from app.schemas.common import DataPoint
from app.services import shariah as shariah_svc
from app.services.prices import quote, refresh_bars

log = logging.getLogger("hss.dashboard")

INDEX_CARDS = [
    ("NG", "NGX All-Share Index", "NGXASI"),
    ("US", "S&P 500", "SPX"),
    ("US", "NASDAQ Composite", "IXIC"),
]


def _index_stock(db: Session, eodhd_symbol: str, label: str) -> Stock | None:
    ex = db.scalar(select(Exchange).where(Exchange.code == "INDX"))
    if ex is None:
        return None
    ticker = eodhd_symbol.split(".")[0].upper()
    s = db.scalar(select(Stock).where(Stock.exchange_id == ex.id, Stock.ticker == ticker))
    if s is None:
        s = Stock(ticker=ticker, exchange_id=ex.id, name=label, instrument_type="index",
                  provider_symbols={"eodhd": eodhd_symbol})
        db.add(s)
        db.commit()
    return s


def _index_cards(db: Session, registry: ProviderRegistry) -> list[dict]:
    cards = []
    symbols = get_settings().index_symbols
    for market, label, key in INDEX_CARDS:
        sym = symbols.get(key, "")
        dp: dict
        if not sym:
            dp = DataPoint[float].unavailable(
                f"Index symbol for {label} not set (INDEX_SYMBOLS). Find it with provider search, type = index."
            ).model_dump()
        elif registry.for_market("GL") is None:
            dp = DataPoint[float].unavailable("; ".join(registry.explain("GL"))).model_dump()
        else:
            try:
                stock = _index_stock(db, sym, label)
                refresh = refresh_bars(db, stock, registry) if stock else None
                q = quote(db, stock) if stock else None
            except Exception as e:  # one broken card must never take the dashboard down
                log.exception("Index card %s failed", key)
                db.rollback()
                cards.append({"market": market, "label": label, "symbol": sym, "change_pct": DataPoint[float]
                              .unavailable(f"Could not load this index ({type(e).__name__}); see backend log")
                              .model_dump()})
                continue
            if not q or q["price"] is None:
                note = (refresh.message if refresh and refresh.message else "No index history stored")
                dp = DataPoint[float].unavailable(note, source="EODHD").model_dump()
            else:
                dp = {"value": q["change_pct"], "source": q["source"], "as_of": q["as_of"],
                      "frequency": q["frequency"], "status": q["status"],
                      "note": q["note"] or (refresh.message if refresh and refresh.status == "failed" else None),
                      "level": q["price"]}
        cards.append({"market": market, "label": label, "symbol": sym or key, "change_pct": dp})
    return cards


def _regime_card(db: Session, market: str) -> dict:
    from app.services.analysis import market_regime  # local import avoids a cycle at start-up

    rg = market_regime(db, market)
    if rg is None or rg.get("label") is None:
        why = (rg or {}).get("explanation") or ("No index symbol configured for NGX (INDEX_SYMBOLS)" if market == "NG"
                                                 else "Index history not stored yet")
        return DataPoint[str].unavailable(why).model_dump()
    label = rg["label"] + (f" · {rg['volatility']}" if rg.get("volatility") else "")
    return {"value": label, "source": "EODHD", "as_of": rg["as_of"], "frequency": "end-of-day",
            "status": "END_OF_DAY", "note": rg["explanation"]}


def _configured(registry: ProviderRegistry, code: str) -> bool:
    p = registry.providers.get(code)
    return bool(p and p.is_configured())


def build_dashboard(db: Session, user_id: int, registry: ProviderRegistry | None = None) -> dict:
    registry = registry or ProviderRegistry(db=db)
    since = datetime.now(UTC) - timedelta(days=7)

    compliant_ids = shariah_svc.compliant_stock_ids(db, db.get(User, user_id))

    setups_q = (
        select(Signal)
        .where(Signal.created_at >= since, Signal.signal_type.in_([SignalType.BUY_SETUP, SignalType.WATCHLIST]))
        .where(Signal.stock_id.in_(compliant_ids or {-1}))
        .order_by(Signal.score.desc().nullslast())
        .limit(20)
    )
    setups = db.scalars(setups_q).all()

    recent = db.scalars(select(Signal).order_by(Signal.created_at.desc()).limit(10)).all()

    unread_alerts = db.scalar(
        select(func.count(AlertEvent.id)).join(Alert).where(Alert.user_id == user_id, AlertEvent.is_read.is_(False))
    ) or 0
    watch_count = db.scalar(
        select(func.count(WatchlistStock.stock_id)).join(Watchlist).where(Watchlist.user_id == user_id)
    ) or 0
    universe = db.scalar(
        select(func.count(Stock.id)).where(Stock.is_active.is_(True), Stock.instrument_type != "index")
    ) or 0
    compliant_count = len(compliant_ids)

    sources = db.scalars(select(DataSource).order_by(DataSource.kind, DataSource.name)).all()

    def sig_row(s: Signal) -> dict:
        return {
            "id": s.id, "ticker": s.stock.ticker, "name": s.stock.name, "signal": s.signal_type.value,
            "score": s.score, "coverage": s.coverage, "risk_reward": s.risk_reward,
            "data_as_of": s.data_as_of, "created_at": s.created_at,
        }

    return {
        "generated_at": datetime.now(UTC),
        "index_cards": _index_cards(db, registry),
        "counts": {
            "stock_universe": universe,
            "shariah_compliant": compliant_count,
            "potential_setups": len([s for s in setups if s.signal_type == SignalType.BUY_SETUP]),
            "watchlist_stocks": watch_count,
            "unread_alerts": unread_alerts,
        },
        "top_setups": [sig_row(s) for s in setups],
        "recent_signals": [sig_row(s) for s in recent],
        "market_regime": {m: _regime_card(db, m) for m in ("NG", "US")},
        "data_sources": [
            {
                "code": d.code, "name": d.name, "kind": d.kind.value, "tier": d.tier, "frequency": d.frequency,
                "enabled": d.is_enabled or _configured(registry, d.code),
                "last_success_at": d.last_success_at, "last_error": d.last_error,
                "status": (DataStatus.UNAVAILABLE if not d.is_enabled or not d.last_success_at else
                           DataStatus.END_OF_DAY if d.frequency == "eod" else DataStatus.DELAYED).value,
            }
            for d in sources
        ],
    }
