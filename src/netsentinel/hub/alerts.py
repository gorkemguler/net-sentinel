"""Alert delivery and retention housekeeping (driven by APScheduler)."""

from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta

from sqlmodel import Session, delete, select

from ..config import get_settings
from ..db import session_scope
from ..models import Alert, DnsObservation, Event
from ..notify import Notifier

log = logging.getLogger("netsentinel.alerts")


def deliver_pending(session: Session | None = None, notifier: Notifier | None = None) -> int:
    """Push every undelivered alert through the notifier. Returns count sent."""
    own = session is None
    ctx = session_scope() if own else _null_ctx(session)
    notifier = notifier or Notifier()
    sent = 0
    with ctx as s:
        pending = s.exec(
            select(Alert).where(Alert.delivered == False).order_by(Alert.ts)  # noqa: E712
        ).all()
        for alert in pending:
            ok = notifier.send(alert.title, alert.body, alert.severity)
            alert.delivered = bool(ok)
            s.add(alert)
            if ok:
                sent += 1
    if sent:
        log.info("delivered %d alert(s)", sent)
    return sent


def prune_old_rows() -> dict[str, int]:
    """Drop DNS + event rows past their retention window."""
    settings = get_settings()
    now = datetime.now(UTC)
    dns_cutoff = now - timedelta(days=settings.dns_retention_days)
    ev_cutoff = now - timedelta(days=settings.event_retention_days)
    removed: dict[str, int] = {}
    with session_scope() as s:
        r1 = s.exec(delete(DnsObservation).where(DnsObservation.ts < dns_cutoff))
        r2 = s.exec(delete(Event).where(Event.ts < ev_cutoff))
        removed = {"dns": r1.rowcount or 0, "events": r2.rowcount or 0}
    log.info("retention sweep removed %s", removed)
    return removed


class _null_ctx:
    """Wrap an externally-owned session so ``with`` works without closing it."""

    def __init__(self, session: Session) -> None:
        self._s = session

    def __enter__(self) -> Session:
        return self._s

    def __exit__(self, *exc) -> None:
        return None
