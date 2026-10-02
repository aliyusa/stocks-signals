"""Application settings, loaded from environment variables (never hard-coded secrets)."""

from functools import lru_cache

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Reads the project-root .env when started from backend/, and a local .env if present.
    model_config = SettingsConfigDict(env_file=("../.env", ".env"), env_file_encoding="utf-8", extra="ignore")

    app_name: str = "Halal Stock Signals"
    environment: str = Field(default="development", pattern="^(development|test|production)$")

    database_url: str = "postgresql+psycopg://hss:hss@localhost:5432/hss"
    redis_url: str | None = None  # optional in development

    # Security
    secret_key: str = Field(default="change-me-in-env", min_length=16)
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    cookie_secure: bool = False  # set True behind HTTPS
    cors_origins: list[str] = ["http://localhost:5173"]
    # Hosted sites: only these emails may register (empty list = open registration, fine on a laptop).
    allowed_emails: list[str] = []
    login_rate_limit: str = "10/minute"
    default_rate_limit: str = "120/minute"

    # Data providers: keys stay server-side only. Empty means provider disabled.
    eodhd_api_key: str | None = None
    fmp_api_key: str | None = None
    twelvedata_api_key: str | None = None
    ngx_api_key: str | None = None

    # EODHD: free plan = 20 calls/day. Every request (even a 404) costs one call.
    eodhd_base_url: str = "https://eodhd.com/api"
    eodhd_daily_call_limit: int = 20
    eodhd_timeout_seconds: float = 20.0
    history_years: int = 5  # depth requested on first load (free plan returns ~1 year)
    # Minimum gap between automatic fetches of one stock. Stops an illiquid or delisted stock whose
    # latest bar never "catches up" from draining the daily budget. Manual refresh ignores it.
    auto_refresh_cooldown_hours: float = 6.0

    # Index symbols in EODHD notation. NGX ASI is left blank until verified with
    # your own key (use the app's provider search with type=index).
    index_symbols: dict[str, str] = {"NGXASI": "", "SPX": "GSPC.INDX", "IXIC": "IXIC.INDX"}

    # Provider routing per market code, first available wins, e.g. "eodhd,csv"
    provider_routes: dict[str, str] = {
        "NG": "ngx,eodhd,csv",
        "US": "fmp,twelvedata,eodhd,csv",
        "UK": "eodhd,fmp,csv",
        "GCC": "eodhd,csv",
        "MY": "eodhd,csv",
        "ID": "eodhd,csv",
        "CA": "eodhd,fmp,csv",
        "EU": "eodhd,csv",
        "GL": "eodhd",
    }

    display_timezone: str = "Africa/Lagos"

    # Email alerts (optional): any SMTP service, e.g. Gmail with an app password. Empty host = email off.
    smtp_host: str | None = None
    smtp_port: int = 587
    smtp_user: str | None = None
    smtp_password: str | None = None
    smtp_from: str | None = None
    smtp_starttls: bool = True

    # Daily job (Vercel Cron sends "Authorization: Bearer <CRON_SECRET>"). Empty = the job endpoint is off.
    cron_secret: str | None = None
    cron_refresh_max: int = 10  # stocks refreshed per run at most
    cron_call_reserve: int = 4  # EODHD calls always left for your own browsing

    # Hosted mode: the backend also serves the built React app from this folder (one URL, same origin).
    static_dir: str | None = None

    @field_validator("secret_key")
    @classmethod
    def _no_default_secret_in_prod(cls, v: str, info):  # noqa: ANN001
        env = info.data.get("environment")
        if env == "production" and v == "change-me-in-env":
            raise ValueError("SECRET_KEY must be set in production")
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
