# Architecture

## Processes

| Process | Package entry | Long-running work |
|---|---|---|
| **hub** | `netsentinel hub` → `uvicorn netsentinel.hub.app:app` | HTTP server; APScheduler jobs `deliver` (30 s) and `prune` (6 h) |
| **sensor** | `netsentinel sensor` → `netsentinel.sensor.runner:main` | APScheduler jobs `discovery`, `dns_flush`, `portscan`; a scapy `AsyncSniffer` thread |

They share one code package; `NETSENTINEL_ROLE` and the CLI subcommand pick the
runtime. Nothing but the hub touches the database.

## Data flow

```
 collectors (sensor)            HubClient            FastAPI /api/ingest
 ─────────────────────          ─────────            ───────────────────
 arp_discovery.discover() ─┐
 PassiveDns.drain()        ├─►  IngestBatch  ──POST──►  process_batch()
 port_scan.scan()          ┘   (bearer auth)                │
                                                            ▼
                                            ┌───────────────────────────────┐
                                            │ pipeline: upsert Device,      │
                                            │ insert DnsObservation,        │
                                            │ append Event, raise Alert,    │
                                            │ enrich() external IPs         │
                                            └───────────────┬───────────────┘
                                                            ▼
                                     SQLite (WAL)  ◄──►  dashboard + REST reads
                                                            │
                                          deliver job ──►  Notifier (ntfy/TG/webhook)
```

## Storage model (`netsentinel/models.py`)

| Table | Key | Notes |
|---|---|---|
| `device` | `mac` | `first_seen` / `last_seen`, `is_known`, free-text `note` |
| `dnsobservation` | `id` | one row per `(client, qname, qtype)` per sensor flush window; `flagged` |
| `event` | `id` | append-only; `kind`, `subject`, `severity`, `data_json` |
| `alert` | `id` | `delivered`, `acknowledged`, optional `source_event_id` |
| `threatverdict` | `indicator` | enrichment cache, 24 h TTL |

`event` and `dnsobservation` are pruned on the retention schedule; `device`,
`alert` and `threatverdict` are kept.

## Detection rules (`netsentinel/hub/pipeline.py`)

| Trigger | Event kind | Alert severity |
|---|---|---|
| MAC never seen before | `device.new` | medium |
| Known MAC, changed IP | `device.ip_change` | (event only) |
| `qname` or an answer on the blocklist | `dns.flag` | high |
| First public answer IP has verdict `malicious` / `suspicious` | `dns.badip` | high / medium |
| Port open now, absent in the previous snapshot for that IP | `port.open` | medium |
| Port gone since the previous snapshot | `port.close` | (event only) |
| Every port scan | `port.snapshot` | info |

The previous snapshot is just the most recent `port.snapshot` event for that IP,
so port-diffing needs no extra state.

## Why these choices

* **SQLite/WAL** - a 2 GB Pi has no spare RAM for Postgres; the write rate of a
  home LAN is trivial; backups are `cp`.
* **Sensor pushes, hub is passive** - the sensor can live on an isolated mirror
  port with only outbound access to the hub.
* **scapy import is lazy** - hub installs stay tiny and CI needs no libpcap.
* **APScheduler, not cron** - one process to supervise per Pi, schedules live
  next to the code.

## Extending

* New collector → `netsentinel/sensor/collectors/`, return schema objects, wire a
  job in `runner.py`.
* New detection → a `_process_*` branch in `pipeline.py` + a test.
* New notifier → a branch in `netsentinel/notify.py` and a `notify_backend` value.
