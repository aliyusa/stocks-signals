"""Which end-of-day bar *should* exist now, per exchange.

Weekends are known non-sessions. Public holidays are not modelled yet, so a bar that is
exactly one session behind is reported as STALE with a "possible holiday" note, never hidden.
"""

from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

# EOD vendors publish some time after the close. Conservative buffer before we expect today's bar.
PUBLISH_BUFFER = timedelta(hours=3)


def previous_weekday(d: date) -> date:
    d -= timedelta(days=1)
    while d.weekday() >= 5:
        d -= timedelta(days=1)
    return d


def expected_last_session(now_utc: datetime, tz: str, close_time: str | None) -> date:
    local = now_utc.astimezone(ZoneInfo(tz or "UTC"))
    today = local.date()
    if today.weekday() >= 5:
        return previous_weekday(today + timedelta(days=1)) if today.weekday() == 6 else previous_weekday(today)
    hh, mm = (int(x) for x in (close_time or "16:00").split(":"))
    publish_at = datetime.combine(today, time(hh, mm), tzinfo=local.tzinfo) + PUBLISH_BUFFER
    return today if local >= publish_at else previous_weekday(today)


def sessions_between(later: date, earlier: date) -> int:
    """Number of weekday sessions after `earlier` up to and including `later`."""
    n, d = 0, earlier
    while d < later:
        d += timedelta(days=1)
        if d.weekday() < 5:
            n += 1
    return n
