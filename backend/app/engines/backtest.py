"""Walk-forward backtest of a strategy on one stock's daily bars.

Guarantees (tested with a shifted-future canary, see tests/test_backtest.py):
- the decision on bar t uses only bars up to and including t (the same `evaluate` as live signals);
- entries fill at the next bar's open plus slippage; exits at a stop or target fill intrabar at that level
  (or at the open if the bar gaps through it); signal and time exits fill at the next open;
- when a bar touches both the stop and the target, the stop is assumed first (conservative);
- commission and slippage are charged on both sides;
- the market-regime rule is not evaluated (no point-in-time index data is passed), and is reported so.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from datetime import date

from app.engines.signals import compute, evaluate


def _dd(curve: list[float]) -> float:
    peak, worst = -math.inf, 0.0
    for v in curve:
        peak = max(peak, v)
        if peak > 0:
            worst = min(worst, v / peak - 1)
    return worst * 100


def run(bars: list[dict], cfg: dict, *, currency: str | None, start: date, end: date, capital: float = 1_000_000.0,
        commission_bps: float = 0.0, slippage_bps: float = 0.0, sizing: str = "all_in", risk_pct: float = 1.0,
        shariah_gate: Callable[[date], str | None] | None = None, require_compliant: bool = False,
        data: dict | None = None) -> dict:
    data = data or compute(bars)
    o, h, lo, c, t = data["o"], data["h"], data["l"], data["c"], data["t"]
    idx = [i for i, d in enumerate(t) if start <= d <= end]
    if len(idx) < 2:
        return {"ok": False, "error": "Fewer than 2 stored bars in the chosen period"}
    i0, i1 = idx[0], idx[-1]
    com, slip = commission_bps / 10_000, slippage_bps / 10_000
    ex = cfg["exit"]
    cash, pos, pending_entry, pending_exit = capital, None, None, None
    trades: list[dict] = []
    skipped: dict[str, int] = {}
    curve, bh_curve, dates = [], [], []
    bars_in = 0

    def skip(reason):
        skipped[reason] = skipped.get(reason, 0) + 1

    def close_pos(i, raw_price, reason):
        nonlocal cash, pos
        fill = raw_price * (1 - slip)
        proceeds = pos["shares"] * fill
        cash += proceeds - proceeds * com
        cost = pos["shares"] * pos["entry"] * (1 + com)
        pl = proceeds * (1 - com) - cost
        risk_ps = pos["entry"] - pos["stop"]
        trades.append({
            "entry_date": t[pos["i"]].isoformat(), "entry": pos["entry"], "shares": pos["shares"],
            "stop": pos["stop"], "target": pos["target"], "exit_date": t[i].isoformat(), "exit": fill,
            "reason": reason, "pl": pl, "pl_pct": pl / cost * 100, "bars_held": i - pos["i"],
            "r_multiple": ((fill - pos["entry"]) / risk_ps) if risk_ps > 0 else None,
            "signal": pos["signal"], "score": pos["score"], "signal_date": pos["signal_date"],
        })
        pos = None

    for i in range(i0, i1 + 1):
        # 1. exits decided at the previous close fill at this open
        if pending_exit and pos:
            close_pos(i, o[i], pending_exit)
        pending_exit = None
        # 2. entries decided at the previous close fill at this open
        if pending_entry and pos is None:
            pe, pending_entry = pending_entry, None
            fill = o[i] * (1 + slip)
            stop = pe["stop"] if ex["stop"] == "signal" else (fill - ex["stop_atr"] * pe["atr"] if pe["atr"] else None)
            if stop is None:
                skip("no stop level available")
            elif fill <= stop:
                skip("opened at or below the stop")
            else:
                if ex["target"] == "signal":
                    target = pe["target"]
                elif ex["target"] == "r_multiple":
                    target = fill + ex["target_r"] * (fill - stop)
                else:
                    target = None
                if sizing == "risk_pct":
                    per_share = (fill - stop) + com * (fill + stop)
                    shares = math.floor(cash * risk_pct / 100 / per_share)
                    shares = min(shares, math.floor(cash / (fill * (1 + com))))
                else:
                    shares = math.floor(cash / (fill * (1 + com)))
                if shares <= 0:
                    skip("cash too small for one share")
                else:
                    cash -= shares * fill * (1 + com)
                    pos = {"i": i, "entry": fill, "shares": shares, "stop": stop, "target": target,
                           "signal": pe["signal"], "score": pe["score"], "signal_date": pe["date"]}
        # 3. stop or target touched during this bar
        if pos:
            if lo[i] <= pos["stop"]:
                close_pos(i, min(o[i], pos["stop"]) if i > pos["i"] else pos["stop"], "stop")
            elif pos["target"] is not None and h[i] >= pos["target"]:
                close_pos(i, max(o[i], pos["target"]) if i > pos["i"] else pos["target"], "target")
        # 4. decisions at this close (data up to i only)
        if i < i1:
            if pos:
                if ex["max_hold_days"] and i - pos["i"] >= ex["max_hold_days"]:
                    pending_exit = "time"
                elif ex["exit_on"]:
                    r = evaluate(data, i, weights=cfg["weights"], params=cfg["params"], currency=currency,
                                 disabled_rules=set(cfg["disabled"]),
                                 position={"quantity": pos["shares"], "avg_entry": pos["entry"]})
                    hit = [x["code"] for x in r.exit_checks if x["triggered"] and x["code"] in ex["exit_on"]]
                    if hit:
                        pending_exit = hit[0]
            else:
                r = evaluate(data, i, weights=cfg["weights"], params=cfg["params"], currency=currency,
                             disabled_rules=set(cfg["disabled"]))
                if r.signal_type in cfg["entry_on"]:
                    status = shariah_gate(t[i]) if shariah_gate else None
                    if status == "NON_COMPLIANT":
                        skip("Shariah NON-COMPLIANT on the signal date")
                    elif require_compliant and status != "COMPLIANT":
                        skip("Shariah status not COMPLIANT on the signal date")
                    else:
                        pending_entry = {"stop": r.stop, "target": r.targets[0].price if r.targets else None,
                                         "atr": r.snapshot.get("atr"), "signal": r.signal_type, "score": r.score,
                                         "date": t[i].isoformat()}
        if pos:
            bars_in += 1
        equity = cash + (pos["shares"] * c[i] if pos else 0)
        curve.append(equity)
        bh_curve.append(capital * c[i] / c[i0])
        dates.append(t[i].isoformat())

    open_at_end = None
    if pos:
        open_at_end = {"entry_date": t[pos["i"]].isoformat(), "entry": pos["entry"], "shares": pos["shares"],
                       "mark": c[i1], "unrealised": pos["shares"] * (c[i1] - pos["entry"])}
        close_pos(i1, c[i1], "end of test (marked at the last close)")
        curve[-1] = cash

    wins = [x for x in trades if x["pl"] > 0]
    losses = [x for x in trades if x["pl"] <= 0]
    gross_win, gross_loss = sum(x["pl"] for x in wins), -sum(x["pl"] for x in losses)
    days = (t[i1] - t[i0]).days or 1
    total = curve[-1] / capital - 1
    rs = [x["r_multiple"] for x in trades if x["r_multiple"] is not None]
    step = max(1, math.ceil(len(curve) / 400))
    metrics = {
        "trades": len(trades), "wins": len(wins), "losses": len(losses),
        "win_rate": len(wins) / len(trades) * 100 if trades else None,
        "avg_gain_pct": sum(x["pl_pct"] for x in wins) / len(wins) if wins else None,
        "avg_loss_pct": sum(x["pl_pct"] for x in losses) / len(losses) if losses else None,
        "profit_factor": gross_win / gross_loss if gross_loss > 0 else None,
        "max_drawdown_pct": _dd(curve), "avg_r": sum(rs) / len(rs) if rs else None,
        "total_return_pct": total * 100,
        "annualised_return_pct": ((1 + total) ** (365.25 / days) - 1) * 100 if total > -1 else -100.0,
        "exposure_pct": bars_in / len(curve) * 100,
        "buy_hold_return_pct": (c[i1] / c[i0] - 1) * 100, "buy_hold_max_drawdown_pct": _dd(bh_curve),
        "start": t[i0].isoformat(), "end": t[i1].isoformat(), "bars": len(curve),
        "final_equity": curve[-1], "capital": capital, "skipped": skipped, "open_at_end": open_at_end,
        "equity": [{"t": dates[k], "v": round(curve[k], 2), "bh": round(bh_curve[k], 2)}
                   for k in list(range(0, len(curve), step)) + ([len(curve) - 1] if (len(curve) - 1) % step else [])],
    }
    return {"ok": True, "metrics": metrics, "trades": trades}
