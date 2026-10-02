from datetime import UTC, date, datetime, timedelta

from app.core.db import SessionLocal
from app.engines.signals import compute, evaluate
from app.models.entities import Alert
from app.services import alerts as alerts_svc
from tests.conftest import csrf, register
from tests.test_eodhd import add_dangcem, fake  # noqa: F401  (fixture re-export)

BASE = "/api/stocks/XNSA/DANGCEM"
REF = {"exchange": "XNSA", "ticker": "DANGCEM"}


def setup(client):
    register(client)
    add_dangcem(client)
    return client.get(BASE).json()["quote"]["price"]


def test_watchlist_crud_and_privacy(client, fake):  # noqa: F811
    setup(client)
    h = csrf(client)
    wid = client.post("/api/watchlists", json={"name": "NGX core"}, headers=h).json()["id"]
    assert client.post("/api/watchlists", json={"name": "NGX core"}, headers=h).status_code == 409
    assert client.post(f"/api/watchlists/{wid}/items", json={**REF, "note": "Cement"}, headers=h).status_code == 201
    w = client.get("/api/watchlists").json()["watchlists"][0]
    item = w["items"][0]
    assert item["ticker"] == "DANGCEM" and item["note"] == "Cement" and item["shariah"] == "NOT_SCREENED"
    assert item["quote"]["price"] is not None
    assert client.get(f"{BASE}/membership").json()["watchlists"][0]["contains"] is True
    client.delete(f"/api/watchlists/{wid}/items/XNSA/DANGCEM", headers=h)
    assert client.get("/api/watchlists").json()["watchlists"][0]["items"] == []
    client.post("/api/auth/logout", headers=h)
    register(client, email="other@example.com")
    assert client.get("/api/watchlists").json()["watchlists"] == []
    assert client.delete(f"/api/watchlists/{wid}", headers=csrf(client)).status_code == 404


def test_portfolio_pl_hold_and_sell(client, fake):  # noqa: F811
    price = setup(client)
    h = csrf(client)
    pid = client.post("/api/portfolios", json={"name": "Main", "base_currency": "NGN"}, headers=h).json()["id"]
    bad = {**REF, "quantity": 10, "avg_entry": price, "stop": price * 2, "target": price * 1.5}
    assert client.post(f"/api/portfolios/{pid}/positions", json=bad, headers=h).status_code == 422
    body = {**REF, "quantity": 100, "avg_entry": price * 0.9, "stop": price * 0.5, "target": price * 3,
            "opened_at": (date.today() - timedelta(days=30)).isoformat()}
    pos_id = client.post(f"/api/portfolios/{pid}/positions", json=body, headers=h).json()["id"]
    p = client.get("/api/portfolios").json()["portfolios"][0]
    row = p["open"][0]
    assert abs(row["pl"] - (price - price * 0.9) * 100) < 1e-6
    assert p["totals"]["NGN"]["value"] == row["value"]
    assert row["signal"]["type"] in ("HOLD", "SELL_EXIT")
    a = client.get(f"{BASE}/analysis").json()["signal"]
    assert a["signal_type"] in ("HOLD", "SELL_EXIT") and len(a["exit_checks"]) == 7

    # a stop above the close is hit, so the holding is rated SELL / EXIT with the reason shown
    client.put(f"/api/positions/{pos_id}", json={"quantity": 100, "avg_entry": price * 0.9, "stop": price * 1.01,
                                                  "target": price * 3}, headers=h)
    a = client.get(f"{BASE}/analysis").json()["signal"]
    assert a["signal_type"] == "SELL_EXIT"
    assert any(x["code"] == "stop_hit" and x["triggered"] for x in a["exit_checks"])

    r = client.post(f"/api/positions/{pos_id}/close", json={"exit_price": price, "closed_at": date.today().isoformat()},
                    headers=h)
    assert r.status_code == 200
    p = client.get("/api/portfolios").json()["portfolios"][0]
    assert p["open"] == [] and abs(p["totals"]["NGN"]["realised"] - (price - price * 0.9) * 100) < 1e-6
    a = client.get(f"{BASE}/analysis").json()["signal"]
    assert a["signal_type"] not in ("HOLD", "SELL_EXIT")  # nothing open any more


def test_alert_fires_once_per_cooldown(client, fake):  # noqa: F811
    setup(client)
    h = csrf(client)
    r = client.post("/api/alerts", json={**REF, "condition": {"type": "price_above", "level": 0.01},
                                         "channels": ["in_app", "browser"], "cooldown_minutes": 60}, headers=h)
    assert r.status_code == 201, r.text
    aid = r.json()["id"]
    ev = client.get("/api/alerts/events").json()["events"]
    assert len(ev) == 1 and ev[0]["browser"] and "DANGCEM" in ev[0]["payload"]["title"]
    assert client.post("/api/alerts/check", headers=h).json()["fired"] == 0  # inside the cooldown
    with SessionLocal() as db:
        a = db.get(Alert, aid)
        later = datetime.now(UTC) + timedelta(hours=2)
        assert alerts_svc.evaluate(db, [a], now=later) == []  # cooldown over, but same bar: no repeat
        a.state = {**a.state, "last_fired_bar": "2000-01-01"}  # a new bar has arrived
        db.commit()
        assert len(alerts_svc.evaluate(db, [a], now=later)) == 1
        assert alerts_svc.evaluate(db, [a], now=later + timedelta(minutes=5)) == []
    assert client.get("/api/alerts").json()["unread"] == 2
    client.post("/api/alerts/events/read", json={"all": True}, headers=h)
    assert client.get("/api/alerts").json()["unread"] == 0


def test_alert_validation_and_email_not_configured(client, fake):  # noqa: F811
    setup(client)
    h = csrf(client)
    assert client.post("/api/alerts", json={**REF, "condition": {"type": "price_above"}}, headers=h).status_code == 422
    assert client.post("/api/alerts", json={**REF, "condition": {"type": "moon"}}, headers=h).status_code == 422
    assert client.post("/api/alerts", json={**REF, "condition": {"type": "signal_is", "signal": "RICH"}},
                       headers=h).status_code == 422
    r = client.post("/api/alerts", json={**REF, "condition": {"type": "price_below", "level": 1e12},
                                         "channels": ["email"]}, headers=h)
    assert r.json()["channels"] == ["email", "in_app"]
    ev = client.get("/api/alerts/events").json()["events"][0]
    assert ev["delivered"]["email"] == "not configured"
    assert client.get("/api/alerts/options").json()["channels"]["email"] is False


def test_daily_job_requires_secret(client, fake, monkeypatch):  # noqa: F811
    setup(client)
    assert client.get("/api/cron/daily").status_code == 404  # no secret configured: job is off
    from app.core.config import get_settings
    monkeypatch.setattr(get_settings(), "cron_secret", "s3cret-value-for-test")
    assert client.get("/api/cron/daily", headers={"Authorization": "Bearer wrong"}).status_code == 404
    r = client.get("/api/cron/daily", headers={"Authorization": "Bearer s3cret-value-for-test"})
    assert r.status_code == 200 and "alerts_fired" in r.json()


def test_exit_checks_are_explained():
    bars = [{"t": date(2025, 1, 1) + timedelta(days=k), "o": 100 + k, "h": 101 + k, "l": 99 + k, "c": 100 + k,
             "v": 1000} for k in range(60)]
    data = compute(bars)
    hold = evaluate(data, position={"quantity": 10, "avg_entry": 120, "stop": 100, "target": 400})
    assert hold.signal_type == "HOLD" and hold.position["unrealised"] == (159 - 120) * 10
    sell = evaluate(data, position={"quantity": 10, "avg_entry": 120, "stop": 100, "target": 150})
    assert sell.signal_type == "SELL_EXIT"
    assert [x["code"] for x in sell.exit_checks if x["triggered"]] == ["target_hit"]
    na = evaluate(data, position={"quantity": 10, "avg_entry": 120}, shariah_status="NON_COMPLIANT")
    assert na.signal_type == "SELL_EXIT" and any("No stop" in w for w in na.warnings)
