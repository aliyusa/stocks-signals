# Halal Stock Signals

Shariah-compliant global stock screening and trading-signal research platform. This is a **decision-support tool**: it never places trades, and every value it shows carries a source, timestamp and data status.

Status: **Phase 3 of 8 complete** (Phase 1: architecture, database, authentication, dashboard; Phase 2: EODHD market data, search, Markets page, stock pages with candlestick charts; Phase 3: indicators, explainable setup score, signals, scanner). See [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) for the design, methodology and roadmap.

## Hosting online (no start-up on your laptop)

See [docs/DEPLOY.md](docs/DEPLOY.md): Supabase for the database and Vercel for the app (`server.py`, `vercel.json`), one web address. A Render alternative (`render.yaml`, `Dockerfile`) is included.

## Run with Docker (recommended)

Requires Docker Desktop.

```powershell
copy .env.example .env      # then edit SECRET_KEY and POSTGRES_PASSWORD
docker compose up --build
```

Open http://localhost:8080 and create an account. The backend runs its migrations and seeds reference data on start-up. No prices are seeded.

## Run without Docker (Windows, quick start)

This path uses SQLite and is for development only.

```powershell
# Backend (Python 3.11+)
cd backend
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements-dev.txt
$env:DATABASE_URL="sqlite:///./dev.db"
$env:SECRET_KEY="any-long-random-string-for-dev"
python -m app.dev_init
uvicorn app.main:app --reload --port 8000

# Frontend (Node 20+), in a second terminal
cd frontend
npm install
npm run dev
```

Open http://localhost:5173. The API documentation is at http://localhost:8000/api/docs.

## Tests

```powershell
cd backend
pytest -q          # 54 tests: auth, CSRF, audit, EODHD client (mocked), call budget, indicators vs reference values, signals, no look-ahead, scanner
ruff check app tests
cd ..\frontend
npm run build      # type-check and production build
```

## Connecting EODHD (Phase 2)

1. Register at https://eodhd.com and copy your API token.
2. Put it in `.env` as `EODHD_API_KEY=...` (never in the frontend, never in chat or email) and restart the backend.
3. In the app: **Markets → Nigeria → Import NGX list (1 call)** to load every NGX ticker, or use the search box and press **Search EODHD (1 call)**.
4. Open a stock. The first visit downloads its daily history (1 call); later visits reuse stored bars until a new session is due.

How the free 20-calls-a-day budget is protected:

- Local search is free; only the explicit "Search EODHD" button spends a call.
- A stock is fetched only when its stored history is behind the expected session, and at most once every 6 hours automatically (`AUTO_REFRESH_COOLDOWN_HOURS`).
- Calls are counted before each request (EODHD bills 404s too). At the limit, the app shows stored data and says the budget is spent; it resets at 01:00 WAT.
- The S&P 500 and NASDAQ cards use 1 call each per day. The NGX All-Share card stays UNAVAILABLE until you set its EODHD symbol in `INDEX_SYMBOLS`, because that code has not been verified.

Status badges: **END-OF-DAY** means the latest expected close is stored. **STALE** means it is behind; one session behind is flagged as a possible public holiday (holidays are not modelled yet). **UNAVAILABLE** means nothing is stored. On NGX stocks, the Data quality panel warns when many bars have high = low, which makes momentum indicators unreliable.

## Signals and scanner (Phase 3)

- **Stock page:** the signal (POTENTIAL BUY SETUP, WATCHLIST, WAIT or AVOID), the setup score out of 100 with its coverage, a plain-English summary, entry zone, stop and targets with how each was derived, every rule with pass, fail or not evaluated, warnings, daily and weekly trend, market regime and an indicator snapshot. The chart can show SMA 20/50/200, EMA 21, Bollinger bands, the levels, and RSI and MACD panes.
- **Stock Scanner:** filters on stored bars only, so it spends no EODHD calls. Open or refresh a stock first to give it history.
- **Signals:** the latest stored signal per stock.
- **Settings → Setup score weights:** change the category weights; signals recompute on the next view or scan.
- The market rule uses the S&P 500 for US stocks. NGX stocks show the market regime as unavailable until an NGX index symbol is set in `INDEX_SYMBOLS`.
- SELL / EXIT and HOLD need an open position, so they arrive with the portfolio in Phase 5. Shariah status stays NOT SCREENED until Phase 4.

## Data providers

Add keys to `.env` to enable a provider. Keys stay on the server and are never sent to the browser. Until a provider is connected and has fetched successfully, the UI shows **UNAVAILABLE** rather than any estimate. EODHD is implemented; FMP, Twelve Data, the official NGX API and CSV import are interface stubs that report "not configured". See §5 of the architecture document for free and paid options and their limits.

## Security

- Argon2id password hashing, a password policy, and account lockout after 5 failed logins
- JWT access and refresh tokens in httpOnly, SameSite=Lax cookies; "log out everywhere" through token versioning
- Double-submit CSRF protection on every cookie-authenticated write
- Rate limiting (Redis-backed in Docker), security headers, and a content security policy on the frontend
- An audit log for authentication and provider-call events; generic error responses that never leak internals
- The EODHD key is used only server-side; it is never returned by the API or written to error messages, logs or the audit trail (covered by a test)

## Disclaimer

This platform provides market research, technical analysis and Shariah-screening information for educational and decision-support purposes. Signals are not guarantees of future performance and are not personalised investment advice. Users are responsible for their own investment decisions. Shariah screening methodologies differ; verify religious compliance with an appropriately qualified authority.
