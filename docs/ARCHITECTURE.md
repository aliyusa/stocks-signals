# Halal Stock Signals: Architecture and Roadmap

Version 0.4 (Phase 4) · 01 Oct 2026

Guiding principle: **DATA → ANALYSIS → SIGNAL → EXPLANATION**. The platform never places trades. Every number it shows carries a source, a timestamp, a frequency and a status. When a value is missing, the platform says "Data unavailable" and does not substitute an estimate.

## Contents

1. [System architecture](#1-system-architecture)
2. [Database schema](#2-database-schema)
3. [Signal-generation methodology](#3-signal-generation-methodology)
4. [Shariah-screening methodology](#4-shariah-screening-methodology)
5. [Market-data sources](#5-market-data-sources)
6. [What is free and open-source](#6-what-is-free-and-open-source)
7. [Folder structure](#7-folder-structure)
8. [Roadmap](#8-roadmap)
9. [Major engineering decisions](#9-major-engineering-decisions)

---

## 1. System architecture

```
 Browser (React + TypeScript + Tailwind, Lightweight Charts)
      │  HTTPS, JSON; httpOnly auth cookie + CSRF header
      ▼
 FastAPI backend (Python 3.11)
  ├── api/        REST routers (auth, markets, stocks, scanner, signals, ...)
  ├── services/   business logic, one module per domain
  ├── engines/    pure, testable computation
  │     ├── indicators   (SMA, EMA, RSI, MACD, ATR, Bollinger, OBV, ...)
  │     ├── signals      (rule evaluation, weighted score, levels, R:R)
  │     ├── shariah      (business + ratio screens per methodology)
  │     ├── regime       (market-condition classifier)
  │     └── backtest     (walk-forward, no look-ahead)
  ├── providers/  data abstraction layer (see §5)
  └── workers/    APScheduler jobs: price refresh, screens, alerts
      │
      ├── PostgreSQL 16   system of record
      └── Redis 7         cache, rate-limit counters, job locks
```

**Request flow for a stock page:** the router calls `StockService`. `StockService` reads cached `PriceHistory` rows. If they are older than the provider's expected frequency, it asks the `ProviderRegistry` for a refresh. The indicator engine then computes on the stored bars, the signal engine turns those values into a signal, and the response carries a `DataPoint` envelope (value, source, as_of, frequency, status) for every field.

**Engines are pure functions** over pandas DataFrames. They never fetch data themselves, and so they can be unit-tested with fixed inputs and reused unchanged by the backtester. That reuse is what prevents the live logic and the backtest logic from drifting apart.

[Back to top](#contents)

## 2. Database schema

PostgreSQL with SQLAlchemy 2.0 ORM and Alembic migrations. All timestamps are stored in UTC (`timestamptz`) and displayed in WAT or the user's zone.

| Entity | Key columns | Notes |
|---|---|---|
| `users` | id, email (unique), password_hash, full_name, is_active, is_admin, timezone, created_at | Argon2 hashes |
| `markets` | id, code (NG, US, UK, GCC, MY, ID, CA, EU), name | Selector groups |
| `exchanges` | id, market_id, code (MIC, e.g. XNSA, XNAS), name, currency, timezone, open/close time | |
| `sectors` | id, name, parent_id | Optional hierarchy |
| `data_sources` | id, code, name, kind (price/fundamental/news/shariah), tier (free/paid), frequency, is_enabled, last_success_at, last_error | Drives status badges |
| `stocks` | id, ticker, exchange_id, name, sector_id, country, currency, isin, is_active, delisted_at | Unique (ticker, exchange_id); `delisted_at` reduces survivorship bias |
| `price_history` | stock_id, interval (1d, 1w, 1h, 15m), ts, open, high, low, close, adj_close, volume, source_id, ingested_at | PK (stock_id, interval, ts); index on (stock_id, interval, ts desc) |
| `fundamentals` | stock_id, period_end, period_type (Q/A/TTM), revenue, net_income, eps, total_debt, interest_bearing_debt, cash, interest_bearing_securities, receivables, total_assets, interest_income, non_permissible_income, market_cap, shares_out, dividend_ps, source_id, reported_at, is_estimate | `is_estimate` separates verified from estimated |
| `shariah_methodologies` | id, code, name, description, thresholds (JSONB), prohibited_activities (JSONB), denominator (market_cap / total_assets / 36m avg market cap), owner_user_id (null = built-in) | Configurable |
| `shariah_screens` | id, stock_id, methodology_id, status, business_result (JSONB), ratio_results (JSONB), data_as_of, computed_at, reviewer_note | Full audit trail of "why" |
| `technical_indicators` | stock_id, interval, ts, name, params (JSONB), value (JSONB) | Cache only; always recomputable |
| `strategies` | id, user_id, name, description, rules (JSONB), weights (JSONB), level_method, is_builtin | |
| `signals` | id, stock_id, strategy_id, interval, ts, signal_type (BUY_SETUP, SELL_EXIT, HOLD, WAIT, AVOID, WATCHLIST), score, score_breakdown (JSONB), reasons (JSONB), warnings (JSONB), entry_low, entry_high, stop, target1..3, rr, data_as_of | Immutable once written |
| `watchlists` / `watchlist_stocks` | user_id, name / watchlist_id, stock_id, added_at, note | |
| `portfolios` / `portfolio_positions` | user_id, name, base_currency / portfolio_id, stock_id, quantity, avg_entry, stop, target, opened_at | Manual entry only |
| `alerts` | id, user_id, stock_id (nullable), condition (JSONB), channels (JSONB), is_active, last_triggered_at, cooldown_minutes | |
| `alert_events` | alert_id, triggered_at, payload (JSONB), delivered (JSONB) | |
| `backtests` | id, user_id, strategy_id, universe (JSONB), start, end, costs_bps, slippage_bps, metrics (JSONB), trades (JSONB), status, created_at | |
| `news` | id, stock_id, source_id, published_at, title, url, summary | |
| `audit_logs` | id, user_id, action, entity, entity_id, ip, user_agent, details (JSONB), created_at | Security trail |

[Back to top](#contents)

## 3. Signal-generation methodology

**No black-box prediction.** A signal is a deterministic function of stored bars and fundamentals.

### 3.1 Indicators

The indicators are implemented in plain Python inside `engines/indicators.py`. No pandas, NumPy or TA-Lib: the formulas stay readable, nothing native needs installing on Windows, and a few thousand bars compute in milliseconds. RSI is checked against the published StockCharts worked example and, where pandas is installed, against a pandas reference.

- SMA 20, 50, 100, 200 and EMA 9, 21, 50, 200
- RSI (Wilder), MACD 12/26/9, Stochastic 14/3, ROC
- Volume SMA 20, volume spike ratio, OBV
- ATR 14 (Wilder), Bollinger 20/2
- Swing highs and lows (fractal, k = 3), support and resistance clusters, breakout and breakdown detection, gaps
- ADX 14 with +DI and −DI; weekly trend from resampled weekly bars (SMA 10 and 40 weeks)
- Not yet: VWAP (needs intraday data), Fibonacci and pivot points

TA-Lib is not required; see §9. Every function documents its warm-up length. Output during warm-up is `None`, and any rule that depends on it evaluates to "insufficient data".

### 3.2 Scoring

Each category has sub-rules. A category scores the fraction of its applicable rules that pass, multiplied by the category weight. The default weights, which the user can change, are:

| Category | Weight | Example rules |
|---|---|---|
| Trend | 20 | close > SMA50; SMA50 > SMA200; close > SMA200; EMA21 rising over 5 sessions |
| Momentum | 20 | 50 ≤ RSI ≤ 70; MACD > signal; ROC(10) > 0 |
| Volume | 15 | volume ≥ 1.2 × SMA20(volume); OBV rising over 20 bars |
| Price action | 20 | higher high and higher low; break of resistance; no gap-down in 5 bars |
| Risk | 10 | ATR% below the 1-year median; R:R ≥ 2 |
| Market | 10 | index regime is Trending Up or Sideways |
| Liquidity | 5 | 20-day median traded value ≥ threshold; zero-range bar share < 20% |

Rules whose inputs are unavailable are excluded, and the score is renormalised over the rules that remain. The response always shows `coverage` (for example, "71 of 100 weight points evaluable"). A score computed from coverage below 60% is capped at WATCHLIST. The score is the weighted share of passed rules; it is not a probability.

### 3.3 Classification

The classification is evaluated in order, and the first match wins:

1. **AVOID**: Shariah status is NON-COMPLIANT, or the liquidity category fails.
2. **SELL / EXIT**: an open position meets a stop, breakdown, trend-reversal, overbought-divergence or R:R-deterioration condition. The reason code is always shown.
3. **BUY SETUP**: score ≥ 70, the trend and price-action categories each ≥ 60%, R:R ≥ the user minimum, and no blocking warning.
4. **WATCHLIST**: score from 55 to 69, or BUY conditions met while confirmation (breakout close, volume) is pending.
5. **HOLD**: a position is open and no exit condition is met.
6. **WAIT**: everything else.

The label says "setup score", never probability. Warnings (earnings within 10 days, stale data, high regime volatility) are listed separately and never silently change the score.

### 3.4 Levels

Phase 3 implements the structure + ATR method below. Other methods (percentage, volatility-adjusted) arrive with the strategy builder in Phase 6. Each level is returned with a plain-English note on how it was derived.

- **Entry zone:** breakout level to breakout + 0.5 × ATR, or pullback support to support + 0.5 × ATR; with no nearby structure, close ± 0.25 × ATR.
- **Stop:** the nearest structural low minus 0.5 × ATR (swing method), or entry − k × ATR.
- **Targets:** T1 is the next resistance cluster, T2 the measured move, and T3 the next swing high. **A target is omitted when no structure supports it.**
- **R:R** = (target − entry mid) ÷ (entry mid − stop).

### 3.5 Backtesting guarantees

- The signal on bar *t* uses data up to and including bar *t*'s close only. The fill happens at bar *t+1*'s open, plus slippage.
- Costs (commission in basis points, plus NGX statutory fees as a configurable preset) are charged on both sides.
- The universe is point-in-time: stocks with `delisted_at` inside the window are kept.
- Point-in-time Shariah status uses the fundamentals `reported_at` date, not `period_end`.
- Reported metrics: trades, wins, losses, win rate, average gain and loss, profit factor, maximum drawdown, average R, total and annualised return, and exposure.

[Back to top](#contents)

## 4. Shariah-screening methodology

The platform does not present any single standard as universal. A **methodology** is data: thresholds, denominators and prohibited-activity lists. Three are built in and users can clone and edit them.

| Methodology | Debt test | Cash / securities test | Receivables test | Non-permissible income |
|---|---|---|---|---|
| AAOIFI-based (default) | Interest-bearing debt ÷ market cap < 30% | Interest-bearing deposits and securities ÷ market cap < 30% | Not used | < 5% of revenue |
| Total-assets based (configurable preset) | Debt ÷ total assets < 33% | Cash + interest securities ÷ total assets < 33% | Receivables ÷ total assets < 49% | < 5% |
| Custom | User thresholds and denominators | | | |

The second preset is labelled as a total-assets preset. It does not claim to replicate any index provider's proprietary rules.

**Business-activity screen.** Each stock carries activity tags (manual or provider-supplied) with revenue shares where known. The prohibited list covers conventional banking and lending, conventional insurance, alcohol, gambling, pork, adult entertainment, tobacco, and weapons or defence. Each item is configurable per methodology. Islamic banks and takaful insurers are tagged separately and are not caught by the conventional finance exclusions.

**Status logic** (implemented in `engines/shariah.py`; the first match wins):

1. **NON-COMPLIANT**: the primary business is on the excluded list, a secondary excluded activity is at or above the income limit, or any ratio is at or above its limit.
2. **UNDER REVIEW**: a reviewer has set a review note on the stock.
3. **INSUFFICIENT DATA**: a required input is missing, no activity is marked primary, or the fundamentals are older than the methodology's limit (default 190 days from the period end). The platform never assumes a pass.
4. **QUESTIONABLE**: a ratio passes but is within the questionable margin of its limit (default 10%, so 27% or more against a 30% limit), a secondary excluded activity has an unknown revenue share, or a recorded external screen says NON-COMPLIANT.
5. **COMPLIANT**: every test passes on fresh data.

A stock with nothing entered shows **NOT SCREENED**, which is never treated as compliant.

**Ratio inputs.** Debt uses interest-bearing debt; if that is blank, total debt is used as a conservative stand-in and the "Why?" panel says so. The cash test counts all cash plus interest-bearing securities, again conservatively. Non-permissible income is interest income plus other non-permissible income, divided by revenue for the same period. Market capitalisation is the reported value if entered, otherwise the last stored close on or before the screening date × shares outstanding. The 36-month average uses 36 month-end closes × the current share count and is INSUFFICIENT DATA until 36 months of prices are stored.

**Point in time.** A fundamentals entry is used only from its published date (or its entry date when the published date is blank), and the latest period end available on the screening date wins.

**Fundamentals source.** The EODHD free plan has no fundamentals, so Phase 4 adds manual entry from published financial statements. Each entry must carry a source reference (report and page, or a link), records who entered it, and can be marked as an estimate. Every change to activities, fundamentals, reviews, external screens and methodologies is written to the audit log.

**Methodology editor.** Built-in methodologies are read-only. A user can copy one, change its limits, denominator, excluded activities and freshness limit, and make it the default. The default drives the status shown on stock pages, the scanner, Signals and the dashboard, and a NON-COMPLIANT result turns the technical signal into AVOID.

**Record keeping.** Each screen is stored with its full engine output. A new record is written only when the inputs or result change.

Every result shows the inputs, each test's value against its limit, the data date and the source. The UI shows this "Why?" breakdown, together with the disclaimer that methodologies differ and that users should verify compliance with a qualified Shariah scholar or a recognised screening provider. Purification per share is dividend per share × the non-permissible share of revenue for the same period; purification of capital gains is not calculated.

[Back to top](#contents)

## 5. Market-data sources

Researched 28 Sep 2026. Prices and limits change, so re-check them before subscribing.

| Source | Tier | Coverage | Data type | Limits and caveats |
|---|---|---|---|---|
| **NGX Market Data API** (official) | Paid: NGN 100,000 to NGN 1,000,000 per year (local) or USD 1,000 to USD 12,500 (international) | NGX only | Real-time, 30-minute delayed, EOD, 10-year history, dividends, corporate actions | Formal subscription; the only authoritative real-time NGX feed |
| **EODHD** | Free: 20 calls per day, EOD, 1 year of history. EOD All World: USD 19.99 per month. All-in-one: USD 99.99 per month | 150,000+ tickers including NGX (exchange code XNSA) | EOD; intraday, 15-minute delayed live data and fundamentals on higher plans | Best single choice for NGX plus global EOD. NGX fundamentals depth is unverified |
| **Financial Modeling Prep** | Free: 250 calls per day, US only, EOD. Starter USD 19 per month; Premium USD 49 per month (adds UK and Canada); Ultimate USD 99 per month (global) | US, then UK, Canada, global | EOD, intraday, fundamentals | Good for US fundamentals |
| **Twelve Data** | Free: 800 credits per day, 8 per minute, US stocks, forex, crypto | US on free plan; 20 to 85 markets on paid plans | Real-time US (free), international (paid) | Useful for intraday US |
| **Alpha Vantage** | Free: 25 requests per day. Premium USD 49.99 to USD 249.99 per month | US mainly | EOD and intraday | Free tier too small for scanning |
| **Mansa API** | Free: 100 requests per day (quotes). History requires Pro | NGX | Current quote | Third-party; not verified beyond an open-source integration |
| **CSV import** (built in) | Free | Any | Whatever the file holds, usually EOD | Lets you load NGX daily price lists or broker exports honestly, tagged with their source |

**Status badges** are derived, never assumed:

- **LIVE**: the provider is a real-time entitlement and the last tick is under 60 seconds old.
- **DELAYED**: the entitlement is delayed and the data is within delay plus tolerance.
- **END-OF-DAY**: an EOD source whose last bar is the latest completed session.
- **STALE**: the data is older than expected for its frequency.
- **UNAVAILABLE**: no provider, a failed fetch, or no key configured.

**NGX-specific data quality.** Many NGX bars print identical open, high, low and close for weeks, because the official close methodology and thin trading keep the price unchanged. The engine measures the "zero-range bar share" and flags indicators as unreliable when it exceeds 20%. This measurement feeds the liquidity rule.

### Provider abstraction

```
MarketDataProvider (ABC)
  get_bars(ticker, exchange, interval, start, end) -> Bars
  get_quote(ticker, exchange) -> Quote
  search(query) -> list[Instrument]
  capabilities -> ProviderCapabilities(markets, intervals, realtime, delay_minutes)
├── EODHDProvider         (NGX + global)
├── FMPProvider           (US, UK, CA)
├── TwelveDataProvider    (US intraday)
├── NGXOfficialProvider   (interface ready; needs licence)
├── CSVImportProvider
└── UnavailableProvider   (returns status=UNAVAILABLE, never data)
FundamentalDataProvider  → EODHDFundamentals, FMPFundamentals
NewsProvider             → EODHDNews, FMPNews
```

`ProviderRegistry` chooses a provider per exchange from configuration, for example `NG=eodhd,csv` and `US=fmp,eodhd`. Adding an exchange means writing one config line and, only if no existing provider covers it, one class.

[Back to top](#contents)

## 6. What is free and open-source

Everything in the software stack is free and open-source: React, TypeScript, Tailwind, TradingView Lightweight Charts (Apache-2.0), FastAPI, SQLAlchemy, Alembic, pandas, NumPy, SciPy, PostgreSQL, Redis, APScheduler and Docker Compose.

**Free data** is enough to run the platform with US end-of-day data (FMP free plus Twelve Data free) and NGX via CSV import or the EODHD free tier. The EODHD free tier's 20 calls a day is enough for a watchlist of about 15 stocks, not for a market-wide scan.

**Paid data** is realistically needed for:

- a full NGX scan every day (EODHD USD 19.99 per month is the cheapest option found);
- real-time or delayed NGX (the official NGX API);
- international fundamentals for Shariah ratios (EODHD Fundamentals or FMP Premium).

The AI assistant (Phase 7) needs an LLM API key. It is optional and can be switched off.

[Back to top](#contents)

## 7. Folder structure

```
halal-stock-signals/
├── docker-compose.yml
├── .env.example
├── README.md
├── docs/ARCHITECTURE.md
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic.ini
│   ├── alembic/versions/
│   ├── app/
│   │   ├── main.py
│   │   ├── core/        config, security, db, rate limit, csrf, logging
│   │   ├── models/      SQLAlchemy entities
│   │   ├── schemas/     Pydantic request/response models, DataPoint envelope
│   │   ├── api/         routers
│   │   ├── services/
│   │   ├── engines/     indicators, signals, shariah, regime, backtest
│   │   ├── providers/   base, registry, eodhd, fmp, twelvedata, ngx, csv, unavailable
│   │   ├── workers/     scheduler jobs
│   │   └── seed.py      markets, exchanges, methodologies, data sources (no prices)
│   └── tests/
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── vite.config.ts
    └── src/
        ├── main.tsx, App.tsx
        ├── lib/         api client, auth context, formatters
        ├── components/  layout, badges (DataStatus, Shariah, Signal), cards, tables
        └── pages/       Dashboard, Markets, Scanner, Signals, Watchlist, Portfolio,
                         Backtesting, Strategies, Alerts, Shariah, RiskCalculator, Settings, auth
```

[Back to top](#contents)

## 8. Roadmap

| Phase | Scope | Exit test |
|---|---|---|
| **1** (done) | Architecture, full schema, FastAPI, auth (Argon2, JWT cookie, CSRF, rate limit, audit log), React shell with all navigation, dashboard reading real system status, Docker Compose | Register, log in and see the dashboard. Every market card shows UNAVAILABLE until a provider is configured |
| **2** (done: EODHD) | Provider layer (EODHD done; FMP, Twelve Data, CSV pending), search, stock page, candlestick chart | Load DANGCEM from CSV or EODHD and MSFT from FMP, each with correct badges |
| **3** (done) | Indicator engine, signal engine, market regime, scanner, Signals page, editable score weights, chart overlays and RSI/MACD panes | Unit tests against reference values; scanner returns explainable matches |
| **4** (done) | Shariah engine, methodology editor, "Why?" panel, manual fundamentals entry, Shariah screener | Each status is reachable in tests; missing data yields INSUFFICIENT DATA |
| 5 | Watchlists, alerts (browser push and email), portfolio | An alert fires once per cooldown |
| 6 | Risk calculator, backtester, strategy builder | A no-look-ahead test (shifted-future canary) passes |
| 7 | AI assistant restricted to system data, with citations | Refuses to answer beyond the stored data |
| 8 | Test coverage, security review, performance, deployment guide | CI green; OWASP checklist |

[Back to top](#contents)

## 9. Major engineering decisions

- **Own indicator code instead of TA-Lib.** TA-Lib needs a C library that is awkward to install on Windows and in slim Docker images. Implementing roughly 20 indicators in pandas keeps every formula visible, which the transparency requirement demands, and the code is tested against published reference values. Using `pandas-ta` was considered, but its maintenance status is uncertain.
- **Argon2 password hashing** (via `pwdlib`), rather than bcrypt's 72-byte limit.
- **JWT in an httpOnly, SameSite=Lax cookie plus a double-submit CSRF token.** Keeping tokens away from JavaScript avoids exposing them to XSS; the CSRF header covers the cookie risk.
- **APScheduler instead of Celery** for Phases 1 to 5. There is one fewer service to run on a laptop, and the job functions are plain Python, so a later move to Celery is mechanical.
- **Redis is optional in development.** If it is absent, rate limiting falls back to in-memory storage and caching is disabled.
- **SQLite for tests only.** Production and development use PostgreSQL through Docker.
- **No seeded prices.** The seed script creates markets, exchanges, methodologies and data-source rows only, so the platform starts honest.

---

*This platform provides market research, technical analysis and Shariah-screening information for educational and decision-support purposes. Signals are not guarantees of future performance and are not personalised investment advice. Users are responsible for their own investment decisions. Shariah screening methodologies differ; verify religious compliance with an appropriately qualified authority.*

**Sources for §5:** [NGX Market Data API](https://marketdataapiv3.ngxgroup.com/portal/getstarted/index), [EODHD pricing](https://eodhd.com/pricing), [EODHD XNSA](https://eodhd.com/exchange/XNSA), [FMP pricing](https://site.financialmodelingprep.com/pricing-plans), [Twelve Data pricing](https://twelvedata.com/pricing), [Alpha Vantage premium](https://www.alphavantage.co/premium/), [Mansa integration PR](https://github.com/we-promise/sure/pull/3629).
