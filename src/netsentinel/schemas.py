"""Wire formats for the sensor -> hub API.

These are deliberately separate from the ORM models so the on-the-wire contract
can evolve independently of the storage schema.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field


class DeviceReport(BaseModel):
    mac: str
    ip: str = ""
    hostname: str = ""
    vendor: str = ""
    seen_at: datetime | None = None


class DnsRecord(BaseModel):
    client_ip: str
    qname: str
    qtype: str = "A"
    answer: str = ""
    count: int = 1
    ts: datetime | None = None


class PortReport(BaseModel):
    ip: str
    mac: str = ""
    open_ports: list[int] = Field(default_factory=list)
    services: dict[str, str] = Field(default_factory=dict)  # "port/proto" -> "name version"


class IngestBatch(BaseModel):
    """One POST from a sensor. Any subset of the payload types may be present."""

    sensor_id: str
    devices: list[DeviceReport] = Field(default_factory=list)
    dns: list[DnsRecord] = Field(default_factory=list)
    ports: list[PortReport] = Field(default_factory=list)


class IngestResult(BaseModel):
    accepted: bool = True
    devices_upserted: int = 0
    dns_rows: int = 0
    events_created: int = 0
    alerts_created: int = 0


class HealthReport(BaseModel):
    status: Literal["ok", "degraded"] = "ok"
    version: str
    role: str
    detail: dict[str, Any] = Field(default_factory=dict)
