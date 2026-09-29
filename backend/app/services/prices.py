"""Price ingestion, freshness classification and quote derivation.

Rules:
- Bars are fetched only when the stored history is behind the expected session, so a
  metered free plan is spent on new data, not on repeats.
- The "quote" on end-of-day plans is the last stored close, labelled END_OF_DAY (or STALE).
- Every failure is recorded on the DataSource row and surfaced; stored data is kept.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import DataSource, DataStatus, Exchange, PriceHistory, Stock
from app.providers.base import ProviderUnavailable
from app.providers.registry import ProviderRegistry
from app.services.market_calendar import expected_last_session, sessions_between

RANGES = {"1M": 31, "3M": 92, "6M": 183, "1Y": 366, "5Y": 1830, "MAX": None}
WAT = timezone(timedelta(hours=1), "WAT")  # West Africa Time has no daylight saving


@dataclass
class RefreshResult:
    status: str  # fetched | fresh | cooldown | failed | no_provider
    new_bars: int = 0
    message: str | None = None


def _aware(ts: datetime) -> datetime:
    return ts if ts.tzinfo else ts.replace(tzinfo=UTC)


def latest_bar(db: Session, stock_id: int, interval: str = "1d") -> PriceHistory | None:
    return db.scalar(
        select(PriceHistory).where(PriceHistory.stock_id == stock_id, PriceHistory.interval == interval)
        .order_by(PriceHistory.ts.desc()).limit(1)
    )


def source_row(db: Session, code: str) -> DataSource | None:
    return db.scalar(select(DataSource).where(DataSource.code == code))


def market_of(stock: Stock) -> str:
    return stock.exchange.market.code


def refresh_bars(db: Session, stock: Stock, registry: ProviderRegistry, force: bool = False,
                 now: datetime | None = None) -> RefreshResult:
    now = now or datetime.now(UTC)
    provider = registry.for_market(market_of(stock))
    if provider is None:
        return RefreshResult("no_provider", message="; ".join(registry.explain(market_of(stock))))

    ex: Exchange = stock.exchange
    expected = expected_last_session(now, ex.timezone, ex.close_time)
    last = latest_bar(db, stock.id)
    last_day = _aware(last.ts).date() if last else None
    if last_day and last_day >= expected and not force:
        return RefreshResult("fresh")
    attempted = _aware(stock.last_fetch_attempt_at) if stock.last_fetch_attempt_at else None
    cooldown = timedelta(hours=get_settings().auto_refresh_cooldown_hours)
    if not force and attempted and now - attempted < cooldown:
        nxt = (attempted + cooldown).astimezone(WAT).strftime("%d %b %Y, %H:%M WAT")
        return RefreshResult("cooldown", message=f"Fetched recently; next automatic check after {nxt}")

    history_days = 365 * get_settings().history_years
    start = (last_day - timedelta(days=7)) if last_day else (now.date() - timedelta(days=history_days))
    src = source_row(db, provider.code)
    if src is None:
        msg = f"Data source '{provider.code}' is not registered; run python -m app.seed"
        return RefreshResult("failed", message=msg)
    stock.last_fetch_attempt_at = now
    db.commit()
    try:
        bars = provider.get_bars(stock.ticker, ex.code, "1d", start, now.date())
    except ProviderUnavailable as e:
        src.last_error, src.last_error_at = str(e), now
        db.commit()
        return RefreshResult("failed", message=str(e))

    # Keyed by calendar date (one daily bar per session); the window starts a day early so
    # timezone handling differences between databases can never cause a duplicate insert.
    first_incoming = min((b.ts.date() for b in bars.bars), default=start)
    window_start = datetime.combine(min(start, first_incoming) - timedelta(days=1), datetime.min.time(), UTC)
    existing = {
        _aware(r.ts).date(): r for r in db.scalars(
            select(PriceHistory).where(PriceHistory.stock_id == stock.id, PriceHistory.interval == "1d",
                                       PriceHistory.ts >= window_start)
        )
    }
    new = 0
    for b in bars.bars:
        row = existing.get(b.ts.date())
        if row is None:
            db.add(PriceHistory(stock_id=stock.id, interval="1d", ts=b.ts, open=b.open, high=b.high, low=b.low,
                                close=b.close, adj_close=b.adj_close, volume=b.volume, source_id=src.id))
            new += 1
        else:  # vendors revise recent bars; keep the latest values
            row.open, row.high, row.low, row.close = b.open, b.high, b.low, b.close
            row.adj_close, row.volume, row.source_id = b.adj_close, b.volume, src.id
    src.last_success_at, src.last_error, src.is_enabled = now, None, True
    db.commit()
    msg = None if bars.bars else "Provider returned no bars for this window (possible rename, delisting or holiday)"
    return RefreshResult("fetched", new_bars=new, message=msg)


def freshness(stock: Stock, last_day: date | None, now: datetime | None = None) -> tuple[DataStatus, str | None]:
    if last_day is None:
        return DataStatus.UNAVAILABLE, "No price history stored"
    now = now or datetime.now(UTC)
    expected = expected_last_session(now, stock.exchange.timezone, stock.exchange.close_time)
    behind = sessions_between(expected, last_day)
    if behind <= 0:
        return DataStatus.END_OF_DAY, None
    if behind == 1:
        return DataStatus.STALE, "One session behind: possible public holiday or provider delay"
    return DataStatus.STALE, f"{behind} sessions behind the expected close of {expected.strftime('%d %b %Y')}"


def bars_frame(db: Session, stock_id: int, range_key: str = "1Y", interval: str = "1d") -> list[PriceHistory]:
    days = RANGES.get(range_key.upper(), 366)
    q = select(PriceHistory).where(PriceHistory.stock_id == stock_id, PriceHistory.interval == interval)
    if days:
        last = latest_bar(db, stock_id, interval)
        if last:
            q = q.where(PriceHistory.ts >= _aware(last.ts) - timedelta(days=days))
    return list(db.scalars(q.order_by(PriceHistory.ts)))


def quote(db: Session, stock: Stock) -> dict:
    rows = list(db.scalars(
        select(PriceHistory).where(PriceHistory.stock_id == stock.id, PriceHistory.interval == "1d")
        .order_by(PriceHistory.ts.desc()).limit(2)
    ))
    if not rows:
        return {"price": None, "change_pct": None, "as_of": None, "status": DataStatus.UNAVAILABLE.value,
                "source": None, "frequency": None, "note": "No price history stored"}
    last = rows[0]
    prev = rows[1] if len(rows) > 1 else None
    change = ((last.close / prev.close - 1) * 100) if prev and prev.close else None
    status, note = freshness(stock, _aware(last.ts).date())
    src = db.get(DataSource, last.source_id)
    return {"price": last.close, "change_pct": change, "as_of": _aware(last.ts), "status": status.value,
            "source": src.name if src else None, "frequency": "end-of-day", "note": note,
            "volume": last.volume, "previous_close": prev.close if prev else None}


def data_quality(db: Session, stock: Stock) -> dict:
    n, first, last = db.execute(
        select(func.count(), func.min(PriceHistory.ts), func.max(PriceHistory.ts))
        .where(PriceHistory.stock_id == stock.id, PriceHistory.interval == "1d")
    ).one()
    recent = list(db.scalars(
        select(PriceHistory).where(PriceHistory.stock_id == stock.id, PriceHistory.interval == "1d")
        .order_by(PriceHistory.ts.desc()).limit(60)
    ))
    zero_range = sum(1 for r in recent if r.high is not None and r.low is not None and r.high == r.low)
    zero_vol = sum(1 for r in recent if not r.volume)
    share = (zero_range / len(recent)) if recent else None
    warnings = []
    if share is not None and share > 0.2:
        warnings.append(
            f"{share:.0%} of the last {len(recent)} bars have high = low. Price discovery is thin, so "
            "momentum indicators on this stock are unreliable."
        )
    if recent and zero_vol / len(recent) > 0.2:
        warnings.append(f"{zero_vol} of the last {len(recent)} sessions show zero volume.")
    if n and n < 200:
        warnings.append(f"Only {n} daily bars stored; a 200-day average needs at least 200.")
    return {"bars": n, "first": _aware(first) if first else None, "last": _aware(last) if last else None,
            "zero_range_share_60": share, "warnings": warnings}
