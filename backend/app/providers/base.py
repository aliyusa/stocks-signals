"""Market-data abstraction layer.

Engines and services depend only on these interfaces, never on a vendor SDK.
A provider must raise ProviderUnavailable rather than return guessed data.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime

from app.models.entities import DataStatus


class ProviderUnavailable(Exception):
    """Raised when a provider cannot serve a request (no key, no coverage, network error)."""


@dataclass(frozen=True)
class ProviderCapabilities:
    markets: frozenset[str]
    intervals: frozenset[str]
    realtime: bool = False
    delay_minutes: int | None = None  # None = end-of-day
    fundamentals: bool = False
    news: bool = False


@dataclass
class Bar:
    ts: datetime
    open: float | None
    high: float | None
    low: float | None
    close: float
    volume: float | None
    adj_close: float | None = None


@dataclass
class Bars:
    ticker: str
    exchange: str
    interval: str
    bars: list[Bar]
    source: str
    fetched_at: datetime


@dataclass
class Quote:
    ticker: str
    exchange: str
    price: float
    change_pct: float | None
    as_of: datetime
    source: str
    status: DataStatus


@dataclass
class Instrument:
    ticker: str
    exchange: str
    name: str
    country: str | None = None
    currency: str | None = None
    sector: str | None = None
    extra: dict = field(default_factory=dict)


class MarketDataProvider(ABC):
    code: str
    name: str

    @property
    @abstractmethod
    def capabilities(self) -> ProviderCapabilities: ...

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def get_bars(self, ticker: str, exchange: str, interval: str, start: datetime, end: datetime) -> Bars: ...

    @abstractmethod
    def get_quote(self, ticker: str, exchange: str) -> Quote: ...

    @abstractmethod
    def search(self, query: str) -> list[Instrument]: ...


class FundamentalDataProvider(ABC):
    code: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def get_fundamentals(self, ticker: str, exchange: str) -> list[dict]: ...


class NewsProvider(ABC):
    code: str

    @abstractmethod
    def is_configured(self) -> bool: ...

    @abstractmethod
    def get_news(self, ticker: str, exchange: str, limit: int = 20) -> list[dict]: ...
