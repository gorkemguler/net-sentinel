"""Offline MAC -> vendor lookup.

Uses an IEEE OUI CSV (``oui.csv``) placed in the data dir. ``deploy/scripts``
downloads the full file at install time; ``data/oui-sample.csv`` ships a tiny
subset so tests and first-run work without network.
"""

from __future__ import annotations

import csv
import logging
from functools import lru_cache
from pathlib import Path

from .config import get_settings

log = logging.getLogger("netsentinel.oui")

_SAMPLE = Path(__file__).resolve().parent.parent.parent / "data" / "oui-sample.csv"


def normalise_mac(mac: str) -> str:
    hexstr = "".join(c for c in mac.lower() if c in "0123456789abcdef")
    if len(hexstr) != 12:
        return mac.lower().strip()
    return ":".join(hexstr[i : i + 2] for i in range(0, 12, 2))


def _oui_key(mac: str) -> str:
    return normalise_mac(mac).replace(":", "")[:6].upper()


@lru_cache(maxsize=1)
def _table() -> dict[str, str]:
    settings = get_settings()
    candidates = [settings.data_dir / "oui.csv", _SAMPLE]
    table: dict[str, str] = {}
    for path in candidates:
        if not path.exists():
            continue
        try:
            with path.open(newline="", encoding="utf-8", errors="replace") as fh:
                reader = csv.reader(fh)
                header = next(reader, None)
                # Support both the IEEE export ("Registry,Assignment,Organization Name,...")
                # and a simple "prefix,vendor" two-column format.
                assign_idx, org_idx = 1, 2
                if header and header[0].strip().lower() in {"prefix", "oui"}:
                    assign_idx, org_idx = 0, 1
                for row in reader:
                    if len(row) <= max(assign_idx, org_idx):
                        continue
                    key = row[assign_idx].strip().replace("-", "").replace(":", "").upper()[:6]
                    if key:
                        table.setdefault(key, row[org_idx].strip())
            if table:
                log.info("loaded %d OUI entries from %s", len(table), path)
                break
        except Exception as exc:  # pragma: no cover - defensive
            log.warning("failed reading OUI file %s: %s", path, exc)
    return table


def lookup(mac: str) -> str:
    if not mac:
        return ""
    # Locally administered / random MACs (2nd-least-significant bit of 1st octet).
    first_octet = _oui_key(mac)[:2]
    try:
        if int(first_octet, 16) & 0b10:
            return "Randomised MAC"
    except ValueError:
        pass
    return _table().get(_oui_key(mac), "")
