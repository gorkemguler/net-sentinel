"""Thin HTTP client the sensor uses to talk to the hub."""

from __future__ import annotations

import logging

import httpx

from ..config import Settings, get_settings
from ..schemas import IngestBatch, IngestResult

log = logging.getLogger("netsentinel.sensor.client")


class HubClient:
    def __init__(self, settings: Settings | None = None) -> None:
        self.s = settings or get_settings()
        self._client = httpx.Client(
            base_url=self.s.hub_url.rstrip("/"),
            headers={"Authorization": f"Bearer {self.s.api_token}"},
            timeout=15,
        )

    def health(self) -> bool:
        try:
            r = self._client.get("/healthz")
            return r.is_success
        except httpx.HTTPError as exc:
            log.warning("hub health check failed: %s", exc)
            return False

    def send(self, batch: IngestBatch) -> IngestResult | None:
        if not (batch.devices or batch.dns or batch.ports):
            return None
        try:
            r = self._client.post("/api/ingest", json=batch.model_dump(mode="json"))
            r.raise_for_status()
            result = IngestResult.model_validate(r.json())
            log.info(
                "ingest ok: devices=%d dns=%d events=%d alerts=%d",
                result.devices_upserted,
                result.dns_rows,
                result.events_created,
                result.alerts_created,
            )
            return result
        except httpx.HTTPError as exc:
            log.error("ingest POST failed: %s", exc)
            return None

    def known_device_ips(self) -> list[str]:
        """Ask the hub which IPs it already knows, to focus the port scan."""
        try:
            r = self._client.get("/api/devices", params={"active_minutes": 1440})
            r.raise_for_status()
            return [d["ip"] for d in r.json() if d.get("ip")]
        except httpx.HTTPError as exc:
            log.warning("could not fetch known devices: %s", exc)
            return []

    def close(self) -> None:
        self._client.close()
