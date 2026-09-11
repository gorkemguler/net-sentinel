"""Persisted data model (SQLModel / SQLite).

Kept intentionally small: five tables cover devices, DNS observations, a generic
event stream, alerts, and cached threat-intel verdicts.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlmodel import Field, SQLModel


def _now() -> datetime:
    return datetime.now(UTC)


class Device(SQLModel, table=True):
    """A host seen on the local network, keyed by MAC address."""

    mac: str = Field(primary_key=True, description="Normalised lower-case MAC.")
    ip: str = Field(default="", index=True)
    hostname: str = Field(default="")
    vendor: str = Field(default="")
    first_seen: datetime = Field(default_factory=_now)
    last_seen: datetime = Field(default_factory=_now, index=True)
    is_known: bool = Field(default=False, description="Operator has acknowledged this device.")
    note: str = Field(default="")


class DnsObservation(SQLModel, table=True):
    """Aggregated passive-DNS record: one row per (client, qname) per flush window."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_now, index=True)
    client_ip: str = Field(index=True)
    qname: str = Field(index=True)
    qtype: str = Field(default="A")
    answer: str = Field(default="", description="Comma-joined answers, best effort.")
    count: int = Field(default=1)
    flagged: bool = Field(default=False, description="qname or answer hit the blocklist.")


class Event(SQLModel, table=True):
    """Generic append-only event stream produced by the sensor collectors."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_now, index=True)
    sensor_id: str = Field(default="", index=True)
    kind: str = Field(index=True, description="device.new | device.seen | port.open | dns.flag ...")
    subject: str = Field(default="", index=True, description="MAC / IP / domain concerned.")
    severity: str = Field(default="info", description="info | low | medium | high")
    data_json: str = Field(default="{}", description="JSON blob with collector-specific detail.")


class Alert(SQLModel, table=True):
    """A notable event that was (or will be) delivered to the operator."""

    id: int | None = Field(default=None, primary_key=True)
    ts: datetime = Field(default_factory=_now, index=True)
    title: str
    body: str = Field(default="")
    severity: str = Field(default="medium")
    source_event_id: int | None = Field(default=None, foreign_key="event.id")
    delivered: bool = Field(default=False, index=True)
    acknowledged: bool = Field(default=False, index=True)


class ThreatVerdict(SQLModel, table=True):
    """Cached enrichment result for an external indicator (IP or domain)."""

    indicator: str = Field(primary_key=True)
    kind: str = Field(default="ip", description="ip | domain")
    score: int = Field(default=0, description="0-100, higher is worse.")
    verdict: str = Field(default="unknown", description="clean | suspicious | malicious | unknown")
    source: str = Field(default="")
    detail_json: str = Field(default="{}")
    checked_at: datetime = Field(default_factory=_now, index=True)
