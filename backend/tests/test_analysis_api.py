from tests.conftest import csrf, register
from tests.test_eodhd import add_dangcem, fake  # noqa: F401  (fixture re-export)


def load(client):
    register(client)
    add_dangcem(client)
    client.get("/api/stocks/XNSA/DANGCEM")  # stores 260 bars from the fake provider


def test_analysis_explains_every_rule(client, fake):  # noqa: F811
    load(client)
    a = client.get("/api/stocks/XNSA/DANGCEM/analysis").json()
    assert a["available"] is True
    sig = a["signal"]
    assert sig["signal_type"] in ("BUY_SETUP", "WATCHLIST", "WAIT", "AVOID")
    assert len(sig["rules"]) >= 18 and all("label" in r and "passed" in r for r in sig["rules"])
    assert set(sig["breakdown"]) == {"trend", "momentum", "volume", "price_action", "risk", "market", "liquidity"}
    assert sig["timeframes"]["15m"].startswith("Data unavailable")
    assert "weekly" in sig["timeframes"] and "agreement" in sig["timeframes"]
    assert any("Shariah" in w for w in sig["warnings"])
    assert len(a["series"]["t"]) == len(a["series"]["rsi"])


def test_signals_persisted_and_listed(client, fake):  # noqa: F811
    load(client)
    client.get("/api/stocks/XNSA/DANGCEM/analysis")
    client.get("/api/stocks/XNSA/DANGCEM/analysis")  # same data: no duplicate row
    rows = client.get("/api/signals").json()["results"]
    assert len(rows) == 1 and rows[0]["ticker"] == "DANGCEM"


def test_scanner_filters_and_never_calls_provider(client, fake):  # noqa: F811
    load(client)
    calls_before = len(fake.calls)
    all_ = client.post("/api/scanner", json={"market": "NG"}, headers=csrf(client)).json()
    assert all_["scanned"] == 1 and len(all_["results"]) == 1
    none = client.post("/api/scanner", json={"market": "NG", "rsi_max": 1}, headers=csrf(client)).json()
    assert none["results"] == []
    us = client.post("/api/scanner", json={"market": "US"}, headers=csrf(client)).json()
    assert us["results"] == []
    assert len(fake.calls) == calls_before
    bad = client.post("/api/scanner", json={"signal_types": ["MOON"]}, headers=csrf(client))
    assert bad.status_code == 422


def test_custom_weights_change_score(client, fake):  # noqa: F811
    load(client)
    before = client.get("/api/stocks/XNSA/DANGCEM/analysis").json()["signal"]["score"]
    r = client.put("/api/scoring", json={"weights": {"trend": 100, "momentum": 0, "volume": 0, "price_action": 0,
                                                       "risk": 0, "market": 0, "liquidity": 0}}, headers=csrf(client))
    assert r.status_code == 200
    after = client.get("/api/stocks/XNSA/DANGCEM/analysis").json()
    assert after["strategy"] == "My scoring weights"
    trend = after["signal"]["breakdown"]["trend"]
    assert after["signal"]["score"] == round(trend["pct"] * 100, 1)
    assert client.put("/api/scoring", json={"weights": {"luck": 5}}, headers=csrf(client)).status_code == 422
    client.delete("/api/scoring", headers=csrf(client))
    assert client.get("/api/stocks/XNSA/DANGCEM/analysis").json()["signal"]["score"] == before


def test_dashboard_regime_uses_index_data(client, fake):  # noqa: F811
    register(client)
    d = client.get("/api/dashboard").json()  # fetches S&P 500 bars from the fake provider
    us = d["market_regime"]["US"]
    assert us["status"] in ("END_OF_DAY", "UNAVAILABLE")
    if us["status"] == "UNAVAILABLE":
        assert "60" in us["note"]  # 30 fake index bars are fewer than the 60 the classifier needs
    assert d["market_regime"]["NG"]["status"] == "UNAVAILABLE"
