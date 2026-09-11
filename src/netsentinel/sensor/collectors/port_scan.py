"""Scheduled port-change scan.

Runs nmap against the sensor's own subnet (or the specific IPs the hub already
knows), parses the XML, and returns one :class:`PortReport` per host. The hub
diffs consecutive snapshots and alerts on newly-opened ports.

This is *authorised* scanning of the operator's own LAN only - ``local_subnet``
is enforced here and again on the hub.
"""

from __future__ import annotations

import ipaddress
import logging
import shlex
import subprocess
import xml.etree.ElementTree as ET

from ...config import get_settings
from ...schemas import PortReport

log = logging.getLogger("netsentinel.sensor.portscan")


def _targets(explicit_ips: list[str] | None) -> str | None:
    settings = get_settings()
    try:
        net = ipaddress.ip_network(settings.local_subnet, strict=False)
    except ValueError:
        log.error("invalid local_subnet; port scan disabled")
        return None
    if explicit_ips:
        inside = [ip for ip in explicit_ips if _in_net(ip, net)]
        return " ".join(inside) if inside else None
    return str(net)


def _in_net(ip: str, net) -> bool:
    try:
        return ipaddress.ip_address(ip) in net
    except ValueError:
        return False


def scan(explicit_ips: list[str] | None = None) -> list[PortReport]:
    settings = get_settings()
    target = _targets(explicit_ips)
    if not target:
        log.info("no in-scope targets for port scan")
        return []

    cmd = ["nmap", *shlex.split(settings.portscan_nmap_args), "-oX", "-", *target.split()]
    log.info("running: %s", " ".join(cmd))
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=1800, check=False)
    except (OSError, subprocess.SubprocessError) as exc:
        log.error("nmap failed: %s", exc)
        return []
    if not proc.stdout.strip():
        log.error("nmap produced no XML (stderr: %s)", proc.stderr.strip()[:300])
        return []
    return parse_nmap_xml(proc.stdout)


def parse_nmap_xml(xml_text: str) -> list[PortReport]:
    reports: list[PortReport] = []
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        log.error("could not parse nmap XML: %s", exc)
        return []

    for host in root.findall("host"):
        status = host.find("status")
        if status is not None and status.get("state") != "up":
            continue
        ip = mac = ""
        for addr in host.findall("address"):
            kind = addr.get("addrtype")
            if kind in {"ipv4", "ipv6"}:
                ip = addr.get("addr", "")
            elif kind == "mac":
                mac = (addr.get("addr", "") or "").lower()
        if not ip:
            continue

        open_ports: list[int] = []
        services: dict[str, str] = {}
        ports_el = host.find("ports")
        if ports_el is not None:
            for port in ports_el.findall("port"):
                state = port.find("state")
                if state is None or state.get("state") != "open":
                    continue
                pnum = int(port.get("portid", "0"))
                proto = port.get("protocol", "tcp")
                open_ports.append(pnum)
                svc = port.find("service")
                if svc is not None:
                    name = svc.get("name", "")
                    product = svc.get("product", "")
                    version = svc.get("version", "")
                    services[f"{pnum}/{proto}"] = " ".join(x for x in (name, product, version) if x)
        reports.append(PortReport(ip=ip, mac=mac, open_ports=sorted(open_ports), services=services))

    log.info("port scan parsed %d host(s)", len(reports))
    return reports
