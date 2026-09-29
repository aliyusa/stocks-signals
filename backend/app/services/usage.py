"""Per-day call budget for metered providers (e.g. EODHD free plan: 20 calls/day)."""

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from app.models.entities import ProviderUsage
from app.providers.base import ProviderUnavailable


def today_utc():
    return datetime.now(UTC).date()


class CallBudget:
    def __init__(self, db: Session, source_code: str, daily_limit: int):
        self.db, self.source_code, self.daily_limit = db, source_code, daily_limit

    def used_today(self) -> int:
        row = self.db.get(ProviderUsage, (self.source_code, today_utc()))
        return row.calls if row else 0

    def __call__(self, endpoint: str) -> None:
        """Reserve one call or raise. Counted before the request, because failed requests are billed too."""
        day = today_utc()
        row = self.db.get(ProviderUsage, (self.source_code, day))
        if row is None:
            row = ProviderUsage(source_code=self.source_code, day=day, calls=0)
            self.db.add(row)
        if row.calls >= self.daily_limit:
            raise ProviderUnavailable(
                f"{self.source_code.upper()}: daily call budget reached ({self.daily_limit}/day). "
                "Showing stored data; it resets at 00:00 UTC (01:00 WAT)."
            )
        row.calls += 1
        row.last_endpoint = endpoint
        self.db.commit()


def usage_summary(db: Session, source_code: str, daily_limit: int) -> dict:
    used = CallBudget(db, source_code, daily_limit).used_today()
    return {"source": source_code, "day": today_utc().isoformat(), "used": used, "limit": daily_limit,
            "remaining": max(0, daily_limit - used)}
