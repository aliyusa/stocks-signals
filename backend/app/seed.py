"""Idempotent reference-data seed. Deliberately contains NO prices or fundamentals.

Run: python -m app.seed
"""

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.db import SessionLocal
from app.models.entities import DataSource, Exchange, Market, ShariahMethodology, SourceKind

MARKETS = [
    ("NG", "Nigeria"), ("US", "United States"), ("UK", "United Kingdom"), ("GCC", "Gulf (GCC)"),
    ("MY", "Malaysia"), ("ID", "Indonesia"), ("CA", "Canada"), ("EU", "Europe"), ("GL", "Global indices"),
]

# (market, MIC, name, currency, tz, open, close)
EXCHANGES = [
    ("NG", "XNSA", "Nigerian Exchange (NGX)", "NGN", "Africa/Lagos", "10:00", "14:30"),
    ("US", "XNYS", "New York Stock Exchange", "USD", "America/New_York", "09:30", "16:00"),
    ("US", "XNAS", "NASDAQ", "USD", "America/New_York", "09:30", "16:00"),
    ("US", "XASE", "NYSE American (AMEX)", "USD", "America/New_York", "09:30", "16:00"),
    ("UK", "XLON", "London Stock Exchange", "GBP", "Europe/London", "08:00", "16:30"),
    ("CA", "XTSE", "Toronto Stock Exchange", "CAD", "America/Toronto", "09:30", "16:00"),
    ("GCC", "XSAU", "Saudi Exchange (Tadawul)", "SAR", "Asia/Riyadh", "10:00", "15:00"),
    ("GCC", "XDFM", "Dubai Financial Market", "AED", "Asia/Dubai", "10:00", "15:00"),
    ("MY", "XKLS", "Bursa Malaysia", "MYR", "Asia/Kuala_Lumpur", "09:00", "17:00"),
    ("ID", "XIDX", "Indonesia Stock Exchange", "IDR", "Asia/Jakarta", "09:00", "16:00"),
    ("EU", "XETR", "Deutsche Börse Xetra", "EUR", "Europe/Berlin", "09:00", "17:30"),
    ("GL", "INDX", "Market indices", "XXX", "UTC", None, None),
]

# code, name, kind, tier, frequency, delay, website, notes, settings key attribute
SOURCES = [
    ("ngx", "NGX Market Data API", SourceKind.PRICE, "paid", "realtime", 0,
     "https://marketdataapiv3.ngxgroup.com/portal",
     "Official. Annual subscription NGN 100,000 to 1,000,000 (local). Real-time, 30-min delayed, EOD.", "ngx_api_key"),
    ("eodhd", "EODHD", SourceKind.PRICE, "freemium", "eod", None, "https://eodhd.com/pricing",
     "Free: 20 calls/day, 1 year EOD. Paid from USD 19.99/month. Covers NGX as XNSA.", "eodhd_api_key"),
    ("fmp", "Financial Modeling Prep", SourceKind.PRICE, "freemium", "eod", None,
     "https://site.financialmodelingprep.com/pricing-plans", "Free: 250 calls/day, US EOD only.", "fmp_api_key"),
    ("twelvedata", "Twelve Data", SourceKind.PRICE, "freemium", "realtime", 0, "https://twelvedata.com/pricing",
     "Free: 800 credits/day, 8/min, US stocks.", "twelvedata_api_key"),
    ("csv", "CSV import", SourceKind.PRICE, "manual", "eod", None, None,
     "User-supplied files; each import records its origin.", None),
    ("eodhd_fund", "EODHD Fundamentals", SourceKind.FUNDAMENTAL, "paid", "quarterly", None,
     "https://eodhd.com/pricing", "Fundamentals feed from USD 59.99/month.", "eodhd_api_key"),
    ("fmp_fund", "FMP Fundamentals", SourceKind.FUNDAMENTAL, "freemium", "quarterly", None,
     "https://site.financialmodelingprep.com/pricing-plans", "Limited on free plan.", "fmp_api_key"),
    ("manual_shariah", "Manual Shariah review", SourceKind.SHARIAH, "manual", "manual", None, None,
     "Reviewer-entered activity tags and notes.", None),
]

AAOIFI_PROHIBITED = [
    "conventional_banking", "conventional_lending", "conventional_insurance", "alcohol", "gambling", "pork",
    "adult_entertainment", "tobacco", "weapons_defence", "impermissible_entertainment",
]

METHODOLOGIES = [
    {
        "code": "aaoifi_based",
        "name": "AAOIFI-based (default)",
        "description": "Ratios per AAOIFI Shariah Standard 21 as commonly applied: interest-bearing debt and "
                       "interest-bearing deposits/securities each below 30% of market capitalisation; "
                       "non-permissible income below 5% of revenue. Implementation of the standard's intent, "
                       "not an AAOIFI certification.",
        "thresholds": {"debt_to_denominator": 0.30, "cash_securities_to_denominator": 0.30,
                       "non_permissible_income_to_revenue": 0.05, "questionable_margin": 0.10},
        "denominator": "market_cap",
        "prohibited": AAOIFI_PROHIBITED,
    },
    {
        "code": "total_assets_33",
        "name": "Total-assets based (33%)",
        "description": "Configurable preset using total assets as the denominator: debt and cash plus "
                       "interest-bearing securities each below 33%, receivables below 49%, non-permissible "
                       "income below 5%. Not a replica of any index provider's proprietary rules.",
        "thresholds": {"debt_to_denominator": 0.33, "cash_securities_to_denominator": 0.33,
                       "receivables_to_denominator": 0.49, "non_permissible_income_to_revenue": 0.05,
                       "questionable_margin": 0.10},
        "denominator": "total_assets",
        "prohibited": AAOIFI_PROHIBITED,
    },
]


def seed(db: Session) -> None:
    settings = get_settings()
    markets = {m.code: m for m in db.scalars(select(Market)).all()}
    for code, name in MARKETS:
        if code not in markets:
            markets[code] = Market(code=code, name=name)
            db.add(markets[code])
    db.flush()

    existing_ex = {e.code for e in db.scalars(select(Exchange)).all()}
    for mkt, mic, name, cur, tz, o, c in EXCHANGES:
        if mic not in existing_ex:
            db.add(Exchange(market_id=markets[mkt].id, code=mic, name=name, currency=cur, timezone=tz,
                            open_time=o, close_time=c))

    existing_src = {s.code: s for s in db.scalars(select(DataSource)).all()}
    for code, name, kind, tier, freq, delay, web, notes, key_attr in SOURCES:
        src = existing_src.get(code) or DataSource(code=code)
        src.name, src.kind, src.tier, src.frequency, src.delay_minutes = name, kind, tier, freq, delay
        src.website, src.notes = web, notes
        # Enabled only reflects configuration; status stays UNAVAILABLE until a successful fetch.
        src.is_enabled = bool(getattr(settings, key_attr)) if key_attr else code == "csv"
        db.add(src)

    existing_m = {m.code for m in db.scalars(select(ShariahMethodology)).all()}
    for m in METHODOLOGIES:
        if m["code"] not in existing_m:
            db.add(ShariahMethodology(code=m["code"], name=m["name"], description=m["description"],
                                      thresholds=m["thresholds"], prohibited_activities=m["prohibited"],
                                      denominator=m["denominator"], is_builtin=True))
    db.commit()


if __name__ == "__main__":
    with SessionLocal() as session:
        seed(session)
    print("Reference data seeded (no market data).")
