"""Server-rendered dashboard (Jinja2, no JS build step).

Read-only views over the same data the JSON API exposes. Protected by optional
HTTP-basic auth (see :func:`netsentinel.security.require_dashboard_user`).
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from pathlib import Path

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlmodel import Session, func, select

from .. import __version__
from ..db import get_session
from ..models import Alert, Device, DnsObservation, Event
from ..security import require_dashboard_user

_HERE = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=_HERE / "templates")
templates.env.filters["ago"] = lambda dt: _humanise_ago(dt)

router = APIRouter(dependencies=[Depends(require_dashboard_user)], include_in_schema=False)


def _humanise_ago(dt: datetime | None) -> str:
    if dt is None:
        return "never"
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    delta = datetime.now(UTC) - dt
    secs = int(delta.total_seconds())
    if secs < 60:
        return f"{secs}s ago"
    if secs < 3600:
        return f"{secs // 60}m ago"
    if secs < 86400:
        return f"{secs // 3600}h ago"
    return f"{secs // 86400}d ago"


def _render(request: Request, name: str, **extra):
    """Starlette >=1.0 wants (request, name, context)."""
    context = {"version": __version__, "now": datetime.now(UTC), **extra}
    return templates.TemplateResponse(request, name, context)


@router.get("/", response_class=HTMLResponse)
def index(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    now = datetime.now(UTC)
    day_ago = now - timedelta(hours=24)

    counters = {
        "devices": session.exec(select(func.count()).select_from(Device)).one(),
        "unknown": session.exec(
            select(func.count()).select_from(Device).where(Device.is_known == False)  # noqa: E712
        ).one(),
        "active": session.exec(
            select(func.count())
            .select_from(Device)
            .where(Device.last_seen >= now - timedelta(minutes=15))
        ).one(),
        "alerts_open": session.exec(
            select(func.count()).select_from(Alert).where(Alert.acknowledged == False)  # noqa: E712
        ).one(),
        "dns_flagged": session.exec(
            select(func.count())
            .select_from(DnsObservation)
            .where(DnsObservation.ts >= day_ago, DnsObservation.flagged == True)  # noqa: E712
        ).one(),
    }

    recent_alerts = session.exec(select(Alert).order_by(Alert.ts.desc()).limit(8)).all()
    new_devices = session.exec(select(Device).order_by(Device.first_seen.desc()).limit(8)).all()

    # 24h alert histogram by hour for the sparkline.
    hist_rows = session.exec(
        select(func.strftime("%H", Alert.ts), func.count())
        .where(Alert.ts >= day_ago)
        .group_by(func.strftime("%H", Alert.ts))
    ).all()
    hist = {int(h): c for h, c in hist_rows}
    series = [hist.get((now - timedelta(hours=i)).hour, 0) for i in range(23, -1, -1)]

    return _render(
        request,
        "index.html",
        counters=counters,
        recent_alerts=recent_alerts,
        new_devices=new_devices,
        alert_series=series,
    )


@router.get("/devices", response_class=HTMLResponse)
def devices_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    rows = session.exec(select(Device).order_by(Device.last_seen.desc())).all()
    return _render(request, "devices.html", devices=rows)


@router.get("/dns", response_class=HTMLResponse)
def dns_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    cutoff = datetime.now(UTC) - timedelta(hours=24)
    top = session.exec(
        select(
            DnsObservation.qname,
            func.sum(DnsObservation.count),
            func.max(DnsObservation.flagged),
        )
        .where(DnsObservation.ts >= cutoff)
        .group_by(DnsObservation.qname)
        .order_by(func.sum(DnsObservation.count).desc())
        .limit(100)
    ).all()
    flagged = session.exec(
        select(DnsObservation)
        .where(DnsObservation.flagged == True)  # noqa: E712
        .order_by(DnsObservation.ts.desc())
        .limit(50)
    ).all()
    return _render(
        request,
        "dns.html",
        top=[(q, int(h), bool(f)) for q, h, f in top],
        flagged=flagged,
    )


@router.get("/alerts", response_class=HTMLResponse)
def alerts_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    rows = session.exec(select(Alert).order_by(Alert.ts.desc()).limit(200)).all()
    return _render(request, "alerts.html", alerts=rows)


@router.get("/events", response_class=HTMLResponse)
def events_page(request: Request, session: Session = Depends(get_session)) -> HTMLResponse:
    rows = session.exec(select(Event).order_by(Event.ts.desc()).limit(300)).all()
    return _render(request, "events.html", events=rows)
