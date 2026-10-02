"""Alert conditions, evaluation on stored data, and delivery (in-app, browser, email).

An alert never triggers a data-provider call by itself: it reads the bars and signals already
stored. The daily job refreshes prices first (within the EODHD budget) and then evaluates.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.models.entities import Alert, AlertEvent, Stock, User
from app.services import shariah as shariah_svc
from app.services.prices import latest_bar

log = logging.getLogger("hss.alerts")

CONDITIONS: dict[str, dict] = {
    "price_above": {"label": "Close at or above a price", "param": "level"},
    "price_below": {"label": "Close at or below a price", "param": "level"},
    "rsi_above": {"label": "RSI 14 at or above a value", "param": "value"},
    "rsi_below": {"label": "RSI 14 at or below a value", "param": "value"},
    "score_above": {"label": "Setup score at or above a value", "param": "value"},
    "signal_is": {"label": "Signal changes to a type", "param": "signal"},
    "enters_entry_zone": {"label": "Close inside the entry zone", "param": None},
    "shariah_change": {"label": "Shariah status changes", "param": None},
}
CHANNELS = ("in_app", "browser", "email")
LEVEL_TYPES = {"price_above", "price_below", "rsi_above", "rsi_below", "score_above", "enters_entry_zone"}


def email_configured() -> bool:
    s = get_settings()
    return bool(s.smtp_host and (s.smtp_from or s.smtp_user))


def describe(cond: dict) -> str:
    t = cond.get("type")
    if t == "price_above":
        return f"Close at or above {cond['level']:,.2f}"
    if t == "price_below":
        return f"Close at or below {cond['level']:,.2f}"
    if t == "rsi_above":
        return f"RSI 14 at or above {cond['value']:g}"
    if t == "rsi_below":
        return f"RSI 14 at or below {cond['value']:g}"
    if t == "score_above":
        return f"Setup score at or above {cond['value']:g}"
    if t == "signal_is":
        return f"Signal changes to {cond['signal'].replace('_', ' ')}"
    if t == "enters_entry_zone":
        return "Close inside the signal's entry zone"
    if t == "shariah_change":
        return "Shariah status changes"
    return t or "Unknown condition"


def check(cond: dict, ctx: dict, state: dict) -> tuple[bool | None, dict, str]:
    """Pure condition test. Returns (met, observed values, message). None = cannot be evaluated."""
    t = cond["type"]
    close, sig = ctx.get("close"), ctx.get("signal")
    snap = (sig or {}).get("snapshot", {}) if sig else {}
    if t in ("price_above", "price_below"):
        if close is None:
            return None, {}, "No stored close"
        met = close >= cond["level"] if t == "price_above" else close <= cond["level"]
        return met, {"close": close}, f"Close {close:,.2f} vs {cond['level']:,.2f}"
    if t in ("rsi_above", "rsi_below"):
        r = snap.get("rsi")
        if r is None:
            return None, {}, "RSI unavailable (needs at least 15 bars)"
        met = r >= cond["value"] if t == "rsi_above" else r <= cond["value"]
        return met, {"rsi": r}, f"RSI {r:.1f} vs {cond['value']:g}"
    if t == "score_above":
        sc = (sig or {}).get("score")
        if sc is None:
            return None, {}, "Setup score unavailable"
        return sc >= cond["value"], {"score": sc}, f"Setup score {sc:.0f} vs {cond['value']:g}"
    if t == "signal_is":
        st = (sig or {}).get("signal_type")
        if st is None:
            return None, {}, "Signal unavailable (needs at least 30 bars)"
        met = st == cond["signal"] and state.get("last_signal") != cond["signal"]
        return met, {"signal": st}, f"Signal is now {st.replace('_', ' ')}"
    if t == "enters_entry_zone":
        lo_, hi_ = (sig or {}).get("entry_low"), (sig or {}).get("entry_high")
        if close is None or lo_ is None or hi_ is None:
            return None, {}, "No entry zone defined"
        return lo_ <= close <= hi_, {"close": close, "entry_low": lo_, "entry_high": hi_}, \
            f"Close {close:,.2f} vs entry zone {lo_:,.2f} to {hi_:,.2f}"
    if t == "shariah_change":
        cur = ctx.get("shariah")
        last = state.get("last_shariah")
        met = last is not None and cur != last
        return met, {"shariah": cur}, f"Shariah status {str(last).replace('_', ' ')} to {cur.replace('_', ' ')}"
    return None, {}, "Unknown condition"


def _context(db: Session, stock: Stock, user: User, cache: dict) -> dict:
    key = (stock.id, user.id)
    if key in cache:
        return cache[key]
    from app.services.analysis import analyze  # local import: analysis imports this module's neighbours
    bar = latest_bar(db, stock.id)
    out = analyze(db, stock, user)
    ctx = {"close": bar.close if bar else None, "bar_date": bar.ts.date().isoformat() if bar else None,
           "signal": out[1].to_dict() if out else None,
           "shariah": shariah_svc.status_for(db, stock, shariah_svc.user_methodology(db, user))}
    cache[key] = ctx
    return ctx


def _send_email(to: str, subject: str, body: str) -> str:
    s = get_settings()
    if not email_configured():
        return "not configured"
    msg = EmailMessage()
    msg["From"] = s.smtp_from or s.smtp_user
    msg["To"] = to
    msg["Subject"] = subject
    msg.set_content(body)
    try:
        with smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=10) as smtp:
            if s.smtp_starttls:
                smtp.starttls(context=ssl.create_default_context())
            if s.smtp_user and s.smtp_password:
                smtp.login(s.smtp_user, s.smtp_password)
            smtp.send_message(msg)
        return "sent"
    except Exception as e:  # never surface credentials; the class name is enough to diagnose
        log.warning("Alert email failed: %s", type(e).__name__)
        return f"failed ({type(e).__name__})"


def _fire(db: Session, a: Alert, stock: Stock, user: User, ctx: dict, observed: dict, message: str,
          now: datetime) -> AlertEvent:
    title = f"{stock.ticker}: {a.name}"
    payload = {"title": title, "message": message, "condition": describe(a.condition), "observed": observed,
               "ticker": stock.ticker, "exchange": stock.exchange.code, "bar_date": ctx.get("bar_date")}
    delivered = {"in_app": "stored"}
    if "browser" in a.channels:
        delivered["browser"] = "shown when the app is open"
    if "email" in a.channels:
        body = (f"{title}\n\n{message}\nCondition: {describe(a.condition)}\nData: close of {ctx.get('bar_date')}\n\n"
                "This is research information, not investment advice. The platform never places trades.")
        delivered["email"] = _send_email(user.email, f"Halal Stock Signals alert: {title}", body)
    ev = AlertEvent(alert_id=a.id, payload=payload, delivered=delivered, triggered_at=now)
    db.add(ev)
    a.last_triggered_at = now
    return ev


def evaluate(db: Session, alerts: list[Alert], now: datetime | None = None) -> list[AlertEvent]:
    now = now or datetime.now(UTC)
    cache: dict = {}
    fired: list[AlertEvent] = []
    for a in alerts:
        if not a.is_active or a.stock_id is None:
            continue
        stock = db.get(Stock, a.stock_id)
        user = db.get(User, a.user_id)
        if stock is None or user is None:
            continue
        ctx = _context(db, stock, user, cache)
        state = dict(a.state or {})
        met, observed, message = check(a.condition, ctx, state)
        last = a.last_triggered_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        cooled = last is None or now - last >= timedelta(minutes=a.cooldown_minutes)
        same_bar = a.condition["type"] in LEVEL_TYPES and state.get("last_fired_bar") == ctx.get("bar_date")
        if met and cooled and not same_bar:
            fired.append(_fire(db, a, stock, user, ctx, observed, message, now))
            state["last_fired_bar"] = ctx.get("bar_date")
        if ctx.get("signal"):
            state["last_signal"] = ctx["signal"]["signal_type"]
        state["last_shariah"] = ctx.get("shariah")
        state["last_result"] = None if met is None else bool(met)
        state["last_message"] = message
        a.state = state
        a.last_evaluated_at = now
    db.commit()
    return fired


def evaluate_for_stock(db: Session, stock: Stock) -> list[AlertEvent]:
    rows = db.scalars(select(Alert).where(Alert.stock_id == stock.id, Alert.is_active.is_(True))).all()
    return evaluate(db, list(rows)) if rows else []


def evaluate_for_user(db: Session, user: User) -> list[AlertEvent]:
    rows = db.scalars(select(Alert).where(Alert.user_id == user.id, Alert.is_active.is_(True))).all()
    return evaluate(db, list(rows))


def evaluate_all(db: Session) -> list[AlertEvent]:
    return evaluate(db, list(db.scalars(select(Alert).where(Alert.is_active.is_(True))).all()))
