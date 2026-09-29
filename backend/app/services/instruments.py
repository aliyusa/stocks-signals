"""Stock universe: local search (free) and provider search/import (metered)."""

from sqlalchemy import or_, select
from sqlalchemy.orm import Session, joinedload

from app.models.entities import Exchange, Market, Stock
from app.providers.base import Instrument, ProviderUnavailable
from app.providers.registry import ProviderRegistry


def _like(q: str) -> str:
    esc = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{esc}%"


def search_local(db: Session, q: str, market: str | None = None, limit: int = 20) -> list[Stock]:
    q = q.strip()
    stmt = select(Stock).join(Exchange).join(Market).options(joinedload(Stock.exchange).joinedload(Exchange.market))
    stmt = stmt.where(Stock.is_active.is_(True))
    if q:
        stmt = stmt.where(or_(Stock.ticker.ilike(_like(q), escape="\\"), Stock.name.ilike(_like(q), escape="\\")))
    if market and market != "GLOBAL":
        stmt = stmt.where(Market.code == market)
    # exact ticker first
    rows = list(db.scalars(stmt.limit(200)).unique())
    rows.sort(key=lambda s: (s.ticker != q.upper(), not s.ticker.startswith(q.upper()), s.ticker))
    return rows[:limit]


def upsert_instrument(db: Session, inst: Instrument, provider_code: str) -> Stock | None:
    ex = db.scalar(select(Exchange).where(Exchange.code == inst.exchange))
    if ex is None:
        return None
    stock = db.scalar(select(Stock).where(Stock.ticker == inst.ticker, Stock.exchange_id == ex.id))
    psym = inst.extra.get(f"{provider_code}_symbol")
    symbols = {provider_code: psym} if psym else {}
    if stock is None:
        stock = Stock(ticker=inst.ticker, exchange_id=ex.id, name=inst.name[:200], country=inst.country,
                      currency=inst.currency or ex.currency, isin=(inst.extra.get("isin") or None),
                      instrument_type=inst.extra.get("type") or "stock", provider_symbols=symbols)
        db.add(stock)
        db.flush()  # make it visible to the next lookup in the same batch
    else:
        stock.name = inst.name[:200] or stock.name
        stock.provider_symbols = {**(stock.provider_symbols or {}), **symbols}
        stock.isin = stock.isin or inst.extra.get("isin") or None
    return stock


def search_provider(db: Session, registry: ProviderRegistry, q: str, instrument_type: str | None = None,
                    market: str | None = None) -> tuple[list[Stock], str | None]:
    provider = registry.providers.get("eodhd")
    if provider is None or not provider.is_configured():
        return [], "EODHD: API key not set (EODHD_API_KEY)"
    try:
        found = provider.search(q, limit=25, instrument_type=instrument_type)
    except ProviderUnavailable as e:
        return [], str(e)
    stocks = [s for s in (upsert_instrument(db, i, provider.code) for i in found) if s]
    db.commit()
    if market and market != "GLOBAL":
        stocks = [s for s in stocks if s.exchange.market.code == market]
    return stocks, None


def import_exchange(db: Session, registry: ProviderRegistry, mic: str) -> tuple[int, str | None]:
    provider = registry.providers.get("eodhd")
    if provider is None or not provider.is_configured():
        return 0, "EODHD: API key not set (EODHD_API_KEY)"
    try:
        found = provider.list_exchange(mic)
    except ProviderUnavailable as e:
        return 0, str(e)
    n = 0
    for inst in found:
        if inst.extra.get("type") in ("stock", "etf") and upsert_instrument(db, inst, provider.code):
            n += 1
    db.commit()
    return n, None
