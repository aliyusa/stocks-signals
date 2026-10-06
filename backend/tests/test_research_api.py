from tests.conftest import csrf, register
from tests.test_eodhd import add_dangcem, fake  # noqa: F401  (fixture re-export)

REF = {"exchange": "XNSA", "ticker": "DANGCEM"}


def setup(client):
    register(client)
    add_dangcem(client)
    client.get("/api/stocks/XNSA/DANGCEM")


def body(**kw):
    return {"name": "Breakout only", "weights": {"trend": 30, "momentum": 20, "volume": 15, "price_action": 25,
                                                 "risk": 10, "market": 0, "liquidity": 0},
            "params": {"buy_score": 60, "watch_score": 45}, "disabled": ["obv_rising"], "entry_on": ["BUY_SETUP"],
            "exit": {"stop": "atr", "stop_atr": 2, "target": "r_multiple", "target_r": 2, "max_hold_days": 30}, **kw}


def test_strategy_crud_activation_changes_signals(client, fake):  # noqa: F811
    setup(client)
    h = csrf(client)
    lst = client.get("/api/strategies").json()
    builtin = lst["strategies"][0]
    assert builtin["is_builtin"] and builtin["is_active"]
    assert client.put(f"/api/strategies/{builtin['id']}", json=body(), headers=h).status_code == 403
    assert client.post("/api/strategies", json=body(params={"buy_score": 40}), headers=h).status_code == 422
    s = client.post("/api/strategies", json=body(), headers=h).json()
    assert s["disabled"] == ["obv_rising"] and s["exit"]["stop"] == "atr"
    client.post(f"/api/strategies/{s['id']}/activate", headers=h)
    a = client.get("/api/stocks/XNSA/DANGCEM/analysis").json()
    assert a["strategy"] == "Breakout only"
    obv = next(r for r in a["signal"]["rules"] if r["id"] == "obv_rising")
    assert obv["passed"] is None and "Switched off" in obv["detail"]
    assert a["signal"]["breakdown"]["market"]["weight"] == 0
    client.delete(f"/api/strategies/{s['id']}", headers=h)
    assert client.get("/api/stocks/XNSA/DANGCEM/analysis").json()["strategy"] != "Breakout only"


def test_backtest_runs_and_is_stored(client, fake):  # noqa: F811
    setup(client)
    h = csrf(client)
    sid = client.get("/api/strategies").json()["strategies"][0]["id"]
    bars = client.get("/api/stocks/XNSA/DANGCEM/bars?range=MAX").json()["bars"]
    req = {"strategy_id": sid, "universe": [REF], "start": bars[0]["t"], "end": bars[-1]["t"],
           "commission_bps": 200, "slippage_bps": 25, "shariah_filter": "none"}
    r = client.post("/api/backtests", json=req, headers=h)
    assert r.status_code == 201, r.text
    b = r.json()
    m = b["metrics"]["per_stock"][0]["metrics"]
    assert m["trades"] == len(b["trades"]) and "buy_hold_return_pct" in m and m["equity"]
    assert any("market-regime" in x for x in b["metrics"]["limitations"])
    assert client.get("/api/backtests").json()["backtests"][0]["id"] == b["id"]
    # Shariah: a prohibited primary business blocks every entry
    client.put("/api/stocks/XNSA/DANGCEM/activities", json={"activities": [{"tag": "alcohol", "primary": True}]},
               headers=h)
    blocked = client.post("/api/backtests", json={**req, "shariah_filter": "exclude_non_compliant"}, headers=h).json()
    assert blocked["summary"]["trades"] == 0
    bad = client.post("/api/backtests", json={**req, "end": req["start"]}, headers=h)
    assert bad.status_code == 422


def test_risk_endpoint(client):
    register(client)
    h = csrf(client)
    r = client.post("/api/risk/position-size", json={"account": 500000, "risk_pct": 1, "entry": 50, "stop": 45},
                    headers=h).json()
    assert r["ok"] and r["shares"] == 1000 and len(r["steps"]) == 3
    assert client.post("/api/risk/position-size", json={"account": 500000, "risk_pct": 1, "entry": 50, "stop": 55},
                       headers=h).json()["ok"] is False
