"""Ingest pipeline: turn a sensor :class:`IngestBatch` into devices, DNS rows,
events and alerts.

All detection logic lives here so it is unit-testable without HTTP or a scheduler.
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime

from sqlmodel import Session, select

from ..models import Alert, Device, DnsObservation, Event, ThreatVerdict
from ..oui import lookup as oui_lookup
from ..oui import normalise_mac
from ..schemas import IngestBatch, IngestResult
from ..threatintel import enrich, is_blocklisted

log = logging.getLogger("netsentinel.pipeline")


def _mk_event(session: Session, **kw) -> Event:
    ev = Event(**kw)
    session.add(ev)
    session.flush()  # populate ev.id
    return ev


def _mk_alert(session: Session, ev: Event | None, title: str, body: str, severity: str) -> Alert:
    al = Alert(
        title=title,
        body=body,
        severity=severity,
        source_event_id=ev.id if ev else None,
    )
    session.add(al)
    return al


def process_batch(session: Session, batch: IngestBatch) -> IngestResult:
    result = IngestResult()
    sid = batch.sensor_id or "unknown"

    _process_devices(session, sid, batch, result)
    _process_dns(session, sid, batch, result)
    _process_ports(session, sid, batch, result)

    return result


# --------------------------------------------------------------------- devices
def _process_devices(session: Session, sid: str, batch: IngestBatch, result: IngestResult) -> None:
    for rep in batch.devices:
        mac = normalise_mac(rep.mac)
        if not mac:
            continue
        seen_at = rep.seen_at or datetime.now(UTC)
        dev = session.get(Device, mac)
        if dev is None:
            dev = Device(
                mac=mac,
                ip=rep.ip,
                hostname=rep.hostname,
                vendor=rep.vendor or oui_lookup(mac),
                first_seen=seen_at,
                last_seen=seen_at,
            )
            session.add(dev)
            result.devices_upserted += 1
            ev = _mk_event(
                session,
                sensor_id=sid,
                kind="device.new",
                subject=mac,
                severity="medium",
                data_json=json.dumps(
                    {"ip": dev.ip, "hostname": dev.hostname, "vendor": dev.vendor}
                ),
            )
            result.events_created += 1
            _mk_alert(
                session,
                ev,
                title=f"New device on the network: {dev.hostname or dev.ip or mac}",
                body=f"MAC {mac} ({dev.vendor or 'unknown vendor'}) at {dev.ip or 'unknown IP'}.",
                severity="medium",
            )
            result.alerts_created += 1
        else:
            changed_ip = rep.ip and rep.ip != dev.ip
            dev.ip = rep.ip or dev.ip
            dev.hostname = rep.hostname or dev.hostname
            dev.vendor = dev.vendor or rep.vendor or oui_lookup(mac)
            dev.last_seen = max(dev.last_seen.replace(tzinfo=UTC), seen_at)
            session.add(dev)
            result.devices_upserted += 1
            if changed_ip:
                _mk_event(
                    session,
                    sensor_id=sid,
                    kind="device.ip_change",
                    subject=mac,
                    severity="low",
                    data_json=json.dumps({"ip": rep.ip}),
                )
                result.events_created += 1


# ------------------------------------------------------------------------- dns
def _process_dns(session: Session, sid: str, batch: IngestBatch, result: IngestResult) -> None:
    for rec in batch.dns:
        qname = rec.qname.rstrip(".").lower()
        if not qname:
            continue
        flagged = is_blocklisted(qname) or any(
            is_blocklisted(a.strip()) for a in rec.answer.split(",") if a.strip()
        )
        row = DnsObservation(
            ts=rec.ts or datetime.now(UTC),
            client_ip=rec.client_ip,
            qname=qname,
            qtype=rec.qtype,
            answer=rec.answer,
            count=max(1, rec.count),
            flagged=flagged,
        )
        session.add(row)
        result.dns_rows += 1

        if flagged:
            ev = _mk_event(
                session,
                sensor_id=sid,
                kind="dns.flag",
                subject=qname,
                severity="high",
                data_json=json.dumps({"client": rec.client_ip, "answer": rec.answer}),
            )
            result.events_created += 1
            _mk_alert(
                session,
                ev,
                title=f"Blocklisted domain queried: {qname}",
                body=f"{rec.client_ip} looked up {qname} (answer: {rec.answer or 'n/a'}).",
                severity="high",
            )
            result.alerts_created += 1

        # Enrich the first public answer IP; cheap thanks to the verdict cache.
        for ans in (a.strip() for a in rec.answer.split(",")):
            if not ans:
                continue
            verdict: ThreatVerdict = enrich(session, ans, kind="ip")
            if verdict.verdict in {"malicious", "suspicious"}:
                ev = _mk_event(
                    session,
                    sensor_id=sid,
                    kind="dns.badip",
                    subject=qname,
                    severity="high" if verdict.verdict == "malicious" else "medium",
                    data_json=verdict.detail_json,
                )
                result.events_created += 1
                _mk_alert(
                    session,
                    ev,
                    title=f"{qname} resolves to a flagged IP ({ans})",
                    body=f"Verdict {verdict.verdict} / score {verdict.score} via {verdict.source}.",
                    severity="high" if verdict.verdict == "malicious" else "medium",
                )
                result.alerts_created += 1
            break


# ----------------------------------------------------------------------- ports
def _process_ports(session: Session, sid: str, batch: IngestBatch, result: IngestResult) -> None:
    for rep in batch.ports:
        prev = _latest_port_event(session, rep.ip)
        prev_ports = set(prev) if prev is not None else None
        now_ports = set(rep.open_ports)

        _mk_event(
            session,
            sensor_id=sid,
            kind="port.snapshot",
            subject=rep.ip,
            severity="info",
            data_json=json.dumps({"open": sorted(now_ports), "services": rep.services}),
        )
        result.events_created += 1

        if prev_ports is None:
            continue
        opened = sorted(now_ports - prev_ports)
        closed = sorted(prev_ports - now_ports)
        if opened:
            ev = _mk_event(
                session,
                sensor_id=sid,
                kind="port.open",
                subject=rep.ip,
                severity="medium",
                data_json=json.dumps({"opened": opened, "services": rep.services}),
            )
            result.events_created += 1
            svc = ", ".join(f"{p}:{rep.services.get(f'{p}/tcp', '?')}" for p in opened)
            _mk_alert(
                session,
                ev,
                title=f"New open port(s) on {rep.ip}: {opened}",
                body=f"Services: {svc}",
                severity="medium",
            )
            result.alerts_created += 1
        if closed:
            _mk_event(
                session,
                sensor_id=sid,
                kind="port.close",
                subject=rep.ip,
                severity="low",
                data_json=json.dumps({"closed": closed}),
            )
            result.events_created += 1


def _latest_port_event(session: Session, ip: str) -> list[int] | None:
    stmt = (
        select(Event)
        .where(Event.kind == "port.snapshot", Event.subject == ip)
        .order_by(Event.ts.desc())
        .limit(1)
    )
    row = session.exec(stmt).first()
    if row is None:
        return None
    try:
        return list(json.loads(row.data_json).get("open", []))
    except json.JSONDecodeError:
        return None
