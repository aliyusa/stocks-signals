import re

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.api.deps import current_user
from app.core.config import get_settings
from app.core.db import get_db
from app.core.ratelimit import limiter
from app.models.entities import Exchange, Stock, User
from app.providers.registry import ProviderRegistry
from app.services import audit
from app.services.instruments import import_exchange, search_local, search_provider
from app.services.prices import RANGES, bars_frame, data_quality, latest_bar, quote, refresh_bars
from app.services.usage import usage_summary

router = APIRouter(prefix="/api", tags=["stocks"])

TICKER_PATTERN = r"^[A-Za-z0-9.\-_]{1,24}$"
MIC_PATTERN = r"^[A-Z]{4}$"


def _row(db: Session, s: Stock, with_quote: bool = True) -> dict:
    out = {
        "ticker": s.ticker, "name": s.name, "exchange": s.exchange.code, "exchange_name": s.exchange.name,
        "market": s.exchange.market.code, "country": s.country, "currency": s.currency or s.exchange.currency,
        "type": s.instrument_type, "isin": s.isin, "sector": s.sector.name if s.sector else None,
    }
    if with_quote:
        out["quote"] = quote(db, s)
    return out


def _get_stock(db: Session, mic: str, ticker: str) -> Stock:
    s = db.scalar(select(Stock).join(Exchange).where(Exchange.code == mic, Stock.ticker == ticker.upper()))
    if s is None:
        raise HTTPException(404, "Stock not in the local universe. Use provider search to add it.")
    return s


@router.get("/search")
def search(q: str = Query("", max_length=64), market: str | None = Query(None, max_length=8),
           _: User = Depends(current_user), db: Session = Depends(get_db)):
    """Local search only: free, instant, no provider calls."""
    return {"results": [_row(db, s) for s in search_local(db, q, market)]}


class ProviderSearchIn(BaseModel):
    q: str = Field(min_length=1, max_length=64)
    type: str | None = Field(default=None, pattern="^(stock|etf|index|fund)$")
    market: str | None = Field(default=None, max_length=8)


@router.post("/search/provider")
@limiter.limit("20/minute")
def search_remote(request: Request, body: ProviderSearchIn, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    """Searches EODHD (costs 1 API call) and adds matches to the local universe."""
    s = get_settings()
    stocks, err = search_provider(db, ProviderRegistry(db=db), body.q, body.type, body.market)
    audit.record(db, "provider.search", request, user.id, details={"q": body.q, "error": err, "n": len(stocks)})
    return {"results": [_row(db, x) for x in stocks], "error": err,
            "usage": usage_summary(db, "eodhd", s.eodhd_daily_call_limit)}


@router.post("/exchanges/{mic}/import")
@limiter.limit("5/minute")
def import_symbols(request: Request, mic: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    if not re.fullmatch(MIC_PATTERN, mic):
        raise HTTPException(422, "Invalid exchange code")
    n, err = import_exchange(db, ProviderRegistry(db=db), mic)
    audit.record(db, "provider.import_exchange", request, user.id, entity="exchange", entity_id=mic,
                 details={"imported": n, "error": err})
    return {"imported": n, "error": err, "usage": usage_summary(db, "eodhd", get_settings().eodhd_daily_call_limit)}


@router.get("/stocks")
def list_stocks(market: str | None = Query(None, max_length=8), limit: int = Query(100, ge=1, le=500),
                _: User = Depends(current_user), db: Session = Depends(get_db)):
    rows = search_local(db, "", market, limit)
    return {"results": [_row(db, s) for s in rows]}


@router.get("/stocks/{mic}/{ticker}")
def stock_detail(mic: str, ticker: str, refresh: bool = True, _: User = Depends(current_user),
                 db: Session = Depends(get_db)):
    if not (re.fullmatch(MIC_PATTERN, mic) and re.fullmatch(TICKER_PATTERN, ticker)):
        raise HTTPException(422, "Invalid exchange or ticker")
    s = _get_stock(db, mic, ticker)
    result = refresh_bars(db, s, ProviderRegistry(db=db)) if refresh else None
    last = latest_bar(db, s.id)
    return {
        **_row(db, s),
        "refresh": ({"status": result.status, "new_bars": result.new_bars, "message": result.message}
                    if result else None),
        "data_quality": data_quality(db, s),
        "last_bar": last.ts if last else None,
        "usage": usage_summary(db, "eodhd", get_settings().eodhd_daily_call_limit),
    }


@router.get("/stocks/{mic}/{ticker}/bars")
def stock_bars(mic: str, ticker: str, range: str = Query("1Y", pattern="^(1M|3M|6M|1Y|5Y|MAX)$"),
               _: User = Depends(current_user), db: Session = Depends(get_db)):
    s = _get_stock(db, mic, ticker)
    rows = bars_frame(db, s.id, range)
    return {
        "ticker": s.ticker, "exchange": s.exchange.code, "interval": "1d", "range": range,
        "adjusted": False, "note": "Unadjusted OHLC as published; adj_close accounts for splits and dividends.",
        "bars": [{"t": r.ts.date().isoformat(), "o": r.open, "h": r.high, "l": r.low, "c": r.close,
                  "ac": r.adj_close, "v": r.volume} for r in rows],
        "ranges": list(RANGES),
    }


@router.post("/stocks/{mic}/{ticker}/refresh")
@limiter.limit("10/minute")
def force_refresh(request: Request, mic: str, ticker: str, user: User = Depends(current_user),
                  db: Session = Depends(get_db)):
    s = _get_stock(db, mic, ticker)
    r = refresh_bars(db, s, ProviderRegistry(db=db), force=True)
    audit.record(db, "provider.refresh", request, user.id, entity="stock", entity_id=f"{mic}:{s.ticker}",
                 details={"status": r.status, "new": r.new_bars, "message": r.message})
    return {"status": r.status, "new_bars": r.new_bars, "message": r.message, "quote": quote(db, s),
            "usage": usage_summary(db, "eodhd", get_settings().eodhd_daily_call_limit)}


@router.get("/usage")
def usage(_: User = Depends(current_user), db: Session = Depends(get_db)):
    return {"eodhd": usage_summary(db, "eodhd", get_settings().eodhd_daily_call_limit)}
