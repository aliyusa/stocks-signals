"""Shariah screening engine: business-activity screen plus financial-ratio screens.

Pure functions. The engine never fetches data and never fills a gap: a missing input makes the
affected test "insufficient", and the stock cannot be COMPLIANT until it is supplied.
See docs/ARCHITECTURE.md §4 for the methodology and the status order.

Status order (first match wins):
  1. NON_COMPLIANT      a primary business is prohibited, a secondary prohibited activity is at or
                        above the income threshold, or any ratio is at or above its threshold
  2. UNDER_REVIEW       a reviewer has flagged the stock
  3. INSUFFICIENT_DATA  a required input is missing, or the fundamentals are older than the limit
  4. QUESTIONABLE       a ratio is within the questionable margin of its threshold, a secondary
                        prohibited activity has an unknown revenue share, or an external screen disagrees
  5. COMPLIANT          every test passes on fresh data
"""

from __future__ import annotations

from datetime import date

PROHIBITED_ACTIVITIES: dict[str, str] = {
    "conventional_banking": "Conventional (interest-based) banking",
    "conventional_lending": "Conventional lending, microfinance or leasing on interest",
    "conventional_insurance": "Conventional insurance",
    "alcohol": "Alcohol",
    "gambling": "Gambling, betting or lotteries",
    "pork": "Pork and non-halal meat",
    "adult_entertainment": "Adult entertainment",
    "tobacco": "Tobacco",
    "weapons_defence": "Weapons and defence",
    "impermissible_entertainment": "Impermissible entertainment (music, cinema, hotels with bars and similar)",
}
PERMISSIBLE_ACTIVITIES: dict[str, str] = {
    "permissible": "Permissible business (describe it in the label)",
    "islamic_banking": "Islamic banking (non-interest)",
    "takaful": "Takaful (Islamic insurance)",
}
ACTIVITY_LABELS = {**PROHIBITED_ACTIVITIES, **PERMISSIBLE_ACTIVITIES}
ISLAMIC_FINANCE = {"islamic_banking", "takaful"}

DENOMINATORS: dict[str, str] = {
    "market_cap": "Market capitalisation",
    "total_assets": "Total assets",
    "avg_market_cap_36m": "36-month average market capitalisation",
}

THRESHOLD_KEYS: dict[str, str] = {
    "debt_to_denominator": "Interest-bearing debt",
    "cash_securities_to_denominator": "Cash and interest-bearing securities",
    "receivables_to_denominator": "Receivables",
    "non_permissible_income_to_revenue": "Non-permissible income",
    "questionable_margin": "Questionable margin",
}

# The fields a manual fundamentals entry may carry (all optional; missing means unknown).
FUNDAMENTAL_FIELDS = (
    "revenue", "net_income", "total_debt", "interest_bearing_debt", "cash", "interest_bearing_securities",
    "receivables", "total_assets", "total_equity", "interest_income", "non_permissible_income", "market_cap",
    "shares_outstanding", "dividend_per_share",
)

STATUS_SUMMARY = {
    "COMPLIANT": "Every business and ratio test passes on fundamentals inside the freshness limit.",
    "NON_COMPLIANT": "At least one test fails under this methodology.",
    "QUESTIONABLE": "No test fails, but at least one result is close to its limit or uncertain.",
    "INSUFFICIENT_DATA": "Required inputs are missing or out of date, so no pass is assumed.",
    "UNDER_REVIEW": "A reviewer has flagged this stock; the computed result is shown for reference.",
}


def _num(v) -> float | None:
    return None if v is None else float(v)


def _pct(v: float | None) -> str:
    return "n/a" if v is None else f"{v * 100:.1f}%"


def business_screen(activities: list[dict], prohibited: list[str], income_threshold: float) -> dict:
    items, statuses = [], []
    prohibited_set = set(prohibited)
    for a in activities or []:
        tag = a.get("tag", "")
        primary = bool(a.get("primary"))
        share = _num(a.get("revenue_share"))
        is_prohibited = tag in prohibited_set
        label = a.get("label") or ACTIVITY_LABELS.get(tag, tag)
        if tag in ISLAMIC_FINANCE:
            result, note = "pass", "Islamic finance: the conventional-finance exclusions do not apply."
        elif not is_prohibited:
            result, note = "pass", "Not on this methodology's excluded list."
        elif primary:
            result, note = "fail", "Primary business is on the excluded list."
        elif share is None:
            result, note = "questionable", "Excluded activity with an unknown revenue share."
        elif share >= income_threshold:
            result, note = "fail", f"{_pct(share)} of revenue, at or above the {_pct(income_threshold)} limit."
        else:
            result = "pass"
            note = (f"{_pct(share)} of revenue, below the {_pct(income_threshold)} limit. Include this income in "
                    "non-permissible income so it counts towards the income ratio and purification.")
        items.append({"tag": tag, "label": label, "primary": primary, "revenue_share": share,
                      "prohibited": is_prohibited, "result": result, "note": note,
                      "source": a.get("source"), "as_of": a.get("as_of")})
        statuses.append(result)

    if not items:
        return {"result": "insufficient", "items": [],
                "message": "No business activities are recorded for this stock. Add the primary business."}
    if not any(i["primary"] for i in items):
        statuses.append("insufficient")
        message = "No activity is marked as the primary business."
    else:
        message = None
    for r in ("fail", "insufficient", "questionable"):
        if r in statuses:
            return {"result": r, "items": items, "message": message or {
                "fail": "An excluded activity fails the business screen.",
                "insufficient": "Business information is incomplete.",
                "questionable": "An excluded activity has an unknown revenue share.",
            }[r]}
    return {"result": "pass", "items": items, "message": "No excluded activity at a disqualifying level."}


def _ratio(rid: str, label: str, num: float | None, num_note: str, num_fields: list[str],
           den: dict, den_label: str, threshold: float, margin: float) -> dict:
    den_value = den.get("value")
    out = {"id": rid, "label": label, "threshold": threshold, "op": "<",
           "numerator": {"value": num, "fields": num_fields, "note": num_note},
           "denominator": {"name": den_label, "value": den_value, "method": den.get("method"),
                           "as_of": den.get("as_of")},
           "value": None, "result": "insufficient", "note": None}
    if num is None:
        out["note"] = f"Missing input: {num_note}"
        return out
    if den_value is None or den_value <= 0:
        out["note"] = f"{den_label} unavailable: {den.get('reason') or 'no value'}"
        return out
    v = num / den_value
    out["value"] = v
    if v >= threshold:
        out["result"], out["note"] = "fail", f"{_pct(v)} is at or above the {_pct(threshold)} limit."
    elif v >= threshold * (1 - margin):
        out["result"] = "near"
        out["note"] = f"{_pct(v)} passes but is within {margin * 100:.0f}% of the {_pct(threshold)} limit."
    else:
        out["result"], out["note"] = "pass", f"{_pct(v)} is below the {_pct(threshold)} limit."
    return out


def ratio_screens(f: dict | None, denominators: dict[str, dict], methodology: dict) -> list[dict]:
    t = methodology["thresholds"]
    margin = float(t.get("questionable_margin", 0.10))
    dkey = methodology["denominator"]
    den = denominators.get(dkey) or {"value": None, "reason": "not computed"}
    den_label = DENOMINATORS.get(dkey, dkey)
    f = f or {}
    g = {k: _num(f.get(k)) for k in FUNDAMENTAL_FIELDS}
    out = []

    if "debt_to_denominator" in t:
        if g["interest_bearing_debt"] is not None:
            num, note, fields = g["interest_bearing_debt"], "interest-bearing debt", ["interest_bearing_debt"]
        elif g["total_debt"] is not None:
            num, fields = g["total_debt"], ["total_debt"]
            note = "total debt, used as a conservative stand-in for interest-bearing debt"
        else:
            num, note, fields = None, "interest-bearing debt (or total debt)", ["interest_bearing_debt"]
        out.append(_ratio("debt", "Interest-bearing debt", num, note, fields, den, den_label,
                          float(t["debt_to_denominator"]), margin))

    if "cash_securities_to_denominator" in t:
        cash, sec = g["cash"], g["interest_bearing_securities"]
        num = None if cash is None or sec is None else cash + sec
        note = ("cash and equivalents plus interest-bearing securities; all cash counts, a conservative stand-in "
                "for interest-bearing deposits")
        if cash is None or sec is None:
            missing = [k for k, v in (("cash", cash), ("interest-bearing securities", sec)) if v is None]
            note = " and ".join(missing) + " (enter 0 if the company holds none)"
        out.append(_ratio("cash_securities", "Cash and interest-bearing securities", num, note,
                          ["cash", "interest_bearing_securities"], den, den_label,
                          float(t["cash_securities_to_denominator"]), margin))

    if "receivables_to_denominator" in t:
        out.append(_ratio("receivables", "Receivables", g["receivables"], "receivables", ["receivables"], den,
                          den_label, float(t["receivables_to_denominator"]), margin))

    if "non_permissible_income_to_revenue" in t:
        ii, npi, rev = g["interest_income"], g["non_permissible_income"], g["revenue"]
        num = None if ii is None or npi is None else ii + npi
        note = "interest income plus other non-permissible income"
        if num is None:
            missing = [k for k, v in (("interest income", ii), ("other non-permissible income", npi)) if v is None]
            note = " and ".join(missing) + " (enter 0 if there is none)"
        rden = {"value": rev, "method": "Revenue for the same period", "reason": "revenue not entered"}
        out.append(_ratio("income", "Non-permissible income", num, note,
                          ["interest_income", "non_permissible_income"], rden, "Revenue",
                          float(t["non_permissible_income_to_revenue"]), margin))
    return out


def purification(f: dict | None, currency: str | None) -> dict | None:
    if not f:
        return None
    dps, rev = _num(f.get("dividend_per_share")), _num(f.get("revenue"))
    ii, npi = _num(f.get("interest_income")), _num(f.get("non_permissible_income"))
    if dps is None or not rev or ii is None or npi is None:
        return None
    share = (ii + npi) / rev
    return {"ratio": share, "per_share": dps * share, "dividend_per_share": dps, "currency": currency,
            "note": "Amount per share to give away from each dividend received: dividend per share × the "
                    "non-permissible share of revenue for the same period. Gains on sale are not covered."}


def screen(*, fundamentals: dict | None, denominators: dict[str, dict], activities: list[dict],
           methodology: dict, as_of: date, external: list[dict] | None = None,
           review_note: str | None = None) -> dict:
    """Screen one stock under one methodology. `fundamentals` is one period's values plus metadata
    (period_end, period_type, currency, source, reported_at, id); None means none are stored."""
    t = methodology["thresholds"]
    income_threshold = float(t.get("non_permissible_income_to_revenue", 0.05))
    business = business_screen(activities, methodology.get("prohibited_activities", []), income_threshold)
    ratios = ratio_screens(fundamentals, denominators, methodology)
    warnings: list[str] = []
    reasons: list[str] = []

    data = None
    fresh = False
    if fundamentals:
        pe = fundamentals.get("period_end")
        age = (as_of - pe).days if pe else None
        max_age = int(methodology.get("max_data_age_days", 190))
        fresh = age is not None and age <= max_age
        data = {"period_end": pe.isoformat() if pe else None, "period_type": fundamentals.get("period_type"),
                "currency": fundamentals.get("currency"), "source": fundamentals.get("source"),
                "source_ref": fundamentals.get("source_ref"), "is_estimate": bool(fundamentals.get("is_estimate")),
                "reported_at": fundamentals.get("reported_at"), "age_days": age, "max_age_days": max_age,
                "fresh": fresh, "id": fundamentals.get("id")}
        if not fresh:
            warnings.append(f"Fundamentals are {age} days old (period ending {pe:%d %b %Y}); the limit is "
                            f"{max_age} days. Enter a newer report.")
        if fundamentals.get("is_estimate"):
            warnings.append("Fundamentals are marked as estimates, not reported figures.")
    else:
        reasons.append("No fundamentals are stored for this stock, so the ratio tests cannot run.")

    fails = [r for r in ratios if r["result"] == "fail"]
    insufficient = [r for r in ratios if r["result"] == "insufficient"]
    near = [r for r in ratios if r["result"] == "near"]

    ext = [e for e in (external or []) if e.get("status") in ("COMPLIANT", "NON_COMPLIANT")]

    if business["result"] == "fail" or fails:
        status = "NON_COMPLIANT"
        if business["result"] == "fail":
            reasons.append(business["message"])
        reasons += [f"{r['label']}: {r['note']}" for r in fails]
        if fundamentals and not fresh and fails:
            warnings.append("A failing ratio is based on old fundamentals; re-check with the latest report.")
        if any(e["status"] == "COMPLIANT" for e in ext):
            warnings.append("An external screen lists this stock as compliant; methodologies differ.")
    elif review_note:
        status = "UNDER_REVIEW"
        reasons.append(f"Reviewer note: {review_note}")
    elif business["result"] == "insufficient" or insufficient or not fundamentals or not fresh:
        status = "INSUFFICIENT_DATA"
        if business["result"] == "insufficient":
            reasons.append(business["message"])
        reasons += [f"{r['label']}: {r['note']}" for r in insufficient]
        if fundamentals and not fresh:
            reasons.append("Fundamentals are older than the freshness limit.")
    else:
        disagree = [e for e in ext if e["status"] == "NON_COMPLIANT"]
        if business["result"] == "questionable" or near or disagree:
            status = "QUESTIONABLE"
            if business["result"] == "questionable":
                reasons.append(business["message"])
            reasons += [f"{r['label']}: {r['note']}" for r in near]
            reasons += [f"{e.get('source', 'An external screen')} lists it as NON-COMPLIANT" for e in disagree]
        else:
            status = "COMPLIANT"
            reasons.append("All business and ratio tests pass.")

    return {
        "status": status,
        "summary": STATUS_SUMMARY[status],
        "reasons": reasons,
        "warnings": warnings,
        "business": business,
        "ratios": ratios,
        "data": data,
        "purification": purification(fundamentals, (fundamentals or {}).get("currency")),
        "external": external or [],
        "review_note": review_note,
        "as_of": as_of.isoformat(),
        "methodology": {"id": methodology.get("id"), "code": methodology.get("code"),
                        "name": methodology.get("name"), "denominator": methodology["denominator"],
                        "denominator_label": DENOMINATORS.get(methodology["denominator"])},
    }


def validate_methodology(thresholds: dict, denominator: str, prohibited: list[str], max_age: int) -> list[str]:
    errors = []
    unknown = set(thresholds) - set(THRESHOLD_KEYS)
    if unknown:
        errors.append(f"Unknown thresholds: {', '.join(sorted(unknown))}")
    for k, v in thresholds.items():
        if not isinstance(v, int | float) or not (0 < v < 1):
            errors.append(f"{k} must be a fraction between 0 and 1 (for example 0.30 for 30%)")
    if "non_permissible_income_to_revenue" not in thresholds:
        errors.append("non_permissible_income_to_revenue is required")
    if not any(k.endswith("_to_denominator") for k in thresholds):
        errors.append("At least one balance-sheet ratio is required")
    if denominator not in DENOMINATORS:
        errors.append(f"Denominator must be one of {', '.join(DENOMINATORS)}")
    bad = set(prohibited) - set(PROHIBITED_ACTIVITIES)
    if bad:
        errors.append(f"Unknown activities: {', '.join(sorted(bad))}")
    if not (30 <= max_age <= 730):
        errors.append("Maximum data age must be between 30 and 730 days")
    return errors
