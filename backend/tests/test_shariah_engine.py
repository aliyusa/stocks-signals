"""Pure engine tests with hand-checked numbers. Figures are invented test inputs, not company data."""

from datetime import date

from app.engines.shariah import screen, validate_methodology

AAOIFI = {"id": 1, "code": "aaoifi_based", "name": "AAOIFI-based", "denominator": "market_cap",
          "max_data_age_days": 190, "prohibited_activities": ["alcohol", "conventional_banking", "gambling"],
          "thresholds": {"debt_to_denominator": 0.30, "cash_securities_to_denominator": 0.30,
                         "non_permissible_income_to_revenue": 0.05, "questionable_margin": 0.10}}
TOTAL_ASSETS = {**AAOIFI, "denominator": "total_assets",
                "thresholds": {**AAOIFI["thresholds"], "receivables_to_denominator": 0.49}}

AS_OF = date(2026, 10, 1)
CEMENT = [{"tag": "permissible", "label": "Cement manufacturing", "primary": True}]


def fund(**kw):
    base = {"period_end": date(2026, 6, 30), "period_type": "H", "currency": "NGN", "source": "Manual",
            "revenue": 1000.0, "interest_bearing_debt": 200.0, "cash": 100.0, "interest_bearing_securities": 0.0,
            "receivables": 50.0, "total_assets": 2000.0, "interest_income": 10.0, "non_permissible_income": 0.0,
            "dividend_per_share": 20.0}
    base.update(kw)
    return base


MCAP = {"market_cap": {"value": 1000.0, "method": "test"}}


def ratio(r, rid):
    return next(x for x in r["ratios"] if x["id"] == rid)


def test_compliant_with_exact_ratios():
    r = screen(fundamentals=fund(), denominators=MCAP, activities=CEMENT, methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "COMPLIANT"
    assert ratio(r, "debt")["value"] == 0.20 and ratio(r, "debt")["result"] == "pass"
    assert ratio(r, "cash_securities")["value"] == 0.10
    assert ratio(r, "income")["value"] == 0.01
    assert r["purification"]["per_share"] == 0.2  # 20 × (10 / 1000)
    assert r["data"]["age_days"] == 93 and r["data"]["fresh"]


def test_debt_at_threshold_fails():
    r = screen(fundamentals=fund(interest_bearing_debt=300.0), denominators=MCAP, activities=CEMENT,
               methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "NON_COMPLIANT" and ratio(r, "debt")["result"] == "fail"


def test_near_threshold_is_questionable():
    r = screen(fundamentals=fund(interest_bearing_debt=280.0), denominators=MCAP, activities=CEMENT,
               methodology=AAOIFI, as_of=AS_OF)  # 28% is within 10% of 30%
    assert r["status"] == "QUESTIONABLE" and ratio(r, "debt")["result"] == "near"


def test_total_debt_used_as_conservative_proxy():
    r = screen(fundamentals=fund(interest_bearing_debt=None, total_debt=250.0), denominators=MCAP,
               activities=CEMENT, methodology=AAOIFI, as_of=AS_OF)
    d = ratio(r, "debt")
    assert d["value"] == 0.25 and "conservative" in d["numerator"]["note"]


def test_missing_input_never_passes():
    r = screen(fundamentals=fund(interest_bearing_securities=None), denominators=MCAP, activities=CEMENT,
               methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "INSUFFICIENT_DATA"
    assert ratio(r, "cash_securities")["result"] == "insufficient"
    none = screen(fundamentals=None, denominators={}, activities=CEMENT, methodology=AAOIFI, as_of=AS_OF)
    assert none["status"] == "INSUFFICIENT_DATA" and none["purification"] is None


def test_stale_fundamentals_block_compliant():
    r = screen(fundamentals=fund(period_end=date(2025, 12, 31)), denominators=MCAP, activities=CEMENT,
               methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "INSUFFICIENT_DATA" and not r["data"]["fresh"]


def test_prohibited_primary_business_fails_without_fundamentals():
    r = screen(fundamentals=None, denominators={}, activities=[{"tag": "alcohol", "primary": True}],
               methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "NON_COMPLIANT"


def test_secondary_activity_share_rules():
    base = dict(fundamentals=fund(), denominators=MCAP, methodology=AAOIFI, as_of=AS_OF)
    small = screen(activities=CEMENT + [{"tag": "alcohol", "revenue_share": 0.02}], **base)
    unknown = screen(activities=CEMENT + [{"tag": "alcohol"}], **base)
    large = screen(activities=CEMENT + [{"tag": "alcohol", "revenue_share": 0.05}], **base)
    assert small["status"] == "COMPLIANT"
    assert unknown["status"] == "QUESTIONABLE"
    assert large["status"] == "NON_COMPLIANT"


def test_islamic_bank_not_caught_by_conventional_exclusions():
    r = screen(fundamentals=fund(), denominators=MCAP, activities=[{"tag": "islamic_banking", "primary": True}],
               methodology=AAOIFI, as_of=AS_OF)
    assert r["business"]["result"] == "pass"


def test_no_activities_is_insufficient():
    r = screen(fundamentals=fund(), denominators=MCAP, activities=[], methodology=AAOIFI, as_of=AS_OF)
    assert r["status"] == "INSUFFICIENT_DATA"


def test_review_flag_and_external_disagreement():
    base = dict(fundamentals=fund(), denominators=MCAP, activities=CEMENT, methodology=AAOIFI, as_of=AS_OF)
    assert screen(review_note="Checking 2026 notes", **base)["status"] == "UNDER_REVIEW"
    ext = [{"source": "Index X", "status": "NON_COMPLIANT", "as_of": "2026-09-01"}]
    assert screen(external=ext, **base)["status"] == "QUESTIONABLE"


def test_total_assets_methodology_adds_receivables():
    den = {"total_assets": {"value": 2000.0, "method": "test"}}
    r = screen(fundamentals=fund(), denominators=den, activities=CEMENT, methodology=TOTAL_ASSETS, as_of=AS_OF)
    assert ratio(r, "debt")["value"] == 0.10 and ratio(r, "receivables")["value"] == 0.025
    assert r["status"] == "COMPLIANT"


def test_methodology_validation():
    good = validate_methodology(AAOIFI["thresholds"], "market_cap", ["alcohol"], 190)
    assert good == []
    bad = validate_methodology({"debt_to_denominator": 1.5, "magic": 0.1}, "vibes", ["crypto"], 5)
    assert len(bad) >= 5
