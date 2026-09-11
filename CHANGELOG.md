# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project aims to
follow [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Docs
- README: new **Hardware & requirements** (board matrix, per-role RAM, SD sizing,
  OS/software) and **Deployment topologies** (two Pis / one Pi / many sensors)
  sections.
- `docs/SETUP.md`: requirements checklist + a single-Pi (hub + sensor) walkthrough.
- `docker-compose.yml`: commented real single-host `sensor` service.
- Ansible: `inventory.example.ini` shows the one-Pi (same host in both groups)
  variant.

## [0.1.0] - 2026-09-09

### Added
- Hub: FastAPI REST API, Jinja2 dashboard, SQLite (WAL) storage.
- Ingest pipeline with detections: new device, device IP change, blocklisted
  DNS name/answer, DNS answer resolving to a flagged IP, newly-opened ports.
- Sensor: ARP/NDP device discovery, passive DNS capture (scapy), scheduled
  authorised `nmap` port-change scan, batched hub uplink with retries.
- Threat-intel enrichment: local blocklist + optional AbuseIPDB, cached in DB.
- Notifications: `log`, `ntfy`, `telegram`, `webhook` backends.
- Offline OUI (MAC vendor) lookup with a bundled sample.
- Deployment: systemd units, per-Pi install scripts, Ansible playbook,
  `docker compose` demo stack.
- CI: ruff + pytest on Python 3.11 / 3.12.

[Unreleased]: https://github.com/gorkemguler/net-sentinel/compare/v0.1.0...HEAD
[0.1.0]: https://github.com/gorkemguler/net-sentinel/releases/tag/v0.1.0
