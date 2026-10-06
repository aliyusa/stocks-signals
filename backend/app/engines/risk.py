"""Position sizing from account size, risk per trade, entry and stop. Pure arithmetic, shown step by step."""

from __future__ import annotations

import math


def position_size(*, account: float, risk_pct: float, entry: float, stop: float, target: float | None = None,
                  lot_size: int = 1, cost_pct_per_side: float = 0.0, max_position_pct: float = 100.0) -> dict:
    """Shares such that a fill at `entry` and an exit at `stop`, including costs on both sides, loses at most
    `risk_pct` of `account`. Long positions only (the platform screens for long, Shariah-compliant holdings)."""
    errors = []
    if account <= 0:
        errors.append("Account size must be positive")
    if not 0 < risk_pct <= 10:
        errors.append("Risk per trade must be above 0% and at most 10%")
    if entry <= 0 or stop <= 0:
        errors.append("Entry and stop must be positive")
    elif stop >= entry:
        errors.append("The stop must be below the entry for a long position")
    if target is not None and target <= entry:
        errors.append("The target must be above the entry")
    if lot_size < 1:
        errors.append("Lot size must be at least 1")
    if not 0 <= cost_pct_per_side < 10:
        errors.append("Costs must be between 0% and 10% per side")
    if errors:
        return {"ok": False, "errors": errors}

    c = cost_pct_per_side / 100
    risk_amount = account * risk_pct / 100
    loss_per_share = (entry - stop) + c * (entry + stop)  # price move plus costs paid on entry and exit
    raw = risk_amount / loss_per_share
    shares = math.floor(raw / lot_size) * lot_size
    capped_by = None
    max_value = account * max_position_pct / 100
    if shares * entry * (1 + c) > max_value:
        shares = math.floor(max_value / (entry * (1 + c)) / lot_size) * lot_size
        capped_by = f"maximum position of {max_position_pct:g}% of the account"
    value = shares * entry
    out = {
        "ok": True,
        "shares": shares,
        "position_value": value,
        "position_pct": value / account * 100,
        "entry_costs": value * c,
        "risk_amount_allowed": risk_amount,
        "loss_per_share": loss_per_share,
        "loss_at_stop": shares * loss_per_share,
        "loss_at_stop_pct": shares * loss_per_share / account * 100,
        "stop_distance_pct": (entry - stop) / entry * 100,
        "capped_by": capped_by,
        "steps": [
            f"Risk allowed: {account:,.2f} × {risk_pct:g}% = {risk_amount:,.2f}",
            f"Loss per share at the stop: ({entry:,.2f} − {stop:,.2f}) + costs {c * (entry + stop):,.4f} "
            f"= {loss_per_share:,.4f}",
            f"Shares: {risk_amount:,.2f} ÷ {loss_per_share:,.4f} = {raw:,.2f}, rounded down to a multiple of "
            f"{lot_size} = {shares:,}" + (f", then capped by the {capped_by}" if capped_by else ""),
        ],
        "warnings": [],
    }
    if shares == 0:
        out["warnings"].append("The risk budget is smaller than one lot at this stop distance; no position fits.")
    if target is not None and shares:
        gain_per_share = (target - entry) - c * (entry + target)
        out.update({"gain_at_target": shares * gain_per_share,
                    "reward_risk": gain_per_share / loss_per_share if loss_per_share > 0 else None})
        if out["reward_risk"] is not None and out["reward_risk"] < 1:
            out["warnings"].append("After costs the reward is smaller than the risk.")
    if (entry - stop) / entry < 0.01:
        out["warnings"].append("The stop is within 1% of the entry; normal daily noise may hit it.")
    return out
