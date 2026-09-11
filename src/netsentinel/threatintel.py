"""Threat-intel enrichment for external indicators.

Two cheap sources, both optional:

* a local newline-delimited blocklist (domains and/or IPs), refreshed by cron;
* the AbuseIPDB "check" endpoint when an API key is configured.

Results are cached in the ``threatverdict`` table for a day so we never hammer
the upstream API from a Pi.
"""

from __future__ import annotations

import ipaddress
import json
import logging
from datetime import UTC, datetime, timedelta
from functools import lru_cache

import httpx
from sqlmodel import Session, select

from .config import Settings, get_settings
from .models import ThreatVerdict

log = logging.getLogger("netsentinel.ti")

_CACHE_TTL = timedelta(hours=24)


@lru_cache(maxsize=1)
def _blocklist() -> set[str]:
    settings = get_settings()
    path = settings.blocklist_path
    if not path.exists():
        return set()
    entries: set[str] = set()
    for line in path.read_text(encoding="utf-8", errors="replace").splitlines():
        line = line.strip().lower()
        if not line or line.startswith(("#", "!")):
            continue
        # Tolerate hosts-file syntax: "0.0.0.0 baddomain.tld".
        parts = line.split()
        entries.add(parts[-1])
    log.info("threat-intel blocklist: %d entries", len(entries))
    return entries


def is_blocklisted(indicator: str) -> bool:
    indicator = indicator.lower().strip(".")
    bl = _blocklist()
    if indicator in bl:
        return True
    # Match parent domains: foo.bar.example.com hits "example.com".
    labels = indicator.split(".")
    return any(".".join(labels[i:]) in bl for i in range(1, len(labels) - 1))


def _is_public_ip(value: str) -> bool:
    try:
        ip = ipaddress.ip_address(value)
    except ValueError:
        return False
    return not (ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_multicast)


def enrich(session: Session, indicator: str, kind: str = "ip") -> ThreatVerdict:
    """Return a cached-or-fresh verdict for one indicator."""
    settings = get_settings()
    cached = session.get(ThreatVerdict, indicator)
    if cached and datetime.now(UTC) - cached.checked_at.replace(tzinfo=UTC) < _CACHE_TTL:
        return cached

    score, verdict, source, detail = 0, "unknown", "none", {}

    if is_blocklisted(indicator):
        score, verdict, source = 100, "malicious", "blocklist"
        detail = {"reason": "present on local blocklist"}
    elif kind == "ip" and _is_public_ip(indicator) and settings.abuseipdb_api_key:
        score, verdict, source, detail = _abuseipdb(settings, indicator)

    row = cached or ThreatVerdict(indicator=indicator, kind=kind)
    row.score = score
    row.verdict = verdict
    row.source = source
    row.detail_json = json.dumps(detail)
    row.checked_at = datetime.now(UTC)
    session.add(row)
    return row


def _abuseipdb(settings: Settings, ip: str) -> tuple[int, str, str, dict]:
    try:
        r = httpx.get(
            "https://api.abuseipdb.com/api/v2/check",
            params={"ipAddress": ip, "maxAgeInDays": 90},
            headers={"Key": settings.abuseipdb_api_key, "Accept": "application/json"},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json().get("data", {})
        score = int(data.get("abuseConfidenceScore", 0))
        verdict = "malicious" if score >= 75 else "suspicious" if score >= 25 else "clean"
        return (
            score,
            verdict,
            "abuseipdb",
            {
                "totalReports": data.get("totalReports"),
                "countryCode": data.get("countryCode"),
                "isp": data.get("isp"),
                "domain": data.get("domain"),
            },
        )
    except Exception as exc:  # pragma: no cover - network dependent
        log.warning("AbuseIPDB lookup for %s failed: %s", ip, exc)
        return 0, "unknown", "abuseipdb-error", {"error": str(exc)}


def verdicts_summary(session: Session, limit: int = 50) -> list[ThreatVerdict]:
    stmt = (
        select(ThreatVerdict)
        .where(ThreatVerdict.verdict != "clean")
        .where(ThreatVerdict.verdict != "unknown")
        .order_by(ThreatVerdict.score.desc(), ThreatVerdict.checked_at.desc())
        .limit(limit)
    )
    return list(session.exec(stmt))
