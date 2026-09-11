"""JSON REST API.

* ``POST /api/ingest``        - sensors push batches here (bearer auth).
* ``GET  /api/devices``       - inventory, filterable.
* ``PATCH /api/devices/{mac}``- acknowledge / annotate a device.
* ``GET  /api/dns/top``       - most-queried names in a window.
* ``GET  /api/events``        - raw event stream.
* ``GET  /api/alerts``        - alerts, newest first.
* ``POST /api/alerts/{id}/ack``
* ``GET  /api/stats``         - dashboard summary counters.
* ``GET  /healthz``           - liveness.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlmodel import Session, func, select

from .. import __version__
from ..config import get_settings
from ..db import get_session
from ..models import Alert, Device, DnsObservation, Event
from ..schemas import HealthReport, IngestBatch, IngestResult
from ..security import require_api_token
from .pipeline import process_batch

router = APIRouter()


@router.get("/healthz", response_model=HealthReport, tags=["meta"])
def healthz() -> HealthReport:
    return HealthReport(status="ok", version=__version__, role="hub")


@router.post(
    "/api/ingest",
    response_model=IngestResult,
    dependencies=[Depends(require_api_token)],
    tags=["ingest"],
)
def ingest(batch: IngestBatch, session: Session = Depends(get_session)) -> IngestResult:
    return process_batch(session, batch)


@router.get("/api/devices", dependencies=[Depends(require_api_token)], tags=["devices"])
def list_devices(
    session: Session = Depends(get_session),
    unknown_only: bool = False,
    active_minutes: int | None = Query(default=None, ge=1),
) -> list[Device]:
    stmt = select(Device).order_by(Device.last_seen.desc())
    if unknown_only:
        stmt = stmt.where(Device.is_known == False)  # noqa: E712
    if active_minutes:
        cutoff = datetime.now(UTC) - timedelta(minutes=active_minutes)
        stmt = stmt.where(Device.last_seen >= cutoff)
    return list(session.exec(stmt))


@router.patch("/api/devices/{mac}", dependencies=[Depends(require_api_token)], tags=["devices"])
def update_device(
    mac: str,
    is_known: bool | None = None,
    note: str | None = None,
    session: Session = Depends(get_session),
) -> Device:
    dev = session.get(Device, mac.lower())
    if dev is None:
        raise HTTPException(404, "device not found")
    if is_known is not None:
        dev.is_known = is_known
    if note is not None:
        dev.note = note
    session.add(dev)
    return dev


@router.get("/api/dns/top", dependencies=[Depends(require_api_token)], tags=["dns"])
def dns_top(
    session: Session = Depends(get_session),
    hours: int = Query(default=24, ge=1, le=720),
    limit: int = Query(default=50, ge=1, le=500),
) -> list[dict]:
    cutoff = datetime.now(UTC) - timedelta(hours=hours)
    stmt = (
        select(
            DnsObservation.qname,
            func.sum(DnsObservation.count).label("hits"),
            func.max(DnsObservation.flagged).label("flagged"),
        )
        .where(DnsObservation.ts >= cutoff)
        .group_by(DnsObservation.qname)
        .order_by(func.sum(DnsObservation.count).desc())
        .limit(limit)
    )
    return [{"qname": q, "hits": int(h), "flagged": bool(f)} for q, h, f in session.exec(stmt)]


@router.get("/api/events", dependencies=[Depends(require_api_token)], tags=["events"])
def list_events(
    session: Session = Depends(get_session),
    kind: str | None = None,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Event]:
    stmt = select(Event).order_by(Event.ts.desc()).limit(limit)
    if kind:
        stmt = stmt.where(Event.kind == kind)
    return list(session.exec(stmt))


@router.get("/api/alerts", dependencies=[Depends(require_api_token)], tags=["alerts"])
def list_alerts(
    session: Session = Depends(get_session),
    unacknowledged_only: bool = False,
    limit: int = Query(default=100, ge=1, le=1000),
) -> list[Alert]:
    stmt = select(Alert).order_by(Alert.ts.desc()).limit(limit)
    if unacknowledged_only:
        stmt = stmt.where(Alert.acknowledged == False)  # noqa: E712
    return list(session.exec(stmt))


@router.post(
    "/api/alerts/{alert_id}/ack",
    dependencies=[Depends(require_api_token)],
    tags=["alerts"],
)
def ack_alert(alert_id: int, session: Session = Depends(get_session)) -> Alert:
    alert = session.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(404, "alert not found")
    alert.acknowledged = True
    session.add(alert)
    return alert


@router.get("/api/stats", dependencies=[Depends(require_api_token)], tags=["meta"])
def stats(session: Session = Depends(get_session)) -> dict:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)
    active_since = now - timedelta(minutes=15)
    active = session.exec(
        select(func.count()).select_from(Device).where(Device.last_seen >= active_since)
    ).one()
    return {
        "devices_total": session.exec(select(func.count()).select_from(Device)).one(),
        "devices_unknown": session.exec(
            select(func.count()).select_from(Device).where(Device.is_known == False)  # noqa: E712
        ).one(),
        "devices_active_15m": active,
        "dns_rows_24h": session.exec(
            select(func.count()).select_from(DnsObservation).where(DnsObservation.ts >= day_ago)
        ).one(),
        "dns_flagged_24h": session.exec(
            select(func.count())
            .select_from(DnsObservation)
            .where(DnsObservation.ts >= day_ago, DnsObservation.flagged == True)  # noqa: E712
        ).one(),
        "alerts_open": session.exec(
            select(func.count()).select_from(Alert).where(Alert.acknowledged == False)  # noqa: E712
        ).one(),
        "notify_backend": get_settings().notify_backend,
        "generated_at": now.isoformat(),
    }
