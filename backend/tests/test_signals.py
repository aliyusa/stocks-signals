"""Signal engine behaviour on synthetic, clearly labelled test series (never shown as market data)."""

import random
from datetime import date, timedelta

from app.engines import regime
from app.engines.signals import compute, evaluate, weekly_trend


def make_bars(n=320, drift=0.001, vol=0.012, seed=1, flat=False, base=100.0, volume=100_000):
    random.seed(seed)
    d, p, out = date(2025, 1, 1), base, []
    while len(out) < n:
        d += timedelta(days=1)
        if d.weekday() >= 5:
            continue
        if flat and random.random() < 0.8:
            o = h = lo = c = p
        else:
            c = p * (1 + random.gauss(drift, vol))
            o = p
            h, lo = max(o, c) * (1 + abs(random.gauss(0, 0.004))), min(o, c) * (1 - abs(random.gauss(0, 0.004)))
        out.append({"t": d, "o": o, "h": h, "l": lo, "c": c, "v": volume * (1 + abs(random.gauss(0, 0.3)))})
        p = c
    return out


def with_breakout(bars):
    """Append a 3-day consolidation and a high-volume breakout bar."""
    last = bars[-1]
    hi = max(b["h"] for b in bars[-20:])
    d = last["t"]
    extra = []
    for _k in range(3):
        d += timedelta(days=1 if d.weekday() < 4 else 3)
        c = hi * 0.99
        extra.append({"t": d, "o": c, "h": hi * 0.995, "l": c * 0.99, "c": c, "v": 90_000})
    d += timedelta(days=1 if d.weekday() < 4 else 3)
    extra.append({"t": d, "o": hi, "h": hi * 1.03, "l": hi * 0.999, "c": hi * 1.025, "v": 400_000})
    return bars + extra


def test_score_is_explained_and_bounded():
    r = evaluate(compute(make_bars()), currency="USD")
    assert 0 <= r.score <= 100
    assert 0 < r.coverage <= 1
    assert {x.category for x in r.rules} == set(r.breakdown)
    total = sum(b["points"] or 0 for b in r.breakdown.values())
    evaluated = sum(b["weight"] for b in r.breakdown.values() if b["evaluated"])
    assert abs(total / evaluated * 100 - r.score) < 0.11  # score is exactly the documented formula


def test_uptrend_breakout_scores_higher_than_downtrend():
    up = evaluate(compute(with_breakout(make_bars(drift=0.002, seed=3))), currency="USD",
                  market_regime={"label": "Trending Up"})
    down = evaluate(compute(make_bars(drift=-0.002, seed=3)), currency="USD", market_regime={"label": "Trending Down"})
    assert up.score > down.score
    assert up.snapshot["breakout"] is True
    assert up.entry_low is not None and up.stop < up.entry_low
    assert down.signal_type in ("WAIT", "WATCHLIST")


def test_buy_setup_requires_rr_and_confirmation():
    r = evaluate(compute(with_breakout(make_bars(drift=0.002, seed=3))), currency="USD",
                 market_regime={"label": "Trending Up"})
    if r.signal_type == "BUY_SETUP":
        assert r.risk_reward is not None and r.risk_reward >= 2
        assert r.breakdown["trend"]["pct"] >= 0.6 and r.breakdown["price_action"]["pct"] >= 0.6


def test_targets_never_invented():
    r = evaluate(compute(make_bars(drift=0.003, seed=5)), currency="USD")
    for t in r.targets:
        assert t.price is not None and t.method
    if not r.targets:
        assert r.risk_reward is None
        assert any(x.id == "rr_min" and x.passed is None for x in r.rules)


def test_flat_ngx_style_series_is_avoided_or_warned():
    r = evaluate(compute(make_bars(flat=True, volume=1000, base=1000)), currency="NGN")
    assert r.signal_type == "AVOID" or any("flat" in w for w in r.warnings)
    pd_rule = next(x for x in r.rules if x.id == "price_discovery")
    assert pd_rule.passed is False


def test_non_compliant_is_always_avoid():
    r = evaluate(compute(with_breakout(make_bars(drift=0.002, seed=3))), currency="USD",
                 shariah_status="NON_COMPLIANT")
    assert r.signal_type == "AVOID"


def test_missing_regime_reduces_coverage_not_score_honesty():
    data = compute(make_bars())
    with_m = evaluate(data, currency="USD", market_regime={"label": "Sideways"})
    without = evaluate(data, currency="USD")
    assert without.coverage < with_m.coverage
    assert next(x for x in without.rules if x.id == "market_regime").passed is None


def test_short_history_withholds_buy():
    r = evaluate(compute(make_bars(n=60)), currency="USD")
    assert r.signal_type != "BUY_SETUP"
    assert any("200 bars" in w for w in r.warnings)


def test_no_lookahead_signal_at_i_equals_signal_on_truncated_history():
    bars = with_breakout(make_bars(drift=0.001, seed=11))
    full = compute(bars)
    for i in (150, 220, len(bars) - 5, len(bars) - 1):
        a = evaluate(full, i, currency="USD").to_dict()
        b = evaluate(compute(bars[:i + 1]), currency="USD").to_dict()
        assert a == b, f"look-ahead detected at bar {i}"


def test_weekly_trend_and_regime():
    bars = make_bars(n=400, drift=0.002, seed=2)
    assert weekly_trend(bars) in ("Bullish", "Neutral", "Bearish")
    rg = regime.classify(bars)
    assert rg["label"] in ("Trending Up", "Sideways", "Trending Down")
    assert "ADX" in rg["explanation"]
    assert regime.classify(bars[:30])["label"] is None
