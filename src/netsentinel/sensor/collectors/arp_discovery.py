"""Device discovery.

Strategy, cheapest first:

1. ``nmap -sn`` ping sweep of the configured subnet to refresh the kernel
   neighbour table (ARP for IPv4, NDP for IPv6).
2. Parse ``ip neigh`` for MAC/IP pairs; fall back to ``/proc/net/arp``.
3. Best-effort reverse-DNS for a friendly hostname.

Only the operator-configured ``local_subnet`` is ever touched.
"""

from __future__ import annotations

import ipaddress
import logging
import re
import socket
import subprocess
from pathlib import Path

from ...config import get_settings
from ...oui import lookup as oui_lookup
from ...oui import normalise_mac
from ...schemas import DeviceReport

log = logging.getLogger("netsentinel.sensor.discovery")

_NEIGH_RE = re.compile(
    r"^(?P<ip>[0-9a-fA-F:.]+)\s+dev\s+\S+\s+lladdr\s+(?P<mac>[0-9a-fA-F:]{17})\s+(?P<state>\w+)"
)


def _run(cmd: list[str], timeout: int) -> str:
    try:
        return subprocess.run(
            cmd, capture_output=True, text=True, timeout=timeout, check=False
        ).stdout
    except (OSError, subprocess.SubprocessError) as exc:
        log.warning("command %s failed: %s", cmd[0], exc)
        return ""


def _ping_sweep(subnet: str) -> None:
    net = ipaddress.ip_network(subnet, strict=False)
    if net.num_addresses > 4096:
        log.warning("subnet %s too large (%d hosts); skipping sweep", subnet, net.num_addresses)
        return
    _run(["nmap", "-sn", "-n", "-T4", "--host-timeout", "3s", str(net)], timeout=120)


def _parse_ip_neigh() -> list[tuple[str, str]]:
    out = _run(["ip", "-o", "neigh", "show"], timeout=10)
    pairs: list[tuple[str, str]] = []
    for line in out.splitlines():
        m = _NEIGH_RE.match(line.strip())
        if m and m.group("state").upper() not in {"FAILED", "INCOMPLETE"}:
            pairs.append((m.group("ip"), normalise_mac(m.group("mac"))))
    return pairs


def _parse_proc_arp() -> list[tuple[str, str]]:
    path = Path("/proc/net/arp")
    if not path.exists():
        return []
    pairs: list[tuple[str, str]] = []
    for line in path.read_text().splitlines()[1:]:
        cols = line.split()
        if len(cols) >= 4 and cols[3] != "00:00:00:00:00:00":
            pairs.append((cols[0], normalise_mac(cols[3])))
    return pairs


def _reverse_dns(ip: str) -> str:
    try:
        return socket.gethostbyaddr(ip)[0]
    except (OSError, socket.herror):
        return ""


def discover() -> list[DeviceReport]:
    settings = get_settings()
    subnet = settings.local_subnet
    try:
        net = ipaddress.ip_network(subnet, strict=False)
    except ValueError:
        log.error("invalid local_subnet %r; discovery disabled", subnet)
        return []

    _ping_sweep(subnet)

    seen: dict[str, DeviceReport] = {}
    for ip, mac in _parse_ip_neigh() or _parse_proc_arp():
        try:
            if ipaddress.ip_address(ip) not in net:
                continue
        except ValueError:
            continue
        if not mac or mac in {"00:00:00:00:00:00"}:
            continue
        rep = seen.get(mac)
        if rep is None:
            seen[mac] = DeviceReport(
                mac=mac, ip=ip, hostname=_reverse_dns(ip), vendor=oui_lookup(mac)
            )
        elif not rep.ip:
            rep.ip = ip

    log.info("discovery: %d device(s) in %s", len(seen), subnet)
    return list(seen.values())
