"""Sensor entry point: wires the collectors to a scheduler and the hub client."""

from __future__ import annotations

import logging
import signal
import sys
import time

from apscheduler.schedulers.background import BackgroundScheduler

from ..config import get_settings
from ..schemas import IngestBatch
from .client import HubClient
from .collectors import arp_discovery, port_scan
from .collectors.passive_dns import PassiveDns

log = logging.getLogger("netsentinel.sensor")


class Sensor:
    def __init__(self) -> None:
        self.s = get_settings()
        self.hub = HubClient(self.s)
        self.pdns = PassiveDns()
        self.sched = BackgroundScheduler(timezone="UTC")

    # ------------------------------------------------------------------ jobs
    def job_discovery(self) -> None:
        devices = arp_discovery.discover()
        if devices:
            self.hub.send(IngestBatch(sensor_id=self.s.sensor_id, devices=devices))

    def job_dns_flush(self) -> None:
        records = self.pdns.drain()
        if records:
            self.hub.send(IngestBatch(sensor_id=self.s.sensor_id, dns=records))

    def job_portscan(self) -> None:
        known = self.hub.known_device_ips()
        reports = port_scan.scan(known or None)
        if reports:
            self.hub.send(IngestBatch(sensor_id=self.s.sensor_id, ports=reports))

    # ------------------------------------------------------------------ lifecycle
    def run(self) -> None:
        logging.basicConfig(
            level=self.s.log_level.upper(),
            format="%(asctime)s %(levelname)-7s %(name)s: %(message)s",
        )
        log.info("sensor %s -> hub %s", self.s.sensor_id, self.s.hub_url)
        if not self.hub.health():
            log.warning("hub not reachable yet; will keep trying on schedule")

        self.pdns.start()
        self.sched.add_job(
            self.job_discovery,
            "interval",
            seconds=self.s.discovery_interval_seconds,
            next_run_time=_soon(),
            id="discovery",
            max_instances=1,
        )
        self.sched.add_job(
            self.job_dns_flush,
            "interval",
            seconds=self.s.dns_flush_interval_seconds,
            id="dns_flush",
            max_instances=1,
        )
        self.sched.add_job(
            self.job_portscan,
            "interval",
            seconds=self.s.portscan_interval_seconds,
            next_run_time=_soon(30),
            id="portscan",
            max_instances=1,
        )
        self.sched.start()

        stop = signal.SIGTERM, signal.SIGINT
        for sig in stop:
            signal.signal(sig, self._shutdown)
        while True:
            time.sleep(1)

    def _shutdown(self, *_a) -> None:
        log.info("shutting down sensor")
        self.sched.shutdown(wait=False)
        self.pdns.stop()
        self.hub.close()
        sys.exit(0)


def _soon(offset: int = 3):
    from datetime import UTC, datetime, timedelta

    return datetime.now(UTC) + timedelta(seconds=offset)


def main() -> None:
    Sensor().run()


if __name__ == "__main__":
    main()
