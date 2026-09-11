#!/usr/bin/env python3
"""Synthetic sensor for the docker-compose demo.

Generates plausible device / DNS / port findings and POSTs them to the hub on a
loop so the dashboard has something to show without a real network. Not used in
a real deployment - that's `netsentinel sensor`.
"""

from __future__ import annotations

import os
import random
import time

import httpx

HUB = os.environ.get("NETSENTINEL_HUB_URL", "http://localhost:8080").rstrip("/")
TOKEN = os.environ.get("NETSENTINEL_API_TOKEN", "demo-token-change-me")
SENSOR_ID = os.environ.get("NETSENTINEL_SENSOR_ID", "demo-sensor")

DEVICES = [
    ("b8:27:eb:1a:2b:3c", "192.168.1.2", "raspberrypi-hub"),
    ("dc:a6:32:44:55:66", "192.168.1.3", "raspberrypi-sensor"),
    ("a4:c1:38:77:88:99", "192.168.1.10", "living-room-tv"),
    ("f0:27:2d:aa:bb:cc", "192.168.1.11", "echo-kitchen"),
    ("5c:e2:8c:de:ad:01", "192.168.1.20", "phone-galaxy"),
    ("2c:cf:67:12:34:56", "192.168.1.30", ""),  # unknown-ish
]
GOOD_DNS = [
    "api.github.com",
    "raw.githubusercontent.com",
    "ntp.ubuntu.com",
    "cdn.jsdelivr.net",
    "grafana.com",
    "pypi.org",
    "1.1.1.1.nip.io",
]
BAD_DNS = ["c2.evil.example", "phishing.example", "malware-test.example"]


def client() -> httpx.Client:
    return httpx.Client(base_url=HUB, headers={"Authorization": f"Bearer {TOKEN}"}, timeout=10)


def wait_for_hub(c: httpx.Client) -> None:
    for _ in range(60):
        try:
            if c.get("/healthz").is_success:
                return
        except httpx.HTTPError:
            pass
        time.sleep(2)
    raise SystemExit("hub never became healthy")


def tick(c: httpx.Client, i: int) -> None:
    seen = random.sample(DEVICES, k=random.randint(3, len(DEVICES)))
    dns = [
        {"client_ip": ip, "qname": random.choice(GOOD_DNS), "answer": "140.82.121.6"}
        for _, ip, _ in seen
    ]
    if i % 5 == 4:  # occasionally emit a "bad" lookup
        _, bad_ip, _ = random.choice(seen)
        dns.append({"client_ip": bad_ip, "qname": random.choice(BAD_DNS), "answer": "6.6.6.6"})

    ports = []
    if i % 3 == 0:
        base = [22, 80] + ([443] if i % 6 == 0 else [])
        if i and i % 9 == 0:
            base.append(4444)  # a "new open port" to trigger an alert
        ports = [{"ip": "192.168.1.2", "open_ports": base, "services": {"22/tcp": "OpenSSH 9.2p1"}}]

    payload = {
        "sensor_id": SENSOR_ID,
        "devices": [{"mac": m, "ip": ip, "hostname": h} for m, ip, h in seen],
        "dns": dns,
        "ports": ports,
    }
    r = c.post("/api/ingest", json=payload)
    print(f"tick {i}: {r.status_code} {r.text[:120]}", flush=True)


def main() -> None:
    with client() as c:
        wait_for_hub(c)
        i = 0
        while True:
            try:
                tick(c, i)
            except httpx.HTTPError as exc:
                print(f"tick {i} failed: {exc}", flush=True)
            i += 1
            time.sleep(15)


if __name__ == "__main__":
    main()
