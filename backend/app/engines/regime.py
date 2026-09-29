"""Market regime from an index's daily bars, using measurable rules only.

Trend:      close vs SMA50 vs SMA200, confirmed by ADX(14) > 20
Volatility: current ATR14 as % of price vs its 1-year median (>1.3x high, <0.8x low)
"""

from __future__ import annotations

import statistics

from app.engines import indicators as ind


def classify(bars: list[dict]) -> dict:
    if len(bars) < 60:
        return {"label": None, "volatility": None, "explanation": f"Needs 60 index bars; {len(bars)} stored",
                "measures": {}}
    c = [b["c"] for b in bars]
    h = [b["h"] if b["h"] is not None else b["c"] for b in bars]
    lo = [b["l"] if b["l"] is not None else b["c"] for b in bars]
    s50, s200 = ind.sma(c, 50)[-1], ind.sma(c, 200)[-1]
    adx = ind.adx(h, lo, c)[0][-1]
    atr = ind.atr(h, lo, c)
    atr_pct = [a / x * 100 for a, x in zip(atr[-252:], c[-252:], strict=True) if a is not None]
    close = c[-1]
    slow = s200 if s200 is not None else s50
    trending = adx is not None and adx > 20
    if close > s50 and (slow is None or s50 >= slow) and trending:
        label = "Trending Up"
    elif close < s50 and (slow is None or s50 <= slow) and trending:
        label = "Trending Down"
    else:
        label = "Sideways"
    vol = None
    if len(atr_pct) >= 60:
        med = statistics.median(atr_pct)
        ratio = atr_pct[-1] / med if med else None
        vol = "High Volatility" if ratio and ratio > 1.3 else "Low Volatility" if ratio and ratio < 0.8 else "Normal"
    parts = [f"close {close:,.2f}", f"SMA50 {s50:,.2f}"]
    if s200 is not None:
        parts.append(f"SMA200 {s200:,.2f}")
    else:
        parts.append("SMA200 unavailable (fewer than 200 bars)")
    parts.append(f"ADX {adx:.1f}" if adx is not None else "ADX unavailable")
    if atr_pct:
        parts.append(f"ATR {atr_pct[-1]:.2f}% of price")
    return {
        "label": label, "volatility": vol,
        "explanation": f"{label}: " + ", ".join(parts) + ". Trend requires ADX above 20.",
        "measures": {"close": close, "sma50": s50, "sma200": s200, "adx": adx,
                     "atr_pct": atr_pct[-1] if atr_pct else None},
    }
