"""Passive DNS collector.

Sniffs UDP/53 responses on the monitor interface with scapy and aggregates them
into ``(client_ip, qname, qtype) -> (count, answers)`` until the runner flushes.

Requires either root or ``cap_net_raw`` on the Python interpreter. If scapy is
missing or the socket can't be opened, the collector disables itself and logs
once - the rest of the sensor keeps working.

To see *other* devices' lookups the sensor NIC must receive their traffic:
run it on the router, on a mirror/SPAN port, or point clients' DNS at the Pi.
"""

from __future__ import annotations

import contextlib
import logging
import threading
from collections import defaultdict
from datetime import UTC, datetime

from ...config import get_settings
from ...schemas import DnsRecord

log = logging.getLogger("netsentinel.sensor.pdns")

_QTYPE = {1: "A", 28: "AAAA", 5: "CNAME", 15: "MX", 16: "TXT", 33: "SRV", 2: "NS", 12: "PTR"}


class PassiveDns:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._agg: dict[tuple[str, str, str], dict] = defaultdict(
            lambda: {"count": 0, "answers": set()}
        )
        self._sniffer = None
        self._enabled = False

    # ------------------------------------------------------------------ control
    def start(self) -> None:
        try:
            from scapy.all import DNS, AsyncSniffer  # noqa: F401
        except Exception as exc:  # pragma: no cover - env dependent
            log.warning("scapy unavailable (%s); passive DNS disabled", exc)
            return

        from scapy.all import AsyncSniffer

        iface = get_settings().monitor_interface
        try:
            self._sniffer = AsyncSniffer(
                iface=iface,
                filter="udp port 53",
                prn=self._on_packet,
                store=False,
            )
            self._sniffer.start()
            self._enabled = True
            log.info("passive DNS sniffing on %s", iface)
        except Exception as exc:  # pragma: no cover - env dependent
            log.error("could not start sniffer on %s: %s (need root/cap_net_raw)", iface, exc)

    def stop(self) -> None:
        if self._sniffer is not None:
            with contextlib.suppress(Exception):  # pragma: no cover
                self._sniffer.stop()

    @property
    def enabled(self) -> bool:
        return self._enabled

    # ------------------------------------------------------------------ capture
    def _on_packet(self, pkt) -> None:  # pragma: no cover - needs live traffic
        try:
            from scapy.layers.dns import DNS, DNSRR
            from scapy.layers.inet import IP

            if not pkt.haslayer(DNS) or not pkt.haslayer(IP):
                return
            dns = pkt[DNS]
            if dns.qr != 1 or dns.qd is None:  # only responses, with a question
                return
            qname = dns.qd.qname.decode("idna", "replace").rstrip(".").lower()
            qtype = _QTYPE.get(int(dns.qd.qtype), str(dns.qd.qtype))
            client = pkt[IP].dst  # response destination == the client that asked

            answers: list[str] = []
            for i in range(int(dns.ancount)):
                rr = dns.an[i] if dns.ancount > 1 else dns.an
                if isinstance(rr, DNSRR):
                    rdata = rr.rdata
                    answers.append(rdata.decode() if isinstance(rdata, bytes) else str(rdata))

            key = (client, qname, qtype)
            with self._lock:
                slot = self._agg[key]
                slot["count"] += 1
                slot["answers"].update(a for a in answers if a)
        except Exception:
            return

    # ------------------------------------------------------------------ flush
    def drain(self) -> list[DnsRecord]:
        now = datetime.now(UTC)
        with self._lock:
            agg, self._agg = self._agg, defaultdict(lambda: {"count": 0, "answers": set()})
        out = [
            DnsRecord(
                client_ip=client,
                qname=qname,
                qtype=qtype,
                answer=",".join(sorted(slot["answers"]))[:512],
                count=slot["count"],
                ts=now,
            )
            for (client, qname, qtype), slot in agg.items()
        ]
        if out:
            log.info("passive DNS flush: %d aggregated record(s)", len(out))
        return out
