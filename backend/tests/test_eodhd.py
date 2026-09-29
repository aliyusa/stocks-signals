"""EODHD integration tests against a mocked HTTP transport (no network, no real key)."""

import json
from datetime import UTC, date, datetime, timedelta

import httpx
import pytest

from app.core.config import get_settings
from app.services.market_calendar import expected_last_session, previous_weekday
from tests.conftest import csrf, register

FAKE_KEY = "test-key-SHOULD-NEVER-LEAK"


def weekdays_back(end: date, n: int) -> list[date]:
    out, d = [], end
    while len(out) < n:
        if d.weekday() < 5:
            out.append(d)
        d -= timedelta(days=1)
    return sorted(out)


class FakeEODHD:
    """Records calls; serves canned responses like eodhd.com would."""

    def __init__(self, flat: bool = False):
        self.calls: list[str] = []
        self.flat = flat
        now = datetime.now(UTC)
        self.last_ngx = expected_last_session(now, "Africa/Lagos", "14:30")
        self.last_us = expected_last_session(now, "America/New_York", "16:00")

    def bars(self, last: date, n: int = 260, base: float = 1000.0):
        out = []
        for i, d in enumerate(weekdays_back(last, n)):
            c = base if self.flat else base + i
            out.append({"date": d.isoformat(), "open": c, "high": c if self.flat else c + 5,
                        "low": c if self.flat else c - 5, "close": c, "adjusted_close": c, "volume": 1000 + i})
        return out

    def handler(self, request: httpx.Request) -> httpx.Response:
        assert request.url.params["api_token"] == FAKE_KEY
        path = request.url.path.removeprefix("/api")
        self.calls.append(path)
        if path.startswith("/eod/FORBIDDEN"):
            return httpx.Response(403, text="Forbidden")
        if path == "/eod/DANGCEM.XNSA":
            return httpx.Response(200, json=self.bars(self.last_ngx))
        if path == "/eod/GSPC.INDX" or path == "/eod/IXIC.INDX":
            return httpx.Response(200, json=self.bars(self.last_us, 30, 6000))
        if path.startswith("/search/"):
            return httpx.Response(200, json=[
                {"Code": "DANGCEM", "Exchange": "XNSA", "Name": "Dangote Cement Plc", "Type": "Common Stock",
                 "Country": "Nigeria", "Currency": "NGN", "ISIN": "NGDANGCEM008"},
                {"Code": "DANGSUGAR", "Exchange": "XNSA", "Name": "Dangote Sugar Refinery", "Type": "Common Stock",
                 "Country": "Nigeria", "Currency": "NGN", "ISIN": None},
                {"Code": "ZZZ", "Exchange": "UNKNOWNX", "Name": "Unmapped venue", "Type": "Common Stock"},
            ])
        if path == "/exchange-symbol-list/XNSA":
            return httpx.Response(200, json=[
                {"Code": "MTNN", "Name": "MTN Nigeria", "Country": "Nigeria", "Exchange": "XNSA",
                 "Currency": "NGN", "Type": "Common Stock", "Isin": None},
                {"Code": "SOMEBOND", "Name": "A bond", "Country": "Nigeria", "Exchange": "XNSA",
                 "Currency": "NGN", "Type": "Bond", "Isin": None},
            ])
        return httpx.Response(404, text="Ticker Not Found")


@pytest.fixture
def fake(monkeypatch):
    import app.providers.registry as reg

    fake = FakeEODHD()
    settings = get_settings().model_copy(update={"eodhd_api_key": FAKE_KEY, "eodhd_daily_call_limit": 20})
    real_build = reg.build_providers

    def build(s, db=None):
        providers = real_build(s, db)
        providers["eodhd"]._transport = httpx.MockTransport(fake.handler)
        return providers

    monkeypatch.setattr(reg, "build_providers", build)
    monkeypatch.setattr(reg, "get_settings", lambda: settings)
    return fake


def add_dangcem(client):
    r = client.post("/api/search/provider", json={"q": "dangote"}, headers=csrf(client))
    assert r.status_code == 200, r.text
    return r.json()


def test_provider_search_adds_to_universe_and_costs_one_call(client, fake):
    register(client)
    body = add_dangcem(client)
    tickers = {x["ticker"] for x in body["results"]}
    assert tickers == {"DANGCEM", "DANGSUGAR"}  # unmapped venue dropped, not guessed
    assert body["usage"]["used"] == 1
    # local search now finds it for free
    local = client.get("/api/search", params={"q": "DANG"}).json()["results"]
    assert local[0]["ticker"] in {"DANGCEM", "DANGSUGAR"}
    assert fake.calls == ["/search/dangote"]


def test_detail_fetches_once_then_serves_from_store(client, fake):
    register(client)
    add_dangcem(client)
    d = client.get("/api/stocks/XNSA/DANGCEM").json()
    assert d["refresh"]["status"] == "fetched"
    assert d["refresh"]["new_bars"] == 260
    assert d["quote"]["status"] == "END_OF_DAY"
    assert d["quote"]["source"] == "EODHD"
    assert d["quote"]["price"] == pytest.approx(1259.0)
    assert d["quote"]["change_pct"] == pytest.approx((1259 / 1258 - 1) * 100)
    d2 = client.get("/api/stocks/XNSA/DANGCEM").json()
    assert d2["refresh"]["status"] == "fresh"
    assert fake.calls.count("/eod/DANGCEM.XNSA") == 1
    assert d2["usage"]["used"] == 2  # 1 search + 1 eod


def test_bars_endpoint_ranges(client, fake):
    register(client)
    add_dangcem(client)
    client.get("/api/stocks/XNSA/DANGCEM")
    one_m = client.get("/api/stocks/XNSA/DANGCEM/bars", params={"range": "1M"}).json()["bars"]
    all_ = client.get("/api/stocks/XNSA/DANGCEM/bars", params={"range": "MAX"}).json()["bars"]
    assert 19 <= len(one_m) <= 24
    assert len(all_) == 260
    assert all_[0]["t"] < all_[-1]["t"]
    assert client.get("/api/stocks/XNSA/DANGCEM/bars", params={"range": "2Y"}).status_code == 422


def test_budget_exhaustion_keeps_stored_data(client, fake, monkeypatch):
    import app.providers.registry as reg

    register(client)
    add_dangcem(client)
    client.get("/api/stocks/XNSA/DANGCEM")
    tight = get_settings().model_copy(update={"eodhd_api_key": FAKE_KEY, "eodhd_daily_call_limit": 2})
    monkeypatch.setattr(reg, "get_settings", lambda: tight)
    r = client.post("/api/stocks/XNSA/DANGCEM/refresh", headers=csrf(client)).json()
    assert r["status"] == "failed"
    assert "daily call budget reached" in r["message"]
    assert r["quote"]["price"] == pytest.approx(1259.0)  # stored data still served


def test_forbidden_symbol_is_reported_and_key_never_leaks(client, fake):
    from sqlalchemy import select

    from app.core.db import SessionLocal
    from app.models.entities import AuditLog, DataSource, Exchange, Stock

    register(client)
    with SessionLocal() as db:
        ex = db.scalar(select(Exchange).where(Exchange.code == "XNSA"))
        db.add(Stock(ticker="FORBIDDEN", exchange_id=ex.id, name="Not entitled"))
        db.commit()
    r = client.get("/api/stocks/XNSA/FORBIDDEN")
    body = r.text
    assert r.json()["refresh"]["status"] == "failed"
    assert "403" in r.json()["refresh"]["message"]
    assert r.json()["quote"]["status"] == "UNAVAILABLE"
    assert FAKE_KEY not in body
    with SessionLocal() as db:
        src = db.scalar(select(DataSource).where(DataSource.code == "eodhd"))
        assert src.last_error and FAKE_KEY not in src.last_error
        for a in db.scalars(select(AuditLog)):
            assert FAKE_KEY not in json.dumps(a.details or {})


def test_flat_ngx_bars_trigger_data_quality_warning(client, monkeypatch):
    import app.providers.registry as reg

    fake = FakeEODHD(flat=True)
    settings = get_settings().model_copy(update={"eodhd_api_key": FAKE_KEY})
    real_build = reg.build_providers

    def build(s, db=None):
        p = real_build(s, db)
        p["eodhd"]._transport = httpx.MockTransport(fake.handler)
        return p

    monkeypatch.setattr(reg, "build_providers", build)
    monkeypatch.setattr(reg, "get_settings", lambda: settings)
    register(client)
    add_dangcem(client)
    d = client.get("/api/stocks/XNSA/DANGCEM").json()
    assert d["data_quality"]["zero_range_share_60"] == 1.0
    assert any("high = low" in w for w in d["data_quality"]["warnings"])


def test_import_exchange_skips_non_equities(client, fake):
    register(client)
    r = client.post("/api/exchanges/XNSA/import", headers=csrf(client)).json()
    assert r["imported"] == 1
    assert client.get("/api/search", params={"q": "MTNN"}).json()["results"][0]["name"] == "MTN Nigeria"
    assert client.post("/api/exchanges/xnsa/import", headers=csrf(client)).status_code == 422


def test_dashboard_index_cards_with_key(client, fake):
    register(client)
    cards = {c["symbol"]: c["change_pct"] for c in client.get("/api/dashboard").json()["index_cards"]}
    assert cards["GSPC.INDX"]["status"] == "END_OF_DAY"
    assert cards["GSPC.INDX"]["level"] == pytest.approx(6029.0)
    assert cards["NGXASI"]["status"] == "UNAVAILABLE"  # symbol intentionally not guessed
    assert "not set" in cards["NGXASI"]["note"]


def test_unknown_stock_404_and_validation(client, fake):
    register(client)
    assert client.get("/api/stocks/XNSA/NOPE").status_code == 404
    assert client.get("/api/stocks/XNSA/bad%20ticker!").status_code == 422


def test_calendar_rules():
    # Saturday 26 Sep 2026 and Sunday 27 Sep 2026 -> Friday 25 Sep 2026
    for day in (26, 27):
        now = datetime(2026, 9, day, 12, 0, tzinfo=UTC)
        assert expected_last_session(now, "Africa/Lagos", "14:30") == date(2026, 9, 25)
    # Monday 28 Sep before publish buffer -> Friday; after -> Monday
    assert expected_last_session(datetime(2026, 9, 28, 12, 0, tzinfo=UTC), "Africa/Lagos", "14:30") == date(2026, 9, 25)
    assert expected_last_session(datetime(2026, 9, 28, 17, 0, tzinfo=UTC), "Africa/Lagos", "14:30") == date(2026, 9, 28)
    assert previous_weekday(date(2026, 9, 28)) == date(2026, 9, 25)


def test_freshness_stale():
    from types import SimpleNamespace

    from app.services.prices import freshness

    stock = SimpleNamespace(exchange=SimpleNamespace(timezone="Africa/Lagos", close_time="14:30"))
    now = datetime(2026, 9, 28, 17, 0, tzinfo=UTC)
    assert freshness(stock, date(2026, 9, 28), now)[0].value == "END_OF_DAY"
    status, note = freshness(stock, date(2026, 9, 25), now)
    assert status.value == "STALE" and "holiday" in note
    status, note = freshness(stock, date(2026, 9, 21), now)
    assert status.value == "STALE" and "5 sessions" in note
    assert freshness(stock, None, now)[0].value == "UNAVAILABLE"


def test_forced_refresh_overlap_does_not_duplicate(client, fake):
    register(client)
    add_dangcem(client)
    client.get("/api/stocks/XNSA/DANGCEM")
    r = client.post("/api/stocks/XNSA/DANGCEM/refresh", headers=csrf(client)).json()
    assert r["status"] == "fetched" and r["new_bars"] == 0
    assert len(client.get("/api/stocks/XNSA/DANGCEM/bars", params={"range": "MAX"}).json()["bars"]) == 260


def test_cooldown_stops_repeat_fetches_of_lagging_stock(client, fake):
    """A stock whose provider data never reaches the expected session must not drain the budget."""
    fake.last_ngx = previous_weekday(previous_weekday(fake.last_ngx))  # provider is 2 sessions behind
    register(client)
    add_dangcem(client)
    first = client.get("/api/stocks/XNSA/DANGCEM").json()
    assert first["refresh"]["status"] == "fetched"
    assert first["quote"]["status"] == "STALE"
    for _ in range(3):
        again = client.get("/api/stocks/XNSA/DANGCEM").json()
        assert again["refresh"]["status"] == "cooldown"
    assert fake.calls.count("/eod/DANGCEM.XNSA") == 1
    forced = client.post("/api/stocks/XNSA/DANGCEM/refresh", headers=csrf(client)).json()
    assert forced["status"] == "fetched"  # manual refresh bypasses the cooldown


def test_api_key_is_redacted_from_logs(client, fake, caplog):
    import logging

    from app.core.log_redact import RedactSecretsFilter

    register(client)
    add_dangcem(client)
    with caplog.at_level(logging.DEBUG):
        client.get("/api/stocks/XNSA/DANGCEM")
    assert FAKE_KEY not in caplog.text
    rec = logging.LogRecord("httpx", logging.INFO, "", 0, 'GET https://eodhd.com/api/eod/X?fmt=json&api_token=%s "200"',
                            (FAKE_KEY,), None)
    RedactSecretsFilter().filter(rec)
    assert FAKE_KEY not in rec.getMessage() and "api_token=***" in rec.getMessage()
