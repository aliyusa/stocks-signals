"""Chooses a provider per market from configuration.

EODHD is implemented (Phase 2). The others are interface stubs that always report
'not configured' until their clients are written. No stub ever returns data.
"""

from datetime import datetime

from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.providers.base import (
    Bars,
    Instrument,
    MarketDataProvider,
    ProviderCapabilities,
    ProviderUnavailable,
    Quote,
)
from app.providers.eodhd import EODHDProvider
from app.services.usage import CallBudget

ALL_MARKETS = frozenset({"NG", "US", "UK", "GCC", "MY", "ID", "CA", "EU", "GL"})


class _PendingProvider(MarketDataProvider):
    """Declared provider whose client is implemented in Phase 2."""

    def __init__(self, code: str, name: str, key: str | None, caps: ProviderCapabilities, needs_key: bool = True):
        self.code, self.name, self._key, self._caps, self._needs_key = code, name, key, caps, needs_key

    @property
    def capabilities(self) -> ProviderCapabilities:
        return self._caps

    def is_configured(self) -> bool:
        return False  # becomes key-dependent when the client is implemented

    def reason(self) -> str:
        if self._needs_key and not self._key:
            return f"{self.name}: API key not set"
        return f"{self.name}: client not yet implemented (Phase 2)"

    def get_bars(self, ticker: str, exchange: str, interval: str, start: datetime, end: datetime) -> Bars:
        raise ProviderUnavailable(self.reason())

    def get_quote(self, ticker: str, exchange: str) -> Quote:
        raise ProviderUnavailable(self.reason())

    def search(self, query: str) -> list[Instrument]:
        raise ProviderUnavailable(self.reason())


def build_providers(s: Settings, db: Session | None = None) -> dict[str, MarketDataProvider]:
    eod = frozenset({"1d", "1w"})
    return {
        "ngx": _PendingProvider(
            "ngx", "NGX Market Data API", s.ngx_api_key,  # licence required
            ProviderCapabilities(frozenset({"NG"}), eod | {"15m", "1h"}, realtime=True, fundamentals=False, news=True),
        ),
        "eodhd": EODHDProvider(
            s.eodhd_api_key, base_url=s.eodhd_base_url, timeout=s.eodhd_timeout_seconds,
            budget=CallBudget(db, "eodhd", s.eodhd_daily_call_limit) if db is not None else None,
        ),
        "fmp": _PendingProvider(
            "fmp", "Financial Modeling Prep", s.fmp_api_key,
            ProviderCapabilities(frozenset({"US", "UK", "CA"}), eod, fundamentals=True, news=True),
        ),
        "twelvedata": _PendingProvider(
            "twelvedata", "Twelve Data", s.twelvedata_api_key,
            ProviderCapabilities(frozenset({"US"}), eod | {"15m", "1h", "4h"}, realtime=True),
        ),
        "csv": _PendingProvider(
            "csv", "CSV import", None, ProviderCapabilities(ALL_MARKETS, eod), needs_key=False,
        ),
    }


class ProviderRegistry:
    def __init__(self, settings: Settings | None = None, db: Session | None = None,
                 providers: dict[str, MarketDataProvider] | None = None):
        self.settings = settings or get_settings()
        self.providers = providers if providers is not None else build_providers(self.settings, db)

    def route(self, market_code: str) -> list[str]:
        return [p.strip() for p in self.settings.provider_routes.get(market_code, "").split(",") if p.strip()]

    def for_market(self, market_code: str) -> MarketDataProvider | None:
        for code in self.route(market_code):
            p = self.providers.get(code)
            if p and p.is_configured() and market_code in p.capabilities.markets:
                return p
        return None

    def explain(self, market_code: str) -> list[str]:
        """Human-readable reasons why no provider serves this market."""
        return [self.providers[c].reason() for c in self.route(market_code) if c in self.providers]
