# Hosting on Vercel and Supabase

Version 1.2 · 02 Oct 2026

With this setup nothing runs on your laptop. You open one web address from any device.

| Part | Service | What it does |
|---|---|---|
| Database | Supabase (free), project `stock-signals`, region eu-west-1 (Ireland) | PostgreSQL: accounts, stocks, price bars, signals |
| App | Vercel (Hobby), function region `dub1` (Dublin, next to the database) | One Python function: the FastAPI backend and the built React site on the same address |
| Code | GitHub `aliyusa/stocks-signals` | Vercel builds from it; every push to `main` redeploys |

How it fits together:

- `server.py` (project root) is the Vercel entrypoint. It adds `backend/` to the import path, sets hosted defaults, runs database migrations and reference data on a cold start, then exposes the FastAPI `app`.
- `vercel.json` builds the React app (`frontend/dist`), includes it and the migrations in the function, sets a 60-second limit and pins the region to Dublin.
- Migrations take a PostgreSQL advisory lock inside one transaction, so two instances never migrate at once. This works through Supabase's transaction pooler.

Free-tier limits to know:

- A Supabase free project pauses after about a week without activity. Restore it from the dashboard; the data is kept ([Supabase docs](https://supabase.com/docs/guides/platform/free-project-pausing)).
- The first request after an idle period is slower while the function starts (cold start).

## Environment variables (Vercel → Project → Settings → Environment Variables)

| Name | Value | Secret |
|---|---|---|
| `DATABASE_URL` | Supabase **Transaction pooler** URI (port 6543), with your database password | Yes |
| `EODHD_API_KEY` | Your EODHD key | Yes |
| `SECRET_KEY` | A long random string (at least 32 characters). Signs login tokens | Yes |
| `ALLOWED_EMAILS` | `["aliyusa756@gmail.com"]`. Only these emails can register | No |
| `CRON_SECRET` | Optional. A long random string; turns on the weekday daily job (price refresh and alert checks) | Yes |
| `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, `SMTP_FROM` | Optional, for email alerts. Gmail: `smtp.gmail.com`, `587`, your address, a Google app password, your address | Password: yes |

`ENVIRONMENT=production`, `COOKIE_SECURE=true` and the static folder are set by `server.py`. Enter the three secrets yourself; never paste them into a chat.

To get `DATABASE_URL`: Supabase → project `stock-signals` → **Connect** → **Transaction pooler**. Replace `[YOUR-PASSWORD]` with the database password. If you do not know it, use **Project Settings → Database → Reset database password**, and avoid `@ : / # %` in it.

To make a `SECRET_KEY` on Windows (Command Prompt):

```bat
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

## Deploying

1. Push the code to GitHub (`git push` in the project folder).
2. Vercel → **Add New → Project** → import `aliyusa/stocks-signals`. Framework preset: **FastAPI** (detected). Leave Root Directory as the repository root.
3. Add the four environment variables above, then **Deploy**.
4. Open the address Vercel shows and register with the allowed email.

After changing an environment variable, redeploy (Deployments → ⋯ → Redeploy) for it to take effect.

## Optional: bring your laptop data across

Keeps your account, the NGX list and stored price bars, so no EODHD calls are spent fetching them again. Do it after the first deployment has opened once (which creates the tables) and before registering on the hosted site. Use the **Session pooler** URI (port 5432) for this one-off copy.

```bat
cd C:\Users\PC\Documents\Project\halal-stock-signals\backend
.venv\Scripts\python.exe -m pip install --only-binary=:all: "psycopg[binary]"
.venv\Scripts\python.exe -m app.copy_to_postgres "PASTE-THE-SESSION-POOLER-URI"
```

It refuses to run if the hosted database already has users or price bars.

## Day-to-day

- Open the Vercel address. Nothing to start.
- Code updates: commit and push to `main`; Vercel redeploys by itself.
- `start-windows.bat` still works offline with its own `dev.db`, separate from Supabase.

## Alternative: Render

`render.yaml` and the root `Dockerfile` deploy the same app as one always-on container on Render (New → Blueprint). Use the Supabase **Session pooler** URI there.

## Security notes

- Cookies are `Secure`, `httpOnly` and `SameSite=Lax`; HSTS and a content security policy are sent.
- Only emails in `ALLOWED_EMAILS` can register, so strangers cannot use up your 20 EODHD calls a day.
- The API documentation page is off in production. Secrets live only in Vercel's settings; `.env`, `dev.db` and logs are excluded from Git and from Vercel uploads.

[Back to top](#hosting-on-vercel-and-supabase)
