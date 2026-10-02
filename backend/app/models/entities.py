"""All database entities. See docs/ARCHITECTURE.md §2 for the rationale of each table.

Conventions:
- timestamps are timezone-aware UTC
- every fact that came from outside carries source_id and an as-of timestamp
- nothing here stores a fabricated value; nullable columns mean "unknown"
"""

import enum
from datetime import date, datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.db import Base, JSONType

Money = Numeric(20, 6)
TS = DateTime(timezone=True)


def _now_col():
    return mapped_column(TS, server_default=func.now(), nullable=False)


# ---------- enums ----------


class DataStatus(str, enum.Enum):
    LIVE = "LIVE"
    DELAYED = "DELAYED"
    END_OF_DAY = "END_OF_DAY"
    STALE = "STALE"
    UNAVAILABLE = "UNAVAILABLE"


class ShariahStatus(str, enum.Enum):
    COMPLIANT = "COMPLIANT"
    NON_COMPLIANT = "NON_COMPLIANT"
    QUESTIONABLE = "QUESTIONABLE"
    INSUFFICIENT_DATA = "INSUFFICIENT_DATA"
    UNDER_REVIEW = "UNDER_REVIEW"


class SignalType(str, enum.Enum):
    BUY_SETUP = "BUY_SETUP"
    SELL_EXIT = "SELL_EXIT"
    HOLD = "HOLD"
    WAIT = "WAIT"
    AVOID = "AVOID"
    WATCHLIST = "WATCHLIST"


class SourceKind(str, enum.Enum):
    PRICE = "price"
    FUNDAMENTAL = "fundamental"
    NEWS = "news"
    SHARIAH = "shariah"


# ---------- identity & audit ----------


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    password_hash: Mapped[str] = mapped_column(String(255))
    full_name: Mapped[str | None] = mapped_column(String(120))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False)
    timezone: Mapped[str] = mapped_column(String(64), default="Africa/Lagos")
    token_version: Mapped[int] = mapped_column(Integer, default=0)  # bump to revoke all sessions
    shariah_methodology_id: Mapped[int | None] = mapped_column(
        ForeignKey("shariah_methodologies.id", ondelete="SET NULL", use_alter=True,
                   name="fk_users_shariah_methodology"))  # None = built-in default
    failed_logins: Mapped[int] = mapped_column(Integer, default=0)
    locked_until: Mapped[datetime | None] = mapped_column(TS)
    created_at: Mapped[datetime] = _now_col()


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(BigInteger().with_variant(Integer, "sqlite"), primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), index=True)
    action: Mapped[str] = mapped_column(String(64), index=True)
    entity: Mapped[str | None] = mapped_column(String(64))
    entity_id: Mapped[str | None] = mapped_column(String(64))
    ip: Mapped[str | None] = mapped_column(String(64))
    user_agent: Mapped[str | None] = mapped_column(String(255))
    details: Mapped[dict | None] = mapped_column(JSONType)
    created_at: Mapped[datetime] = _now_col()


# ---------- reference data ----------


class Market(Base):
    __tablename__ = "markets"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(8), unique=True)  # NG, US, UK, GCC, MY, ID, CA, EU
    name: Mapped[str] = mapped_column(String(80))
    exchanges: Mapped[list["Exchange"]] = relationship(back_populates="market")


class Exchange(Base):
    __tablename__ = "exchanges"
    id: Mapped[int] = mapped_column(primary_key=True)
    market_id: Mapped[int] = mapped_column(ForeignKey("markets.id"), index=True)
    code: Mapped[str] = mapped_column(String(16), unique=True)  # ISO MIC, e.g. XNSA
    name: Mapped[str] = mapped_column(String(120))
    currency: Mapped[str] = mapped_column(String(3))
    timezone: Mapped[str] = mapped_column(String(64))
    open_time: Mapped[str | None] = mapped_column(String(5))  # local HH:MM
    close_time: Mapped[str | None] = mapped_column(String(5))
    market: Mapped[Market] = relationship(back_populates="exchanges")


class Sector(Base):
    __tablename__ = "sectors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120), unique=True)
    parent_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"))


class DataSource(Base):
    __tablename__ = "data_sources"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(32), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    kind: Mapped[SourceKind] = mapped_column(Enum(SourceKind, native_enum=False, length=16))
    tier: Mapped[str] = mapped_column(String(16))  # free / freemium / paid / manual
    frequency: Mapped[str] = mapped_column(String(32))  # realtime / delayed-15m / eod / quarterly
    delay_minutes: Mapped[int | None] = mapped_column(Integer)
    website: Mapped[str | None] = mapped_column(String(255))
    notes: Mapped[str | None] = mapped_column(Text)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    last_success_at: Mapped[datetime | None] = mapped_column(TS)
    last_error: Mapped[str | None] = mapped_column(Text)
    last_error_at: Mapped[datetime | None] = mapped_column(TS)


class ProviderUsage(Base):
    """Calls made to a metered provider per UTC day, so free-tier budgets are never exceeded blindly."""

    __tablename__ = "provider_usage"
    source_code: Mapped[str] = mapped_column(String(32), primary_key=True)
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    calls: Mapped[int] = mapped_column(Integer, default=0)
    last_endpoint: Mapped[str | None] = mapped_column(String(64))


class Stock(Base):
    __tablename__ = "stocks"
    __table_args__ = (UniqueConstraint("ticker", "exchange_id", name="uq_stock_ticker_exchange"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    ticker: Mapped[str] = mapped_column(String(24), index=True)
    exchange_id: Mapped[int] = mapped_column(ForeignKey("exchanges.id"), index=True)
    name: Mapped[str] = mapped_column(String(200))
    sector_id: Mapped[int | None] = mapped_column(ForeignKey("sectors.id"), index=True)
    country: Mapped[str | None] = mapped_column(String(2))
    currency: Mapped[str | None] = mapped_column(String(3))
    isin: Mapped[str | None] = mapped_column(String(12), index=True)
    instrument_type: Mapped[str] = mapped_column(String(24), default="stock")  # stock, etf, index
    provider_symbols: Mapped[dict | None] = mapped_column(JSONType)  # {"eodhd": "DANGCEM.XNSA"}
    last_fetch_attempt_at: Mapped[datetime | None] = mapped_column(TS)  # automatic-refresh cooldown
    activity_tags: Mapped[list | None] = mapped_column(JSONType)  # [{tag, label, primary, revenue_share, source}]
    shariah_external: Mapped[list | None] = mapped_column(JSONType)  # [{source, status, as_of, url, note}]
    shariah_review_note: Mapped[str | None] = mapped_column(Text)  # set = UNDER_REVIEW
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    listed_at: Mapped[date | None] = mapped_column(Date)
    delisted_at: Mapped[date | None] = mapped_column(Date)  # kept for survivorship-bias control
    exchange: Mapped[Exchange] = relationship()
    sector: Mapped[Sector | None] = relationship()


# ---------- market data ----------


class PriceHistory(Base):
    __tablename__ = "price_history"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    interval: Mapped[str] = mapped_column(String(4), primary_key=True)  # 15m, 1h, 4h, 1d, 1w
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float] = mapped_column(Float)
    adj_close: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    ingested_at: Mapped[datetime] = _now_col()


Index("ix_price_stock_interval_ts_desc", PriceHistory.stock_id, PriceHistory.interval, PriceHistory.ts.desc())


class Fundamentals(Base):
    __tablename__ = "fundamentals"
    __table_args__ = (UniqueConstraint("stock_id", "period_end", "period_type", "source_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    period_end: Mapped[date] = mapped_column(Date)
    period_type: Mapped[str] = mapped_column(String(4))  # Q, A, TTM
    currency: Mapped[str | None] = mapped_column(String(3))
    revenue: Mapped[float | None] = mapped_column(Money)
    net_income: Mapped[float | None] = mapped_column(Money)
    eps: Mapped[float | None] = mapped_column(Money)
    total_debt: Mapped[float | None] = mapped_column(Money)
    interest_bearing_debt: Mapped[float | None] = mapped_column(Money)
    cash: Mapped[float | None] = mapped_column(Money)
    interest_bearing_securities: Mapped[float | None] = mapped_column(Money)
    receivables: Mapped[float | None] = mapped_column(Money)
    total_assets: Mapped[float | None] = mapped_column(Money)
    total_equity: Mapped[float | None] = mapped_column(Money)
    interest_income: Mapped[float | None] = mapped_column(Money)
    non_permissible_income: Mapped[float | None] = mapped_column(Money)
    market_cap: Mapped[float | None] = mapped_column(Money)
    shares_outstanding: Mapped[float | None] = mapped_column(Money)
    dividend_per_share: Mapped[float | None] = mapped_column(Money)
    is_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    source_ref: Mapped[str | None] = mapped_column(String(500))  # report title, page or URL
    note: Mapped[str | None] = mapped_column(Text)
    entered_by_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"))
    reported_at: Mapped[datetime | None] = mapped_column(TS)  # point-in-time availability
    ingested_at: Mapped[datetime] = _now_col()


class TechnicalIndicator(Base):
    """Cache only; always recomputable from price_history."""

    __tablename__ = "technical_indicators"
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    interval: Mapped[str] = mapped_column(String(4), primary_key=True)
    ts: Mapped[datetime] = mapped_column(TS, primary_key=True)
    name: Mapped[str] = mapped_column(String(32), primary_key=True)
    params: Mapped[dict] = mapped_column(JSONType)
    value: Mapped[dict] = mapped_column(JSONType)


class News(Base):
    __tablename__ = "news"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    source_id: Mapped[int] = mapped_column(ForeignKey("data_sources.id"))
    published_at: Mapped[datetime] = mapped_column(TS, index=True)
    title: Mapped[str] = mapped_column(String(500))
    url: Mapped[str] = mapped_column(String(1000))
    summary: Mapped[str | None] = mapped_column(Text)
    event_type: Mapped[str | None] = mapped_column(String(32))  # earnings, dividend, rights, ...


# ---------- Shariah ----------


class ShariahMethodology(Base):
    __tablename__ = "shariah_methodologies"
    id: Mapped[int] = mapped_column(primary_key=True)
    code: Mapped[str] = mapped_column(String(48), unique=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str] = mapped_column(Text)
    thresholds: Mapped[dict] = mapped_column(JSONType)
    prohibited_activities: Mapped[list] = mapped_column(JSONType)
    denominator: Mapped[str] = mapped_column(String(32))  # market_cap / total_assets / avg_market_cap_36m
    max_data_age_days: Mapped[int] = mapped_column(Integer, default=190)
    owner_user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"))
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)


class ShariahScreen(Base):
    __tablename__ = "shariah_screens"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    methodology_id: Mapped[int] = mapped_column(ForeignKey("shariah_methodologies.id"), index=True)
    status: Mapped[ShariahStatus] = mapped_column(Enum(ShariahStatus, native_enum=False, length=24))
    business_result: Mapped[dict] = mapped_column(JSONType)
    ratio_results: Mapped[list] = mapped_column(JSONType)  # [{name, value, threshold, op, pass}]
    fundamentals_id: Mapped[int | None] = mapped_column(ForeignKey("fundamentals.id"))
    data_as_of: Mapped[date | None] = mapped_column(Date)
    reviewer_note: Mapped[str | None] = mapped_column(Text)
    details: Mapped[dict | None] = mapped_column(JSONType)  # full engine output for the "Why?" panel
    inputs_digest: Mapped[str | None] = mapped_column(String(32), index=True)
    computed_at: Mapped[datetime] = _now_col()


# ---------- strategies, signals ----------


class Strategy(Base):
    __tablename__ = "strategies"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int | None] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    description: Mapped[str | None] = mapped_column(Text)
    rules: Mapped[dict] = mapped_column(JSONType)  # boolean expression tree
    weights: Mapped[dict] = mapped_column(JSONType)
    level_method: Mapped[str] = mapped_column(String(24), default="swing_atr")
    is_builtin: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = _now_col()


class Signal(Base):
    """Immutable record of what the engine concluded, and from which data."""

    __tablename__ = "signals"
    id: Mapped[int] = mapped_column(primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    strategy_id: Mapped[int | None] = mapped_column(ForeignKey("strategies.id", ondelete="SET NULL"))
    interval: Mapped[str] = mapped_column(String(4))
    ts: Mapped[datetime] = mapped_column(TS, index=True)  # bar the signal is based on
    signal_type: Mapped[SignalType] = mapped_column(Enum(SignalType, native_enum=False, length=16), index=True)
    score: Mapped[float | None] = mapped_column(Float, index=True)
    coverage: Mapped[float | None] = mapped_column(Float)
    score_breakdown: Mapped[dict] = mapped_column(JSONType)
    reasons: Mapped[list] = mapped_column(JSONType)
    warnings: Mapped[list] = mapped_column(JSONType)
    entry_low: Mapped[float | None] = mapped_column(Float)
    entry_high: Mapped[float | None] = mapped_column(Float)
    stop: Mapped[float | None] = mapped_column(Float)
    target1: Mapped[float | None] = mapped_column(Float)
    target2: Mapped[float | None] = mapped_column(Float)
    target3: Mapped[float | None] = mapped_column(Float)
    risk_reward: Mapped[float | None] = mapped_column(Float)
    shariah_screen_id: Mapped[int | None] = mapped_column(ForeignKey("shariah_screens.id"))
    data_as_of: Mapped[datetime] = mapped_column(TS)
    created_at: Mapped[datetime] = _now_col()
    stock: Mapped[Stock] = relationship()


# ---------- user workspace ----------


class Watchlist(Base):
    __tablename__ = "watchlists"
    __table_args__ = (UniqueConstraint("user_id", "name"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    created_at: Mapped[datetime] = _now_col()
    items: Mapped[list["WatchlistStock"]] = relationship(cascade="all, delete-orphan")


class WatchlistStock(Base):
    __tablename__ = "watchlist_stocks"
    watchlist_id: Mapped[int] = mapped_column(ForeignKey("watchlists.id", ondelete="CASCADE"), primary_key=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), primary_key=True)
    note: Mapped[str | None] = mapped_column(String(500))
    added_at: Mapped[datetime] = _now_col()


class Portfolio(Base):
    __tablename__ = "portfolios"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(80))
    base_currency: Mapped[str] = mapped_column(String(3), default="NGN")
    created_at: Mapped[datetime] = _now_col()
    positions: Mapped[list["PortfolioPosition"]] = relationship(cascade="all, delete-orphan")


class PortfolioPosition(Base):
    """Manually entered. The platform never executes trades."""

    __tablename__ = "portfolio_positions"
    id: Mapped[int] = mapped_column(primary_key=True)
    portfolio_id: Mapped[int] = mapped_column(ForeignKey("portfolios.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int] = mapped_column(ForeignKey("stocks.id"), index=True)
    quantity: Mapped[float] = mapped_column(Money)
    avg_entry: Mapped[float] = mapped_column(Money)
    stop: Mapped[float | None] = mapped_column(Money)
    target: Mapped[float | None] = mapped_column(Money)
    opened_at: Mapped[date | None] = mapped_column(Date)
    note: Mapped[str | None] = mapped_column(String(500))
    closed_at: Mapped[date | None] = mapped_column(Date)  # set = closed; kept for realised P/L
    exit_price: Mapped[float | None] = mapped_column(Money)
    created_at: Mapped[datetime] = _now_col()
    stock: Mapped[Stock] = relationship()


class Alert(Base):
    __tablename__ = "alerts"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    stock_id: Mapped[int | None] = mapped_column(ForeignKey("stocks.id", ondelete="CASCADE"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    condition: Mapped[dict] = mapped_column(JSONType)  # e.g. {"type":"price_cross","level":1050,"dir":"up"}
    channels: Mapped[list] = mapped_column(JSONType)  # ["browser","email"]
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=1440)
    last_triggered_at: Mapped[datetime | None] = mapped_column(TS)
    last_evaluated_at: Mapped[datetime | None] = mapped_column(TS)
    state: Mapped[dict | None] = mapped_column(JSONType)  # last observed value, for change-type alerts
    created_at: Mapped[datetime] = _now_col()
    stock: Mapped[Stock | None] = relationship()


class AlertEvent(Base):
    __tablename__ = "alert_events"
    id: Mapped[int] = mapped_column(primary_key=True)
    alert_id: Mapped[int] = mapped_column(ForeignKey("alerts.id", ondelete="CASCADE"), index=True)
    triggered_at: Mapped[datetime] = _now_col()
    payload: Mapped[dict] = mapped_column(JSONType)
    delivered: Mapped[dict | None] = mapped_column(JSONType)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False)


class Backtest(Base):
    __tablename__ = "backtests"
    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    strategy_id: Mapped[int] = mapped_column(ForeignKey("strategies.id", ondelete="CASCADE"))
    universe: Mapped[dict] = mapped_column(JSONType)
    start: Mapped[date] = mapped_column(Date)
    end: Mapped[date] = mapped_column(Date)
    costs_bps: Mapped[float] = mapped_column(Float, default=0)
    slippage_bps: Mapped[float] = mapped_column(Float, default=0)
    status: Mapped[str] = mapped_column(String(16), default="queued")
    metrics: Mapped[dict | None] = mapped_column(JSONType)
    trades: Mapped[list | None] = mapped_column(JSONType)
    error: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = _now_col()
