"""EODHD client (https://eodhd.com/financial-apis/).

Facts relied on (EODHD docs, checked 28 Sep 2026):
- EOD:     GET /eod/{CODE}.{EXCHANGE}?api_token=&fmt=json&from=&to=&period=d|w|m
           -> [{date, open, high, low, close, adjusted_close, volume}]
- Search:  GET /search/{query}?api_token=&fmt=json&limit=&type=&exchange=
- Symbols: GET /exchange-symbol-list/{EXCHANGE}?api_token=&fmt=json
- Each request costs one API call, including 404s. 401 = bad key, 403 = not entitled.
- An empty 200 array is not an error (window outside data, or renamed ticker).

The API key is sent only as a query parameter to eodhd.com and is scrubbed from
every error message and log line.
"""

from __future__ import annotations

import logging
from collections.abc import Callable
from datetime import UTC, date, datetime
from urllib.parse import quote

import httpx

from app.providers.base import (
    Bar,
    Bars,
    Instrument,
    MarketDataProvider,
    ProviderCapabilities,
    ProviderUnavailable,
    Quote,
)

log = logging.getLogger("hss.eodhd")

# Our exchange MIC -> EODHD exchange suffix.
MIC_TO_EODHD = {
    "XNSA": "XNSA",
    "XNYS": "US",
    "XNAS": "US",
    "XASE": "US",
    "XLON": "LSE",
    "XTSE": "TO",
    "XSAU": "SR",
    "XDFM": "DFM",  # verify with exchanges-list on your plan
    "XKLS": "KLSE",
    "XIDX": "JK",
    "XETR": "XETRA",
    "INDX": "INDX",
}

# EODHD "Exchange" field in search / symbol-list results -> our MIC.
EODHD_TO_MIC = {
    "XNSA": "XNSA",
    "NASDAQ": "XNAS",
    "NYSE": "XNYS",
    "NYSE MKT": "XASE",
    "AMEX": "XASE",
    "NYSE ARCA": "XASE",
    "BATS": "XASE",
    "LSE": "XLON",
    "TO": "XTSE",
    "SR": "XSAU",
    "DFM": "XDFM",
    "KLSE": "XKLS",
    "JK": "XIDX",
    "XETRA": "XETR",
    "INDX": "INDX",
}

TYPE_MAP = {"common stock": "stock", "preferred stock": "stock", "etf": "etf", "index": "index", "fund": "fund"}
INTERVAL_TO_PERIOD = {"1d": "d", "1w": "w", "1mo": "m"}


class EODHDProvider(MarketDataProvider):
    code = "eodhd"
    name = "EODHD"

    def __init__(self, api_key: str | None, base_url: str = "https://eodhd.com/api", timeout: float = 20.0,
                 budget: Callable[[str], None] | None = None, transport: httpx.BaseTransport | None = None):
        self._key = api_key
        self._base = base_url.rstrip("/")
        self._timeout = timeout
        self._budget = budget  # called before every request; raises ProviderUnavailable when exhausted
        self._transport = transport  # injected in tests

    # ----- interface -----

    @property
    def capabilities(self) -> ProviderCapabilities:
        return ProviderCapabilities(
            markets=frozenset({"NG", "US", "UK", "GCC", "MY", "ID", "CA", "EU", "GL"}),
            intervals=frozenset({"1d", "1w", "1mo"}),
            realtime=False,
            delay_minutes=None,  # end-of-day
            fundamentals=True,
            news=True,
        )

    def is_configured(self) -> bool:
        return bool(self._key)

    def reason(self) -> str:
        return "EODHD: API key not set (EODHD_API_KEY)" if not self._key else "EODHD: configured"

    def symbol_for(self, ticker: str, mic: str) -> str:
        suffix = MIC_TO_EODHD.get(mic)
        if not suffix:
            raise ProviderUnavailable(f"EODHD: exchange {mic} is not mapped")
        return f"{ticker.upper()}.{suffix}"

    def get_bars(self, ticker: str, exchange: str, interval: str, start: datetime | date,
                 end: datetime | date) -> Bars:
        period = INTERVAL_TO_PERIOD.get(interval)
        if not period:
            raise ProviderUnavailable(f"EODHD: interval {interval} not supported on end-of-day plans")
        symbol = self.symbol_for(ticker, exchange)
        rows = self._get(f"/eod/{symbol}", "eod", {
            "fmt": "json", "period": period, "order": "a",
            "from": _d(start).isoformat(), "to": _d(end).isoformat(),
        })
        if not isinstance(rows, list):
            raise ProviderUnavailable("EODHD: unexpected response shape for EOD data")
        bars = []
        for r in rows:
            try:
                close = float(r["close"])
                bars.append(Bar(
                    ts=datetime.fromisoformat(r["date"]).replace(tzinfo=UTC),
                    open=_f(r.get("open")), high=_f(r.get("high")), low=_f(r.get("low")),
                    close=close, volume=_f(r.get("volume")), adj_close=_f(r.get("adjusted_close")),
                ))
            except (KeyError, TypeError, ValueError):
                log.warning("EODHD: skipped malformed bar for %s: %r", symbol, r)
        return Bars(ticker=ticker.upper(), exchange=exchange, interval=interval, bars=bars, source=self.code,
                    fetched_at=datetime.now(UTC))

    def get_quote(self, ticker: str, exchange: str) -> Quote:
        # Free/EOD plans have no live quote; the service derives the quote from stored bars.
        raise ProviderUnavailable("EODHD: live quotes need a paid plan; using last end-of-day bar instead")

    def search(self, query: str, limit: int = 20, instrument_type: str | None = None,
               exchange: str | None = None) -> list[Instrument]:
        q = query.strip()
        if not q or len(q) > 64:
            return []
        params = {"fmt": "json", "limit": str(max(1, min(limit, 50)))}
        if instrument_type:
            params["type"] = instrument_type
        if exchange:
            params["exchange"] = MIC_TO_EODHD.get(exchange, exchange)
        rows = self._get(f"/search/{_quote(q)}", "search", params)
        return [i for i in (_instrument(r) for r in rows or []) if i]

    def list_exchange(self, mic: str) -> list[Instrument]:
        suffix = MIC_TO_EODHD.get(mic)
        if not suffix or suffix == "US":
            # US list is ~50,000 symbols across venues; import via search instead.
            raise ProviderUnavailable(f"EODHD: bulk symbol import not offered for {mic}")
        rows = self._get(f"/exchange-symbol-list/{suffix}", "exchange-symbol-list", {"fmt": "json"})
        return [i for i in (_instrument(r, default_exchange=suffix) for r in rows or []) if i]

    # ----- transport -----

    def _get(self, path: str, endpoint: str, params: dict[str, str]):
        if not self._key:
            raise ProviderUnavailable(self.reason())
        if self._budget:
            self._budget(endpoint)
        try:
            with httpx.Client(timeout=self._timeout, transport=self._transport) as c:
                r = c.get(f"{self._base}{path}", params={**params, "api_token": self._key})
        except httpx.HTTPError as e:
            raise ProviderUnavailable(f"EODHD: network error ({type(e).__name__})") from None
        if r.status_code == 401:
            raise ProviderUnavailable("EODHD: API key rejected (401)")
        if r.status_code == 403:
            raise ProviderUnavailable("EODHD: your plan is not entitled to this symbol or endpoint (403)")
        if r.status_code == 404:
            raise ProviderUnavailable("EODHD: symbol not found (404)")
        if r.status_code == 429:
            raise ProviderUnavailable("EODHD: provider rate limit reached (429)")
        if r.status_code >= 400:
            raise ProviderUnavailable(f"EODHD: HTTP {r.status_code}")
        try:
            return r.json()
        except ValueError:
            raise ProviderUnavailable("EODHD: response was not JSON") from None


def _quote(q: str) -> str:
    return quote(q, safe="")


def _d(v: datetime | date) -> date:
    return v.date() if isinstance(v, datetime) else v


def _f(v) -> float | None:
    if v is None or v == "":
        return None
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


def _instrument(r: dict, default_exchange: str | None = None) -> Instrument | None:
    code = r.get("Code")
    ex = (r.get("Exchange") or default_exchange or "").upper()
    mic = EODHD_TO_MIC.get(ex)
    if not code or not mic:
        return None
    return Instrument(
        ticker=str(code).upper(), exchange=mic, name=r.get("Name") or str(code),
        country=_country(r.get("Country")), currency=r.get("Currency"),
        extra={"eodhd_symbol": f"{code}.{MIC_TO_EODHD[mic]}", "type": TYPE_MAP.get(str(r.get("Type", "")).lower(),
               str(r.get("Type", "")).lower() or "stock"), "isin": r.get("ISIN") or r.get("Isin"),
               "previous_close": r.get("previousClose"), "previous_close_date": r.get("previousCloseDate")},
    )


_COUNTRIES = {"nigeria": "NG", "usa": "US", "united states": "US", "uk": "GB", "united kingdom": "GB",
              "canada": "CA", "saudi arabia": "SA", "united arab emirates": "AE", "malaysia": "MY",
              "indonesia": "ID", "germany": "DE"}


def _country(name: str | None) -> str | None:
    return _COUNTRIES.get((name or "").strip().lower())
