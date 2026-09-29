"""Technical indicators in plain Python.

Why not TA-Lib or pandas: the formulas stay visible (the platform must explain every
number), there is no native code to install on Windows, and lists of a few thousand
bars are computed in milliseconds.

Conventions
- Every function takes oldest-first lists and returns a list of the same length.
- Values inside the warm-up window are None. Rules that need them must treat None as
  "insufficient data", never as zero.
- Nothing here looks at a later bar than the one being computed (no look-ahead), so
  the backtester can reuse these functions unchanged.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass

Num = float | None


def sma(values: Sequence[Num], n: int) -> list[Num]:
    out: list[Num] = [None] * len(values)
    window: list[float] = []
    total = 0.0
    for i, v in enumerate(values):
        if v is None:  # a gap resets the window; averages never bridge missing data
            window, total = [], 0.0
            continue
        window.append(v)
        total += v
        if len(window) > n:
            total -= window.pop(0)
        if len(window) == n:
            out[i] = total / n
    return out


def ema(values: Sequence[Num], n: int) -> list[Num]:
    """Standard EMA, alpha = 2/(n+1), seeded with the SMA of the first n values."""
    out: list[Num] = [None] * len(values)
    k = 2.0 / (n + 1)
    seed: list[float] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = v * k + prev * (1 - k)
        out[i] = prev
    return out


def _wilder(values: Sequence[Num], n: int) -> list[Num]:
    """Wilder's smoothing (alpha = 1/n), seeded with the simple mean of the first n values."""
    out: list[Num] = [None] * len(values)
    seed: list[float] = []
    prev: float | None = None
    for i, v in enumerate(values):
        if v is None:
            continue
        if prev is None:
            seed.append(v)
            if len(seed) == n:
                prev = sum(seed) / n
                out[i] = prev
            continue
        prev = (prev * (n - 1) + v) / n
        out[i] = prev
    return out


def rsi(close: Sequence[float], n: int = 14) -> list[Num]:
    gains: list[Num] = [None]
    losses: list[Num] = [None]
    for i in range(1, len(close)):
        d = close[i] - close[i - 1]
        gains.append(max(d, 0.0))
        losses.append(max(-d, 0.0))
    ag, al = _wilder(gains, n), _wilder(losses, n)
    out: list[Num] = []
    for g, l_ in zip(ag, al, strict=True):
        if g is None or l_ is None:
            out.append(None)
        elif l_ == 0:
            out.append(100.0 if g > 0 else 50.0)  # no movement at all is neutral, not overbought
        else:
            out.append(100 - 100 / (1 + g / l_))
    return out


def macd(close: Sequence[float], fast: int = 12, slow: int = 26, signal: int = 9):
    ef, es = ema(close, fast), ema(close, slow)
    line = [a - b if a is not None and b is not None else None for a, b in zip(ef, es, strict=True)]
    sig = ema(line, signal)
    hist = [a - b if a is not None and b is not None else None for a, b in zip(line, sig, strict=True)]
    return line, sig, hist


def true_range(high: Sequence[float], low: Sequence[float], close: Sequence[float]) -> list[Num]:
    out: list[Num] = []
    for i in range(len(close)):
        if i == 0:
            out.append(high[0] - low[0])
        else:
            out.append(max(high[i] - low[i], abs(high[i] - close[i - 1]), abs(low[i] - close[i - 1])))
    return out


def atr(high, low, close, n: int = 14) -> list[Num]:
    return _wilder(true_range(high, low, close), n)


def bollinger(close: Sequence[float], n: int = 20, k: float = 2.0):
    mid = sma(close, n)
    upper: list[Num] = [None] * len(close)
    lower: list[Num] = [None] * len(close)
    for i in range(n - 1, len(close)):
        m = mid[i]
        if m is None:
            continue
        w = close[i - n + 1:i + 1]
        sd = math.sqrt(sum((x - m) ** 2 for x in w) / n)  # population SD, as in Bollinger's definition
        upper[i], lower[i] = m + k * sd, m - k * sd
    return mid, upper, lower


def stochastic(high, low, close, n: int = 14, d: int = 3):
    k: list[Num] = [None] * len(close)
    for i in range(n - 1, len(close)):
        hh, ll = max(high[i - n + 1:i + 1]), min(low[i - n + 1:i + 1])
        k[i] = 50.0 if hh == ll else (close[i] - ll) / (hh - ll) * 100
    return k, sma(k, d)


def roc(close: Sequence[float], n: int = 10) -> list[Num]:
    return [None if i < n or close[i - n] == 0 else (close[i] / close[i - n] - 1) * 100 for i in range(len(close))]


def obv(close: Sequence[float], volume: Sequence[Num]) -> list[Num]:
    out: list[Num] = []
    total = 0.0
    for i, c in enumerate(close):
        v = volume[i] or 0.0
        if i > 0:
            total += v if c > close[i - 1] else -v if c < close[i - 1] else 0.0
        out.append(total)
    return out


def adx(high, low, close, n: int = 14) -> tuple[list[Num], list[Num], list[Num]]:
    plus_dm: list[Num] = [None]
    minus_dm: list[Num] = [None]
    for i in range(1, len(close)):
        up, down = high[i] - high[i - 1], low[i - 1] - low[i]
        plus_dm.append(up if up > down and up > 0 else 0.0)
        minus_dm.append(down if down > up and down > 0 else 0.0)
    tr = true_range(high, low, close)
    tr[0] = None
    atr_ = _wilder(tr, n)
    pdi_s, mdi_s = _wilder(plus_dm, n), _wilder(minus_dm, n)
    pdi: list[Num] = []
    mdi: list[Num] = []
    dx: list[Num] = []
    for a, p, m in zip(atr_, pdi_s, mdi_s, strict=True):
        if a is None or p is None or m is None or a == 0:
            pdi.append(None), mdi.append(None), dx.append(None)
            continue
        pv, mv = 100 * p / a, 100 * m / a
        pdi.append(pv), mdi.append(mv)
        dx.append(0.0 if pv + mv == 0 else 100 * abs(pv - mv) / (pv + mv))
    return _wilder(dx, n), pdi, mdi


# ---------- price structure ----------


@dataclass(frozen=True)
class Swing:
    index: int
    price: float
    kind: str  # "high" | "low"


def swings(high: Sequence[float], low: Sequence[float], k: int = 3) -> list[Swing]:
    """Fractal swing points: a high greater than the k bars either side (lows mirrored).

    A swing at index i is only *known* at i + k, so callers working bar-by-bar must
    ignore swings newer than (current index - k). `confirmed_swings` does that.
    Runs of identical prices (common on NGX) count once, at their first bar.
    """
    out: list[Swing] = []
    for i in range(k, len(high) - k):
        left_h, right_h = high[i - k:i], high[i + 1:i + k + 1]
        if high[i] > max(left_h) and high[i] >= max(right_h):
            out.append(Swing(i, high[i], "high"))
        left_l, right_l = low[i - k:i], low[i + 1:i + k + 1]
        if low[i] < min(left_l) and low[i] <= min(right_l):
            out.append(Swing(i, low[i], "low"))
    return out


def confirmed_swings(high, low, upto: int, k: int = 3) -> list[Swing]:
    return [s for s in swings(high[:upto + 1], low[:upto + 1], k) if s.index <= upto - k]


@dataclass(frozen=True)
class Level:
    price: float
    touches: int
    last_index: int
    kind: str  # support | resistance (relative to the reference price)


def levels(swing_points: Sequence[Swing], ref_price: float, tolerance: float, min_touches: int = 1) -> list[Level]:
    """Cluster swing prices that lie within `tolerance` of each other (single-linkage on sorted prices)."""
    pts = sorted(swing_points, key=lambda s: s.price)
    clusters: list[list[Swing]] = []
    for s in pts:
        if clusters and s.price - clusters[-1][-1].price <= tolerance:
            clusters[-1].append(s)
        else:
            clusters.append([s])
    out = []
    for c in clusters:
        if len(c) < min_touches:
            continue
        price = sum(s.price for s in c) / len(c)
        out.append(Level(price, len(c), max(s.index for s in c), "support" if price < ref_price else "resistance"))
    return out


def gaps(open_: Sequence[Num], high, low, lookback: int = 5) -> list[dict]:
    """Full gaps in the last `lookback` bars: today's low above yesterday's high (up) or the reverse."""
    out = []
    start = max(1, len(high) - lookback)
    for i in range(start, len(high)):
        if low[i] > high[i - 1]:
            out.append({"index": i, "direction": "up", "size": low[i] - high[i - 1]})
        elif high[i] < low[i - 1]:
            out.append({"index": i, "direction": "down", "size": low[i - 1] - high[i]})
    return out


def trend_structure(swing_points: Sequence[Swing]) -> str:
    """Compare the last two confirmed swing highs and lows."""
    highs = [s.price for s in swing_points if s.kind == "high"][-2:]
    lows = [s.price for s in swing_points if s.kind == "low"][-2:]
    if len(highs) < 2 or len(lows) < 2:
        return "insufficient"
    hh, hl = highs[1] > highs[0], lows[1] > lows[0]
    lh, ll = highs[1] < highs[0], lows[1] < lows[0]
    if hh and hl:
        return "higher_highs_higher_lows"
    if lh and ll:
        return "lower_highs_lower_lows"
    return "mixed"


def resample_weekly(bars: Sequence[dict]) -> list[dict]:
    """Aggregate daily bars (dicts with t as date) into ISO weeks. The last week may be partial."""
    out: list[dict] = []
    for b in bars:
        key = b["t"].isocalendar()[:2]
        if out and out[-1]["_k"] == key:
            w = out[-1]
            w["h"] = max(w["h"], b["h"])
            w["l"] = min(w["l"], b["l"])
            w["c"] = b["c"]
            w["v"] = (w["v"] or 0) + (b["v"] or 0)
            w["t"] = b["t"]
        else:
            out.append({**b, "_k": key})
    for w in out:
        w.pop("_k", None)
    return out
