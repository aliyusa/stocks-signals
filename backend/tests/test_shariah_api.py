from datetime import date, timedelta

from tests.conftest import csrf, register
from tests.test_eodhd import add_dangcem, fake  # noqa: F401  (fixture re-export)

BASE = "/api/stocks/XNSA/DANGCEM"


def setup_stock(client):
    register(client)
    add_dangcem(client)
    client.get(BASE)  # stores bars from the fake provider


def recent_period() -> str:
    return (date.today() - timedelta(days=40)).isoformat()


FUND = {"period_type": "H", "currency": "NGN", "source_ref": "H1 2026 unaudited accounts, p. 4",
        "revenue": 1_000_000.0, "interest_bearing_debt": 10_000.0, "cash": 5_000.0,
        "interest_bearing_securities": 0.0, "interest_income": 1_000.0, "non_permissible_income": 0.0,
        "shares_outstanding": 1_000.0, "total_assets": 2_000_000.0, "dividend_per_share": 30.0}


def test_unscreened_stock_is_never_assumed_compliant(client, fake):  # noqa: F811
    setup_stock(client)
    r = client.get(f"{BASE}/shariah").json()
    assert r["result"]["not_screened"] is True and r["result"]["status"] == "INSUFFICIENT_DATA"
    a = client.get(f"{BASE}/analysis").json()
    assert a["shariah"]["status"] == "NOT_SCREENED"
    sc = client.get("/api/shariah/screener?market=NG").json()
    assert sc["counts"]["NOT_SCREENED"] == sc["total"] >= 1 and sc["results"] == []


def test_full_screen_flow_and_signal_integration(client, fake):  # noqa: F811
    setup_stock(client)
    h = csrf(client)
    r = client.put(f"{BASE}/activities", json={"activities": [
        {"tag": "permissible", "label": "Cement", "primary": True}]}, headers=h)
    assert r.status_code == 200
    r = client.post(f"{BASE}/fundamentals", json={**FUND, "period_end": recent_period()}, headers=h)
    assert r.status_code == 201, r.text
    s = client.get(f"{BASE}/shariah").json()
    res = s["result"]
    assert res["status"] in ("COMPLIANT", "QUESTIONABLE", "NON_COMPLIANT")
    debt = next(x for x in res["ratios"] if x["id"] == "debt")
    assert debt["denominator"]["value"] > 0 and "shares outstanding" in debt["denominator"]["method"]
    assert res["purification"]["per_share"] == 30.0 * 1_000 / 1_000_000
    assert len(s["history"]) == 1
    client.get(f"{BASE}/shariah")  # unchanged inputs: no duplicate screen record
    assert len(client.get(f"{BASE}/shariah").json()["history"]) == 1

    # a prohibited primary business turns the signal into AVOID
    client.put(f"{BASE}/activities", json={"activities": [{"tag": "alcohol", "primary": True}]}, headers=h)
    a = client.get(f"{BASE}/analysis").json()
    assert a["shariah"]["status"] == "NON_COMPLIANT" and a["signal"]["signal_type"] == "AVOID"
    sc = client.post("/api/scanner", json={"market": "NG", "shariah": ["COMPLIANT"]}, headers=h).json()
    assert sc["results"] == []
    rows = client.get("/api/shariah/screener?market=NG&status=NON_COMPLIANT").json()["results"]
    assert rows[0]["ticker"] == "DANGCEM"


def test_fundamentals_validation_and_delete(client, fake):  # noqa: F811
    setup_stock(client)
    h = csrf(client)
    future = (date.today() + timedelta(days=5)).isoformat()
    assert client.post(f"{BASE}/fundamentals", json={**FUND, "period_end": future}, headers=h).status_code == 422
    no_ref = {k: v for k, v in FUND.items() if k != "source_ref"}
    assert client.post(f"{BASE}/fundamentals", json={**no_ref, "period_end": recent_period()},
                       headers=h).status_code == 422
    assert client.post(f"{BASE}/fundamentals", json={**FUND, "period_end": recent_period(), "cash": -1},
                       headers=h).status_code == 422
    fid = client.post(f"{BASE}/fundamentals", json={**FUND, "period_end": recent_period()}, headers=h).json()["id"]
    again = client.post(f"{BASE}/fundamentals", json={**FUND, "period_end": recent_period(), "cash": 7.0},
                        headers=h).json()
    assert again["id"] == fid and again["cash"] == 7.0  # same period updates in place
    assert client.delete(f"{BASE}/fundamentals/{fid}", headers=h).status_code == 200
    assert client.get(f"{BASE}/shariah").json()["fundamentals"] == []


def test_methodology_clone_edit_default_delete(client, fake):  # noqa: F811
    setup_stock(client)
    h = csrf(client)
    client.put(f"{BASE}/activities", json={"activities": [{"tag": "permissible", "primary": True}]}, headers=h)
    ms = client.get("/api/shariah/methodologies").json()
    aaoifi = next(m for m in ms if m["code"] == "aaoifi_based")
    assert aaoifi["is_default"] and aaoifi["is_builtin"]
    edit = {"name": "Strict", "description": "Tighter limits", "denominator": "market_cap",
            "thresholds": {**aaoifi["thresholds"], "debt_to_denominator": 0.25},
            "prohibited_activities": aaoifi["prohibited_activities"], "max_data_age_days": 120}
    assert client.put(f"/api/shariah/methodologies/{aaoifi['id']}", json=edit, headers=h).status_code == 403
    copy = client.post("/api/shariah/methodologies", json={"from_id": aaoifi["id"], "name": "Strict"},
                       headers=h).json()
    r = client.put(f"/api/shariah/methodologies/{copy['id']}", json=edit, headers=h)
    assert r.status_code == 200 and r.json()["thresholds"]["debt_to_denominator"] == 0.25
    bad = {**edit, "thresholds": {"debt_to_denominator": 30}}
    assert client.put(f"/api/shariah/methodologies/{copy['id']}", json=bad, headers=h).status_code == 422
    assert client.put("/api/shariah/default", json={"methodology_id": copy["id"]}, headers=h).status_code == 200
    ms = client.get("/api/shariah/methodologies").json()
    assert next(m for m in ms if m["id"] == copy["id"])["is_default"]
    assert client.get(f"{BASE}/shariah").json()["result"]["methodology"]["name"] == "Strict"  # records a screen
    assert client.delete(f"/api/shariah/methodologies/{copy['id']}", headers=h).status_code == 200
    client.delete(f"/api/shariah/methodologies/{copy['id']}", headers=h)
    ms = client.get("/api/shariah/methodologies").json()
    assert next(m for m in ms if m["code"] == "aaoifi_based")["is_default"]


def test_other_users_methodology_is_private(client):
    register(client)
    h = csrf(client)
    aaoifi = next(m for m in client.get("/api/shariah/methodologies").json() if m["code"] == "aaoifi_based")
    mine = client.post("/api/shariah/methodologies", json={"from_id": aaoifi["id"], "name": "Mine"},
                       headers=h).json()
    client.post("/api/auth/logout", headers=h)
    register(client, email="other@example.com")
    h2 = csrf(client)
    assert all(m["id"] != mine["id"] for m in client.get("/api/shariah/methodologies").json())
    assert client.put("/api/shariah/default", json={"methodology_id": mine["id"]}, headers=h2).status_code == 404
    assert client.delete(f"/api/shariah/methodologies/{mine['id']}", headers=h2).status_code == 404


def test_review_and_external(client, fake):  # noqa: F811
    setup_stock(client)
    h = csrf(client)
    client.put(f"{BASE}/activities", json={"activities": [{"tag": "permissible", "primary": True}]}, headers=h)
    client.put(f"{BASE}/shariah-review", json={"note": "Awaiting full-year notes"}, headers=h)
    assert client.get(f"{BASE}/shariah").json()["result"]["status"] == "UNDER_REVIEW"
    bad = {"items": [{"source": "X", "status": "COMPLIANT", "as_of": "2026-09-01", "url": "javascript:alert(1)"}]}
    assert client.put(f"{BASE}/shariah-external", json=bad, headers=h).status_code == 422
    ok = {"items": [{"source": "Index X", "status": "NON_COMPLIANT", "as_of": "2026-09-01",
                     "url": "https://example.com/list"}]}
    assert client.put(f"{BASE}/shariah-external", json=ok, headers=h).status_code == 200
    assert client.get(f"{BASE}/shariah").json()["external"][0]["source"] == "Index X"
