"""Transparent, rule-based setup scoring.

Every signal is a pure function of the bars up to and including bar `i`, plus optional
context (market regime, Shariah status). No hidden model and no future data.

Output contract (see docs/ARCHITECTURE.md §3):
- rules: every rule with category, pass / fail / n/a, the measured value and a sentence
- score: weighted, renormalised over rules that could be evaluated
- coverage: share of total weight that could be evaluated
- signal_type: BUY_SETUP, WATCHLIST, WAIT or AVOID; with an open position, SELL_EXIT or HOLD
  (exit checks are listed one by one in `exit_checks`)
- levels: entry zone, stop, targets, each with the method used; a level is omitted
  when no price structure supports it
"""

from __future__ import annotations

import statistics
from dataclasses import asdict, dataclass, field
from datetime import date

from app.engines import indicators as ind

DEFAULT_WEIGHTS = {"trend": 20, "momentum": 20, "volume": 15, "price_action": 20, "risk": 10, "market": 10,
                   "liquidity": 5}
CATEGORY_LABELS = {"trend": "Trend", "momentum": "Momentum", "volume": "Volume", "price_action": "Price action",
                   "risk": "Risk", "market": "Market", "liquidity": "Liquidity"}

DEFAULT_PARAMS = {
    "buy_score": 70.0,
    "watch_score": 55.0,
    "min_rr": 2.0,
    "min_coverage": 0.6,
    "min_category_pct": 0.6,  # trend and price action must each pass at least this share for BUY
    "volume_confirm_ratio": 1.2,
    "rsi_low": 50.0,
    "rsi_high": 70.0,
    "flat_bar_max": 0.2,
    # 20-day median traded value (close x volume) below this is treated as illiquid
    "min_traded_value": {"NGN": 5_000_000, "USD": 1_000_000, "GBP": 500_000, "EUR": 500_000},
}


@dataclass
class Rule:
    id: str
    category: str
    label: str
    passed: bool | None  # None = could not be evaluated (insufficient data)
    value: str | None = None
    detail: str = ""


@dataclass
class LevelOut:
    name: str
    price: float | None
    method: str


@dataclass
class SignalResult:
    as_of: date
    close: float
    signal_type: str
    score: float | None
    coverage: float
    breakdown: dict
    rules: list[Rule]
    reasons: list[str]
    warnings: list[str]
    entry_low: float | None = None
    entry_high: float | None = None
    stop: float | None = None
    targets: list[LevelOut] = field(default_factory=list)
    risk_reward: float | None = None
    level_notes: list[LevelOut] = field(default_factory=list)
    supports: list[dict] = field(default_factory=list)
    resistances: list[dict] = field(default_factory=list)
    snapshot: dict = field(default_factory=dict)
    timeframes: dict = field(default_factory=dict)
    summary: str = ""
    exit_checks: list[dict] = field(default_factory=list)
    position: dict | None = None

    def to_dict(self) -> dict:
        d = asdict(self)
        d["as_of"] = self.as_of.isoformat()
        return d


def compute(bars: list[dict]) -> dict:
    """All indicator series for a bar list (oldest first). Bars: {t, o, h, l, c, v}."""
    o = [b["o"] if b["o"] is not None else b["c"] for b in bars]
    h = [b["h"] if b["h"] is not None else b["c"] for b in bars]
    lo = [b["l"] if b["l"] is not None else b["c"] for b in bars]
    c = [b["c"] for b in bars]
    v = [b["v"] for b in bars]
    macd_line, macd_sig, macd_hist = ind.macd(c)
    bb_mid, bb_up, bb_lo = ind.bollinger(c)
    stoch_k, stoch_d = ind.stochastic(h, lo, c)
    adx_, pdi, mdi = ind.adx(h, lo, c)
    return {
        "o": o, "h": h, "l": lo, "c": c, "v": v, "t": [b["t"] for b in bars],
        "sma20": ind.sma(c, 20), "sma50": ind.sma(c, 50), "sma100": ind.sma(c, 100), "sma200": ind.sma(c, 200),
        "ema9": ind.ema(c, 9), "ema21": ind.ema(c, 21), "ema50": ind.ema(c, 50), "ema200": ind.ema(c, 200),
        "rsi": ind.rsi(c, 14), "macd": macd_line, "macd_signal": macd_sig, "macd_hist": macd_hist,
        "stoch_k": stoch_k, "stoch_d": stoch_d, "roc10": ind.roc(c, 10), "obv": ind.obv(c, v),
        "vol_sma20": ind.sma([x if x is not None else 0.0 for x in v], 20),
        "atr": ind.atr(h, lo, c, 14), "bb_mid": bb_mid, "bb_up": bb_up, "bb_lo": bb_lo,
        "adx": adx_, "pdi": pdi, "mdi": mdi,
    }


def _at(series, i):
    return series[i] if 0 <= i < len(series) else None


def _fmt(x, d=2):
    return None if x is None else f"{x:,.{d}f}"


def _cmp(a, b) -> bool | None:
    return None if a is None or b is None else a > b


def trend_label(close, fast, slow) -> str:
    if close is None or fast is None or slow is None:
        return "Insufficient data"
    if close > fast > slow:
        return "Bullish"
    if close < fast < slow:
        return "Bearish"
    return "Neutral"


def evaluate(
    data: dict,
    i: int | None = None,
    *,
    weights: dict | None = None,
    params: dict | None = None,
    currency: str | None = None,
    market_regime: dict | None = None,
    shariah_status: str | None = None,
    extra_warnings: list[str] | None = None,
    position: dict | None = None,
    disabled_rules: set[str] | frozenset[str] = frozenset(),
) -> SignalResult:
    w = {**DEFAULT_WEIGHTS, **(weights or {})}
    p = {**DEFAULT_PARAMS, **(params or {})}
    n = len(data["c"])
    i = n - 1 if i is None else i
    c, h, lo = data["c"], data["h"], data["l"]
    close = c[i]
    atr = _at(data["atr"], i)
    rules: list[Rule] = []

    def rule(id_, cat, label, passed, value=None, detail=""):
        rules.append(Rule(id_, cat, label, passed, value, detail))

    # ---------- trend ----------
    s50, s200, e21 = _at(data["sma50"], i), _at(data["sma200"], i), _at(data["ema21"], i)
    e21_prev = _at(data["ema21"], i - 5)
    rule("close_gt_sma50", "trend", "Price above 50-day SMA", _cmp(close, s50), _fmt(s50),
         f"Close {_fmt(close)} vs SMA50 {_fmt(s50)}" if s50 else "Needs 50 bars")
    rule("sma50_gt_sma200", "trend", "50-day SMA above 200-day SMA", _cmp(s50, s200), _fmt(s200),
         f"SMA50 {_fmt(s50)} vs SMA200 {_fmt(s200)}" if s200 else "Needs 200 bars")
    rule("close_gt_sma200", "trend", "Price above 200-day SMA", _cmp(close, s200), _fmt(s200),
         f"Close {_fmt(close)} vs SMA200 {_fmt(s200)}" if s200 else "Needs 200 bars")
    rule("ema21_rising", "trend", "21-day EMA rising over 5 sessions", _cmp(e21, e21_prev), _fmt(e21),
         f"EMA21 {_fmt(e21)} vs {_fmt(e21_prev)} five sessions ago" if e21_prev else "Needs 26 bars")

    # ---------- momentum ----------
    r = _at(data["rsi"], i)
    ml, ms = _at(data["macd"], i), _at(data["macd_signal"], i)
    mh, mh_prev = _at(data["macd_hist"], i), _at(data["macd_hist"], i - 1)
    roc = _at(data["roc10"], i)
    rule("rsi_band", "momentum", f"RSI between {p['rsi_low']:.0f} and {p['rsi_high']:.0f}",
         None if r is None else p["rsi_low"] <= r <= p["rsi_high"], _fmt(r, 1),
         "Momentum positive without being overbought" if r is not None else "Needs 15 bars")
    rule("macd_gt_signal", "momentum", "MACD above its signal line", _cmp(ml, ms), _fmt(ml, 3),
         f"MACD {_fmt(ml, 3)} vs signal {_fmt(ms, 3)}" if ms is not None else "Needs 34 bars")
    rule("macd_hist_rising", "momentum", "MACD histogram rising", _cmp(mh, mh_prev), _fmt(mh, 3),
         f"Histogram {_fmt(mh, 3)} vs {_fmt(mh_prev, 3)} yesterday" if mh_prev is not None else "Needs 35 bars")
    rule("roc_positive", "momentum", "10-day rate of change positive", None if roc is None else roc > 0,
         None if roc is None else f"{roc:+.2f}%", "")

    # ---------- volume ----------
    vol, vavg = data["v"][i], _at(data["vol_sma20"], i)
    obv_now, obv_prev = _at(data["obv"], i), _at(data["obv"], i - 20)
    vol_ratio = (vol / vavg) if vol is not None and vavg else None
    rule("volume_confirm", "volume", f"Volume at least {p['volume_confirm_ratio']:.1f}x the 20-day average",
         None if vol_ratio is None else vol_ratio >= p["volume_confirm_ratio"],
         None if vol_ratio is None else f"{vol_ratio:.2f}x",
         f"{(vol_ratio - 1) * 100:+.0f}% vs 20-day average" if vol_ratio is not None else "Volume data unavailable")
    rule("obv_rising", "volume", "On-balance volume rising over 20 sessions",
         None if i < 20 or not any(data["v"][i - 20:i + 1]) else obv_now > obv_prev, None, "Accumulation proxy")
    upv = dnv = 0.0
    if i >= 20:
        upv = sum((data["v"][j] or 0) for j in range(i - 19, i + 1) if c[j] > c[j - 1])
        dnv = sum((data["v"][j] or 0) for j in range(i - 19, i + 1) if c[j] < c[j - 1])
    ud_ok = None if i < 20 or (upv == 0 and dnv == 0) else upv > dnv
    rule("updown_volume", "volume", "Up-day volume exceeds down-day volume (20 sessions)", ud_ok,
         None if ud_ok is None or dnv == 0 else f"{upv / dnv:.2f}x",
         "" if ud_ok is not None else "No up or down days with volume in the window")

    # ---------- price action ----------
    lookback_start = max(0, i - 250)
    sw = [s for s in ind.confirmed_swings(h, lo, i, k=3) if s.index >= lookback_start]
    structure = ind.trend_structure(sw)
    rule("structure_hh_hl", "price_action", "Higher highs and higher lows",
         None if structure == "insufficient" else structure == "higher_highs_higher_lows", structure.replace("_", " "),
         "Last two confirmed swing highs and lows")
    prior_high = max(h[i - 20:i]) if i >= 20 else None
    breakout = None if prior_high is None else close > prior_high
    rule("breakout_20d", "price_action", "Close above the prior 20-session high", breakout, _fmt(prior_high),
         f"Close {_fmt(close)} vs 20-session high {_fmt(prior_high)}" if prior_high else "Needs 21 bars")
    gp = ind.gaps(data["o"][:i + 1], h[:i + 1], lo[:i + 1], lookback=5)
    gap_down = any(g["direction"] == "down" for g in gp)
    rule("no_gap_down", "price_action", "No gap down in the last 5 sessions", None if i < 5 else not gap_down,
         None, "Gap down found" if gap_down else "")

    # ---------- levels ----------
    tol = max((atr or 0) * 0.5, close * 0.005)
    lv = ind.levels(sw, ref_price=close, tolerance=tol)
    supports = sorted([x for x in lv if x.price < close], key=lambda x: -x.price)
    resist = sorted([x for x in lv if x.price > close], key=lambda x: x.price)
    entry_low = entry_high = stop = None
    level_notes: list[LevelOut] = []
    targets: list[LevelOut] = []
    if atr:
        if breakout:
            entry_low, entry_high = prior_high, prior_high + 0.5 * atr
            level_notes.append(LevelOut("Entry zone", None, "Breakout level to breakout + 0.5 x ATR14"))
        elif supports and close - supports[0].price <= 3 * atr:
            s0 = supports[0].price
            entry_low, entry_high = s0, s0 + 0.5 * atr
            note = f"Pullback to support {s0:,.2f} ({supports[0].touches} touch(es)) to + 0.5 x ATR14"
            level_notes.append(LevelOut("Entry zone", None, note))
        else:
            entry_low, entry_high = close - 0.25 * atr, close + 0.25 * atr
            level_notes.append(LevelOut("Entry zone", None, "Current price +/- 0.25 x ATR14 (no nearby structure)"))
        below = [s for s in supports if s.price < entry_low]
        if below:
            stop = below[0].price - 0.5 * atr
            level_notes.append(LevelOut("Stop", stop, f"Below support {below[0].price:,.2f} minus 0.5 x ATR14"))
        else:
            stop = entry_low - 2 * atr
            level_notes.append(LevelOut("Stop", stop, "Entry minus 2 x ATR14 (no support below entry)"))
        above = [x for x in resist if x.price > entry_high]
        if above:
            targets.append(LevelOut("Target 1", above[0].price, f"Next resistance ({above[0].touches} touch(es))"))
        if breakout and i >= 20:
            height = max(h[i - 20:i]) - min(lo[i - 20:i])
            mm = prior_high + height
            if not targets or mm > targets[-1].price:
                note = "Measured move: breakout + prior 20-session range"
                targets.append(LevelOut(f"Target {len(targets) + 1}", mm, note))
        if len(above) > 1 and (not targets or above[1].price > targets[-1].price):
            targets.append(LevelOut(f"Target {len(targets) + 1}", above[1].price, "Second resistance above entry"))
        targets = targets[:3]
    mid = (entry_low + entry_high) / 2 if entry_low is not None else None
    rr = None
    if mid is not None and stop is not None and targets and mid > stop:
        rr = (targets[0].price - mid) / (mid - stop)

    # ---------- risk ----------
    rule("rr_min", "risk", f"Reward-to-risk at least {p['min_rr']:.1f} to 1",
         None if rr is None else rr >= p["min_rr"], None if rr is None else f"{rr:.2f} : 1",
         "To Target 1 from the middle of the entry zone" if rr is not None
         else "No target supported by price structure")
    atr_pct = [(a / cc * 100) if a and cc else None for a, cc in zip(data["atr"][max(0, i - 250):i + 1],
                                                                    c[max(0, i - 250):i + 1], strict=True)]
    atr_pct_valid = [x for x in atr_pct if x is not None]
    cur_atr_pct = atr_pct[-1] if atr_pct else None
    if cur_atr_pct is not None and len(atr_pct_valid) >= 60:
        med = statistics.median(atr_pct_valid)
        rule("volatility_normal", "risk", "Volatility not elevated (ATR% at most 1.5x its 1-year median)",
             cur_atr_pct <= 1.5 * med, f"{cur_atr_pct:.2f}% vs median {med:.2f}%")
    else:
        rule("volatility_normal", "risk", "Volatility not elevated (ATR% at most 1.5x its 1-year median)", None)

    # ---------- market ----------
    regime_label = (market_regime or {}).get("label")
    rule("market_regime", "market", "Market regime is Trending Up or Sideways",
         None if not regime_label else regime_label in ("Trending Up", "Sideways"), regime_label,
         (market_regime or {}).get("explanation", "Index data unavailable for this market"))

    # ---------- liquidity ----------
    recent = list(range(max(0, i - 59), i + 1))
    flat = sum(1 for j in recent if h[j] == lo[j])
    flat_share = flat / len(recent) if recent else None
    tv = [c[j] * (data["v"][j] or 0) for j in range(max(0, i - 19), i + 1)]
    med_tv = statistics.median(tv) if tv else None
    threshold = p["min_traded_value"].get(currency or "", None)
    rule("traded_value", "liquidity", "20-day median traded value above threshold",
         None if threshold is None or med_tv is None else med_tv >= threshold,
         None if med_tv is None else f"{currency or ''} {med_tv:,.0f}".strip(),
         f"Threshold {currency} {threshold:,.0f}" if threshold else "No threshold set for this currency")
    rule("price_discovery", "liquidity", f"At most {p['flat_bar_max']:.0%} flat bars (high = low) in 60 sessions",
         None if flat_share is None else flat_share <= p["flat_bar_max"],
         None if flat_share is None else f"{flat_share:.0%}", "Flat bars mean no intraday trading range")

    # ---------- score ----------
    # Rules switched off in a strategy stay listed for transparency but carry no weight.
    for x in rules:
        if x.id in disabled_rules:
            x.passed, x.detail = None, "Switched off in this strategy"
    scored_rules = [x for x in rules if x.id not in disabled_rules]
    breakdown = {}
    total_w = sum(w.values()) or 1
    evaluated_w = scored = 0.0
    coverage_w = 0.0
    for cat, weight in w.items():
        cr = [x for x in scored_rules if x.category == cat]
        appl = [x for x in cr if x.passed is not None]
        passed = [x for x in appl if x.passed]
        pct = (len(passed) / len(appl)) if appl else None
        pts = weight * pct if pct is not None else None
        breakdown[cat] = {"label": CATEGORY_LABELS[cat], "weight": weight, "rules": len(cr), "evaluated": len(appl),
                          "passed": len(passed), "pct": pct, "points": pts}
        if appl:
            evaluated_w += weight
            scored += pts
            coverage_w += weight * len(appl) / len(cr)
        elif not cr:
            total_w -= weight  # every rule in the category is switched off: it no longer counts
    score = (scored / evaluated_w * 100) if evaluated_w else None
    coverage = coverage_w / total_w if total_w > 0 else 0.0

    # ---------- classification ----------
    reasons: list[str] = []
    warnings: list[str] = list(extra_warnings or [])
    liq = breakdown["liquidity"]
    trend_pct = breakdown["trend"]["pct"] or 0
    pa_pct = breakdown["price_action"]["pct"] or 0
    if shariah_status == "NON_COMPLIANT":
        stype = "AVOID"
        reasons.append("Shariah screen: NON-COMPLIANT under the selected methodology")
    elif liq["evaluated"] and liq["passed"] == 0:
        stype = "AVOID"
        reasons.append("Liquidity checks failed: prices or volumes too thin for reliable signals")
    elif score is None:
        stype = "WAIT"
    elif coverage < p["min_coverage"]:
        stype = "WATCHLIST" if score >= p["watch_score"] else "WAIT"
        warnings.append(f"Only {coverage:.0%} of the scoring weight could be evaluated; BUY SETUP is withheld")
    elif (score >= p["buy_score"] and trend_pct >= p["min_category_pct"] and pa_pct >= p["min_category_pct"]
          and rr is not None and rr >= p["min_rr"]):
        stype = "BUY_SETUP"
    elif score >= p["watch_score"]:
        stype = "WATCHLIST"
        missing = []
        if score < p["buy_score"]:
            missing.append(f"score {score:.0f} below {p['buy_score']:.0f}")
        if trend_pct < p["min_category_pct"]:
            missing.append("trend confirmation")
        if pa_pct < p["min_category_pct"]:
            missing.append("price-action confirmation")
        if rr is None or rr < p["min_rr"]:
            missing.append(f"reward-to-risk of {p['min_rr']:.1f}")
        if missing:
            reasons.append("Waiting for: " + ", ".join(missing))
    else:
        stype = "WAIT"

    exit_checks: list[dict] = []
    pos_out = None
    if position:
        exit_checks, pos_out = _exit_checks(data, i, position, shariah_status, sw, s50, s200)
        triggered = [x for x in exit_checks if x["triggered"]]
        reasons = []  # the entry-setup reasons do not apply to a holding
        if triggered:
            stype = "SELL_EXIT"
            reasons += [f"{x['label']}: {x['detail']}" for x in triggered]
        else:
            stype = "HOLD"
            reasons.append("Open position: no exit condition is met")
        if position.get("stop") is None:
            warnings.append("No stop is set for this position, so the stop check cannot run")
    for x in rules:
        if x.passed and not position:
            reasons.append(f"{x.label}" + (f" ({x.value})" if x.value else ""))

    if flat_share is not None and flat_share > p["flat_bar_max"]:
        warnings.append(f"{flat_share:.0%} of recent bars are flat; momentum indicators are unreliable here")
    if n < 200 or i < 199:
        warnings.append("Fewer than 200 bars: the 200-day average rules could not be evaluated")
    if shariah_status in (None, "INSUFFICIENT_DATA", "UNDER_REVIEW"):
        warnings.append("Shariah status not established; verify before acting")
    if cur_atr_pct is not None and any(x.id == "volatility_normal" and x.passed is False for x in rules):
        warnings.append("Volatility is elevated relative to the past year")
    warnings.append("Earnings calendar not connected yet; check announcements before acting")

    daily = trend_label(close, s50, s200)
    timeframes = {"15m": "Data unavailable (end-of-day plan)", "1h": "Data unavailable (end-of-day plan)",
                  "4h": "Data unavailable (end-of-day plan)", "daily": daily}
    snapshot = {
        "close": close, "sma20": _at(data["sma20"], i), "sma50": s50, "sma100": _at(data["sma100"], i), "sma200": s200,
        "ema9": _at(data["ema9"], i), "ema21": e21, "ema50": _at(data["ema50"], i), "ema200": _at(data["ema200"], i),
        "rsi": r, "macd": ml, "macd_signal": ms, "macd_hist": mh, "stoch_k": _at(data["stoch_k"], i),
        "stoch_d": _at(data["stoch_d"], i), "roc10": roc, "atr": atr, "atr_pct": cur_atr_pct,
        "bb_up": _at(data["bb_up"], i), "bb_lo": _at(data["bb_lo"], i), "adx": _at(data["adx"], i),
        "volume": vol, "volume_avg20": vavg, "volume_ratio": vol_ratio, "flat_share_60": flat_share,
        "median_traded_value_20": med_tv, "high_52w": max(h[max(0, i - 251):i + 1]),
        "low_52w": min(lo[max(0, i - 251):i + 1]), "structure": structure, "breakout": breakout,
    }
    summary = _summary(stype, score, coverage, close, prior_high, rr, entry_low, entry_high, stop, targets)
    if position:
        summary = _position_summary(stype, exit_checks, pos_out) + " " + summary
    return SignalResult(
        as_of=data["t"][i], close=close, signal_type=stype, score=None if score is None else round(score, 1),
        coverage=round(coverage, 3), breakdown=breakdown, rules=rules, reasons=reasons, warnings=warnings,
        entry_low=entry_low, entry_high=entry_high, stop=stop, targets=targets,
        risk_reward=None if rr is None else round(rr, 2), level_notes=level_notes,
        supports=[{"price": s.price, "touches": s.touches} for s in supports[:3]],
        resistances=[{"price": s.price, "touches": s.touches} for s in resist[:3]],
        snapshot=snapshot, timeframes=timeframes, summary=summary, exit_checks=exit_checks, position=pos_out,
    )


def _exit_checks(data, i, position, shariah_status, sw, s50, s200) -> tuple[list[dict], dict]:
    """Each exit condition for an open position, evaluated on data up to bar i only."""
    c, lo, rsi = data["c"], data["l"], data["rsi"]
    close = c[i]
    entry = float(position["avg_entry"])
    stop = None if position.get("stop") is None else float(position["stop"])
    target = None if position.get("target") is None else float(position["target"])
    checks: list[dict] = []

    def chk(code, label, triggered, detail):
        checks.append({"code": code, "label": label, "triggered": triggered, "detail": detail})

    chk("shariah", "Shariah status", shariah_status == "NON_COMPLIANT",
        "NON-COMPLIANT under the selected methodology; review the holding and purification"
        if shariah_status == "NON_COMPLIANT" else f"Status: {(shariah_status or 'not screened').replace('_', ' ')}")
    chk("stop_hit", "Stop", None if stop is None else close <= stop,
        "No stop set" if stop is None else f"Close {close:,.2f} vs stop {stop:,.2f}")
    chk("target_hit", "Target reached", None if target is None else close >= target,
        "No target set" if target is None else f"Close {close:,.2f} vs target {target:,.2f}")
    low20 = min(lo[i - 20:i]) if i >= 20 else None
    chk("breakdown", "Breakdown below the prior 20-session low", None if low20 is None else close < low20,
        "Needs 21 bars" if low20 is None else f"Close {close:,.2f} vs 20-session low {low20:,.2f}")
    if s50 is None or s200 is None:
        chk("trend_reversal", "Trend reversal", None, "Needs 200 bars")
    else:
        bearish = close < s50 < s200
        chk("trend_reversal", "Trend reversal", bearish,
            f"Close {close:,.2f}, SMA50 {s50:,.2f}, SMA200 {s200:,.2f}"
            + (" (close below SMA50 below SMA200)" if bearish else ""))
    highs = [s for s in sw if s.kind == "high"][-2:]
    if len(highs) == 2 and rsi[highs[0].index] is not None and rsi[highs[1].index] is not None:
        a, b = highs
        div = b.price > a.price and rsi[b.index] < rsi[a.index] and rsi[a.index] >= 70
        chk("bearish_divergence", "Overbought bearish divergence", div,
            f"Swing highs {a.price:,.2f} then {b.price:,.2f}; RSI {rsi[a.index]:.1f} then {rsi[b.index]:.1f}")
    else:
        chk("bearish_divergence", "Overbought bearish divergence", None, "Fewer than two confirmed swing highs")
    if stop is not None and target is not None and stop < close < target:
        rem = (target - close) / (close - stop)
        chk("rr_deterioration", "Remaining reward-to-risk below 1 : 1", rem < 1,
            f"{rem:.2f} : 1 from the close to your target and stop")
    else:
        chk("rr_deterioration", "Remaining reward-to-risk below 1 : 1", None,
            "Needs a stop below and a target above the close")
    qty = float(position.get("quantity") or 0)
    pos_out = {"quantity": qty, "avg_entry": entry, "stop": stop, "target": target, "close": close,
               "unrealised": (close - entry) * qty, "unrealised_pct": (close / entry - 1) * 100 if entry else None}
    return checks, pos_out


def _position_summary(stype, checks, pos) -> str:
    pl = pos.get("unrealised_pct")
    head = f"Open position {'+' if (pl or 0) >= 0 else ''}{pl:.2f}% from the average entry. " if pl is not None else ""
    if stype == "SELL_EXIT":
        return head + "Exit conditions met: " + ", ".join(x["label"].lower() for x in checks if x["triggered"]) + "."
    return head + "No exit condition is met, so the holding is rated HOLD."


def _summary(stype, score, coverage, close, prior_high, rr, el, eh, stop, targets) -> str:
    """One plain-English paragraph, written as an explanation, never as an instruction."""
    if score is None:
        return "Not enough price history to evaluate a setup."
    s = f"Setup score {score:.0f}/100 on {coverage:.0%} of the scoring weight. "
    if stype == "BUY_SETUP":
        s += "Several independent rules agree on a potential long setup. "
    elif stype == "WATCHLIST":
        s += "Some rules support a setup but confirmation is still missing. "
    elif stype == "AVOID":
        s += "A blocking condition applies, so no setup is offered. "
    else:
        s += "Evidence is weak or conflicting; no setup is indicated. "
    if prior_high is not None and close <= prior_high:
        s += f"A daily close above {prior_high:,.2f} (the prior 20-session high) would be a breakout trigger. "
    if stop is not None and el is not None:
        s += f"The setup would be invalidated below {stop:,.2f}. "
    if rr is not None:
        s += f"Reward-to-risk to Target 1 is {rr:.2f} : 1. "
    elif el is not None:
        s += "No target is supported by nearby price structure, so reward-to-risk is not stated. "
    return s.strip()


def weekly_trend(bars: list[dict]) -> str:
    wk = ind.resample_weekly(bars)
    c = [w["c"] for w in wk]
    s10, s40 = ind.sma(c, 10), ind.sma(c, 40)
    return trend_label(c[-1] if c else None, s10[-1] if c else None, s40[-1] if c else None)


def agreement(timeframes: dict) -> str:
    vals = [v for k, v in timeframes.items() if v in ("Bullish", "Bearish", "Neutral")]
    if len(vals) < 2:
        return "Only one timeframe has data; agreement cannot be assessed."
    if len(set(vals)) == 1:
        return f"Daily and weekly trends agree: {vals[0].lower()}."
    return "Daily and weekly trends conflict: " + ", ".join(
        f"{k} {v.lower()}" for k, v in timeframes.items() if v in ("Bullish", "Bearish", "Neutral")) + "."
