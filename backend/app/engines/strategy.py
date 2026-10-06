"""Strategy definition: which rules count, with what weights and thresholds, and how a backtest exits.

A strategy is data (stored in strategies.rules and strategies.weights), validated here so the
signal engine and the backtester read exactly the same configuration.
"""

from __future__ import annotations

from app.engines.signals import CATEGORY_LABELS, DEFAULT_PARAMS, DEFAULT_WEIGHTS

RULES: list[tuple[str, str, str]] = [
    ("close_gt_sma50", "trend", "Price above 50-day SMA"),
    ("sma50_gt_sma200", "trend", "50-day SMA above 200-day SMA"),
    ("close_gt_sma200", "trend", "Price above 200-day SMA"),
    ("ema21_rising", "trend", "21-day EMA rising over 5 sessions"),
    ("rsi_band", "momentum", "RSI inside the momentum band"),
    ("macd_gt_signal", "momentum", "MACD above its signal line"),
    ("macd_hist_rising", "momentum", "MACD histogram rising"),
    ("roc_positive", "momentum", "10-day rate of change positive"),
    ("volume_confirm", "volume", "Volume above the confirmation ratio"),
    ("obv_rising", "volume", "On-balance volume rising over 20 sessions"),
    ("updown_volume", "volume", "Up-day volume exceeds down-day volume"),
    ("structure_hh_hl", "price_action", "Higher highs and higher lows"),
    ("breakout_20d", "price_action", "Close above the prior 20-session high"),
    ("no_gap_down", "price_action", "No gap down in the last 5 sessions"),
    ("rr_min", "risk", "Reward-to-risk at least the minimum"),
    ("volatility_normal", "risk", "Volatility not elevated"),
    ("market_regime", "market", "Market regime is Trending Up or Sideways"),
    ("traded_value", "liquidity", "20-day median traded value above threshold"),
    ("price_discovery", "liquidity", "Few flat bars (high = low)"),
]
RULE_IDS = {r[0] for r in RULES}

# key: (label, min, max)
PARAM_LIMITS: dict[str, tuple[str, float, float]] = {
    "buy_score": ("Score for POTENTIAL BUY SETUP", 50, 95),
    "watch_score": ("Score for WATCHLIST", 30, 90),
    "min_rr": ("Minimum reward-to-risk", 0.5, 10),
    "min_coverage": ("Minimum coverage of the scoring weight", 0.3, 1),
    "min_category_pct": ("Trend and price action must each pass at least", 0, 1),
    "rsi_low": ("RSI band low", 0, 100),
    "rsi_high": ("RSI band high", 0, 100),
    "volume_confirm_ratio": ("Volume confirmation ratio", 0.5, 5),
    "flat_bar_max": ("Maximum share of flat bars", 0, 1),
}

EXIT_DEFAULTS = {
    "stop": "signal",          # signal = the setup's stop level; atr = entry - stop_atr x ATR14
    "stop_atr": 2.0,
    "target": "signal",        # signal = Target 1; r_multiple = entry + target_r x risk; none
    "target_r": 2.0,
    "max_hold_days": 60,       # 0 = no time exit
    "exit_on": ["breakdown", "trend_reversal"],  # engine exit checks that close a trade at the next open
}
EXIT_CHECKS = {"breakdown": "Close below the prior 20-session low", "trend_reversal": "Close below SMA50 below SMA200",
               "bearish_divergence": "Overbought bearish divergence"}
ENTRY_TYPES = ("BUY_SETUP", "WATCHLIST")


def config(weights: dict | None, rules: dict | None) -> dict:
    """Merged, defaulted strategy configuration."""
    rules = rules or {}
    return {
        "weights": {**DEFAULT_WEIGHTS, **(weights or {})},
        "params": {**DEFAULT_PARAMS, **(rules.get("params") or {})},
        "disabled": sorted(set(rules.get("disabled") or []) & RULE_IDS),
        "entry_on": [t for t in (rules.get("entry_on") or ["BUY_SETUP"]) if t in ENTRY_TYPES] or ["BUY_SETUP"],
        "exit": {**EXIT_DEFAULTS, **(rules.get("exit") or {})},
    }


def validate(weights: dict, params: dict, disabled: list[str], entry_on: list[str], exit_: dict) -> list[str]:
    errors: list[str] = []
    if set(weights) - set(DEFAULT_WEIGHTS):
        errors.append("Unknown weight categories")
    if any(not isinstance(v, int | float) or v < 0 or v > 100 for v in weights.values()):
        errors.append("Each weight must be between 0 and 100")
    if sum(weights.values()) <= 0:
        errors.append("At least one weight must be positive")
    for k, v in params.items():
        if k not in PARAM_LIMITS:
            errors.append(f"Unknown parameter {k}")
            continue
        _, lo, hi = PARAM_LIMITS[k]
        if not isinstance(v, int | float) or not lo <= v <= hi:
            errors.append(f"{PARAM_LIMITS[k][0]} must be between {lo:g} and {hi:g}")
    merged = {**DEFAULT_PARAMS, **params}
    if merged["watch_score"] >= merged["buy_score"]:
        errors.append("The WATCHLIST score must be below the BUY SETUP score")
    if merged["rsi_low"] >= merged["rsi_high"]:
        errors.append("The RSI band low must be below its high")
    if set(disabled) - RULE_IDS:
        errors.append("Unknown rules")
    if len(set(disabled)) >= len(RULE_IDS):
        errors.append("At least one rule must stay on")
    if not entry_on or set(entry_on) - set(ENTRY_TYPES):
        errors.append("Entry must be on BUY_SETUP and optionally WATCHLIST")
    if exit_.get("stop") not in ("signal", "atr"):
        errors.append("Stop must be 'signal' or 'atr'")
    if not 0.5 <= float(exit_.get("stop_atr", 2)) <= 10:
        errors.append("ATR stop multiple must be between 0.5 and 10")
    if exit_.get("target") not in ("signal", "r_multiple", "none"):
        errors.append("Target must be 'signal', 'r_multiple' or 'none'")
    if not 0.5 <= float(exit_.get("target_r", 2)) <= 20:
        errors.append("Target R multiple must be between 0.5 and 20")
    if not 0 <= int(exit_.get("max_hold_days", 0)) <= 1000:
        errors.append("Maximum holding period must be between 0 and 1000 sessions")
    if set(exit_.get("exit_on") or []) - set(EXIT_CHECKS):
        errors.append("Unknown exit check")
    return errors


def catalogue() -> dict:
    return {"rules": [{"id": i, "category": c, "category_label": CATEGORY_LABELS[c], "label": label}
                      for i, c, label in RULES],
            "categories": CATEGORY_LABELS, "default_weights": DEFAULT_WEIGHTS,
            "params": [{"key": k, "label": v[0], "min": v[1], "max": v[2], "default": DEFAULT_PARAMS[k]}
                       for k, v in PARAM_LIMITS.items()],
            "exit_defaults": EXIT_DEFAULTS, "exit_checks": EXIT_CHECKS, "entry_types": list(ENTRY_TYPES)}
