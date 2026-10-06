import math
import time
from datetime import date, timedelta

from app.engines import strategy
from app.engines.backtest import run
from app.engines.risk import position_size
from app.engines.signals import compute, evaluate


def series(n=420, seed=7):
    """Deterministic trending, noisy bars (test data, not market data)."""
    bars, price, x = [], 100.0, seed
    for k in range(n):
        x = (x * 1103515245 + 12345) % 2**31
        noise = (x / 2**31 - 0.5) * 3
        drift = 0.25 * math.sin(k / 40) + 0.08
        o = price
        price = max(5.0, price + drift + noise)
        hi, lo_ = max(o, price) + abs(noise) * 0.6 + 0.2, min(o, price) - abs(noise) * 0.6 - 0.2
        bars.append({"t": date(2022, 1, 3) + timedelta(days=k), "o": o, "h": hi, "l": lo_, "c": price,
                     "v": 100_000 + (x % 50_000)})
    return bars


CFG = strategy.config(None, {"params": {"buy_score": 60, "watch_score": 45, "min_rr": 1.0}})


def test_shifted_future_canary_signals_never_see_the_future():
    a = series()
    k = 300
    # B equals A up to bar k-1; after that the future is shifted down 40% and reversed.
    b = a[:k] + [{**bar, "o": bar["o"] * 0.6, "h": bar["h"] * 0.6, "l": bar["l"] * 0.6, "c": bar["c"] * 0.6}
                 for bar in reversed(a[k:])]
    for bar_new, bar_old in zip(b[k:], a[k:], strict=True):
        bar_new["t"] = bar_old["t"]
    da, db = compute(a), compute(b)
    for i in range(60, k):
        ra = evaluate(da, i, weights=CFG["weights"], params=CFG["params"], currency="NGN")
        rb = evaluate(db, i, weights=CFG["weights"], params=CFG["params"], currency="NGN")
        assert ra.to_dict() == rb.to_dict(), f"bar {i} depends on data after it"
    end = a[k - 1]["t"]
    ta = run(a, CFG, currency="NGN", start=a[0]["t"], end=end, data=da)
    tb = run(b, CFG, currency="NGN", start=b[0]["t"], end=end, data=db)
    assert ta["trades"] == tb["trades"] and ta["metrics"]["final_equity"] == tb["metrics"]["final_equity"]


def test_backtest_fills_next_open_and_charges_costs():
    a = series()
    res = run(a, CFG, currency="NGN", start=a[0]["t"], end=a[-1]["t"], commission_bps=50, slippage_bps=10)
    assert res["ok"]
    m = res["metrics"]
    assert m["trades"] == m["wins"] + m["losses"]
    by_date = {b["t"].isoformat(): i for i, b in enumerate(a)}
    for tr in res["trades"]:
        si, ei = by_date[tr["signal_date"]], by_date[tr["entry_date"]]
        assert ei == si + 1  # never on the signal bar itself
        assert abs(tr["entry"] - a[ei]["o"] * 1.001) < 1e-9  # next open plus 10 bps slippage
        assert tr["exit_date"] >= tr["entry_date"]
    free = run(a, CFG, currency="NGN", start=a[0]["t"], end=a[-1]["t"])
    if free["trades"]:
        assert free["metrics"]["final_equity"] > m["final_equity"]  # costs reduce the result
    assert len(m["equity"]) <= 402


def test_shariah_gate_blocks_entries():
    a = series()
    res = run(a, CFG, currency="NGN", start=a[0]["t"], end=a[-1]["t"], shariah_gate=lambda d: "NON_COMPLIANT")
    assert res["metrics"]["trades"] == 0
    assert res["metrics"]["skipped"].get("Shariah NON-COMPLIANT on the signal date", 0) >= 1


def test_backtest_speed_five_years():
    a = series(1260)
    t0 = time.time()
    run(a, CFG, currency="NGN", start=a[0]["t"], end=a[-1]["t"])
    assert time.time() - t0 < 30


def test_position_size_matches_hand_calculation():
    r = position_size(account=1_000_000, risk_pct=1, entry=100, stop=95, lot_size=1)
    assert r["shares"] == 2000 and r["loss_at_stop"] == 10_000
    capped = position_size(account=1_000_000, risk_pct=2, entry=100, stop=99.5, max_position_pct=25)
    assert capped["shares"] == 2500 and capped["capped_by"]
    costs = position_size(account=1_000_000, risk_pct=1, entry=100, stop=95, cost_pct_per_side=1, target=120)
    assert costs["shares"] == 1438  # 10,000 / (5 + 1.95) = 1,438.8, rounded down
    assert costs["loss_at_stop"] <= 10_000 and costs["reward_risk"] > 2
    assert not position_size(account=1000, risk_pct=1, entry=100, stop=101)["ok"]


def test_strategy_validation():
    assert strategy.validate({"trend": 30}, {"buy_score": 75}, ["obv_rising"], ["BUY_SETUP"],
                             strategy.EXIT_DEFAULTS) == []
    errs = strategy.validate({"luck": 5}, {"buy_score": 40, "watch_score": 60}, ["nope"], ["MOON"],
                             {"stop": "x", "stop_atr": 50, "target": "y", "target_r": 0, "max_hold_days": -1})
    assert len(errs) >= 7
