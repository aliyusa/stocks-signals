"""Indicator correctness against published reference values and an independent pandas implementation."""

import math
import random

import pytest

from app.engines import indicators as ind

# Wilder RSI worked example published by StockCharts ("RSI" ChartSchool article).
SC_CLOSE = [44.34, 44.09, 44.15, 43.61, 44.33, 44.83, 45.10, 45.42, 45.84, 46.08, 45.89, 46.03, 45.61, 46.28,
            46.28, 46.00, 46.03, 46.41, 46.22, 45.64, 46.21, 46.25, 45.71, 46.45, 45.78, 45.35, 44.03, 44.18,
            44.22, 44.57, 43.42, 42.66, 43.13]
SC_RSI = [70.53, 66.32, 66.55, 69.41, 66.36, 57.97, 62.93, 63.26, 56.06, 62.38, 54.71, 50.42, 39.99, 41.46,
          41.87, 45.46, 37.30, 33.08, 37.77]


def test_rsi_matches_stockcharts_worked_example():
    r = ind.rsi(SC_CLOSE, 14)
    assert all(v is None for v in r[:14])
    got = [round(v, 2) for v in r[14:]]
    # The published table rounds its intermediate averages (e.g. average loss 0.0996 where the exact
    # value is 0.1000), so it differs from exact arithmetic by up to about 0.07 points.
    for g, e in zip(got, SC_RSI, strict=True):
        assert abs(g - e) <= 0.1, (got, SC_RSI)


def test_rsi_flat_series_is_neutral_not_overbought():
    assert ind.rsi([100.0] * 30, 14)[-1] == 50.0


def test_sma_and_warmup():
    assert ind.sma([1, 2, 3, 4, 5], 3) == [None, None, 2.0, 3.0, 4.0]


def test_ema_seeded_with_sma():
    e = ind.ema([1, 2, 3, 4, 5, 6], 3)
    assert e[:2] == [None, None] and e[2] == 2.0
    assert e[3] == pytest.approx(3.0) and e[5] == pytest.approx(5.0)


def _series(n=400, seed=7):
    random.seed(seed)
    p, rows = 100.0, []
    for _ in range(n):
        c = p * (1 + random.gauss(0, 0.02))
        h, lo = max(p, c) * (1 + abs(random.gauss(0, 0.005))), min(p, c) * (1 - abs(random.gauss(0, 0.005)))
        rows.append((p, h, lo, c, random.randint(1000, 5000)))
        p = c
    o, h, lo, c, v = zip(*rows, strict=True)
    return list(o), list(h), list(lo), list(c), list(v)


pd = pytest.importorskip("pandas")


def test_against_pandas_reference():
    o, h, lo, c, v = _series()
    s = pd.Series(c)
    for n in (20, 50, 200):
        ref = s.rolling(n).mean().tolist()
        mine = ind.sma(c, n)
        assert all((a is None and math.isnan(b)) or abs(a - b) < 1e-9 for a, b in zip(mine, ref, strict=True))
    # EMA/Wilder differ only in seeding; after warm-up decay they must agree closely
    ref_ema = s.ewm(span=21, adjust=False).mean().tolist()
    assert abs(ind.ema(c, 21)[-1] - ref_ema[-1]) < 1e-9
    d = s.diff()
    up = d.clip(lower=0).ewm(alpha=1 / 14, adjust=False).mean()
    dn = (-d.clip(upper=0)).ewm(alpha=1 / 14, adjust=False).mean()
    ref_rsi = (100 - 100 / (1 + up / dn)).tolist()
    assert abs(ind.rsi(c, 14)[-1] - ref_rsi[-1]) < 1e-6
    line, sig, hist = ind.macd(c)
    ref_line = (s.ewm(span=12, adjust=False).mean() - s.ewm(span=26, adjust=False).mean())
    assert abs(line[-1] - ref_line.iloc[-1]) < 1e-9
    assert abs(hist[-1] - (line[-1] - sig[-1])) < 1e-12
    mid, up_b, lo_b = ind.bollinger(c, 20)
    assert abs(up_b[-1] - (s.rolling(20).mean() + 2 * s.rolling(20).std(ddof=0)).iloc[-1]) < 1e-9


def test_atr_obv_stoch_roc_adx_shapes():
    o, h, lo, c, v = _series(120)
    for series in (ind.atr(h, lo, c), ind.obv(c, v), ind.stochastic(h, lo, c)[0], ind.roc(c), ind.adx(h, lo, c)[0]):
        assert len(series) == len(c)
        assert series[-1] is not None
    k, _ = ind.stochastic(h, lo, c)
    assert all(0 <= x <= 100 for x in k if x is not None)
    a, _, _ = ind.adx(h, lo, c)
    assert all(0 <= x <= 100 for x in a if x is not None)


def test_swings_confirmation_has_no_lookahead():
    h = [1, 2, 3, 9, 3, 2, 1, 2, 3]
    lo = [x - 0.5 for x in h]
    assert ind.confirmed_swings(h, lo, upto=5, k=3) == []  # the peak at index 3 needs 3 bars after it
    assert any(s.index == 3 and s.kind == "high" for s in ind.confirmed_swings(h, lo, upto=6, k=3))


def test_levels_cluster_nearby_swings():
    pts = [ind.Swing(1, 100, "high"), ind.Swing(5, 101, "high"), ind.Swing(9, 120, "high"), ind.Swing(3, 90, "low")]
    lv = ind.levels(pts, ref_price=110, tolerance=2)
    assert [(round(x.price, 1), x.touches, x.kind) for x in lv] == [(90, 1, "support"), (100.5, 2, "support"),
                                                                   (120, 1, "resistance")]
