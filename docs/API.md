# HTTP API

Base URL: `http://<hub>:8080`. Interactive docs: `/docs` (Swagger), `/redoc`.

Auth: every `/api/*` route needs `Authorization: Bearer <NETSENTINEL_API_TOKEN>`.
`/healthz` is open. The dashboard routes (`/`, `/devices`, …) use optional
HTTP-basic instead.

## Meta

### `GET /healthz`
```json
{ "status": "ok", "version": "0.1.0", "role": "hub", "detail": {} }
```

### `GET /api/stats`
Dashboard counters.
```json
{
  "devices_total": 14, "devices_unknown": 2, "devices_active_15m": 9,
  "dns_rows_24h": 5120, "dns_flagged_24h": 3, "alerts_open": 1,
  "notify_backend": "ntfy", "generated_at": "2026-09-09T12:00:00+00:00"
}
```

## Ingest (sensor → hub)

### `POST /api/ingest`
Body - any subset of `devices` / `dns` / `ports` may be present:
```json
{
  "sensor_id": "sensor-1",
  "devices": [
    { "mac": "b8:27:eb:11:22:33", "ip": "192.168.1.50", "hostname": "pi-hole", "vendor": "" }
  ],
  "dns": [
    { "client_ip": "192.168.1.10", "qname": "example.com", "qtype": "A", "answer": "93.184.216.34", "count": 3 }
  ],
  "ports": [
    { "ip": "192.168.1.50", "open_ports": [22, 53, 80], "services": { "22/tcp": "ssh OpenSSH 9.2p1" } }
  ]
}
```
Response:
```json
{ "accepted": true, "devices_upserted": 1, "dns_rows": 1, "events_created": 2, "alerts_created": 1 }
```

## Devices

| Method | Path | Query | |
|---|---|---|---|
| `GET` | `/api/devices` | `unknown_only=bool`, `active_minutes=int` | list |
| `PATCH` | `/api/devices/{mac}` | `is_known=bool`, `note=str` | acknowledge / annotate |

```bash
curl -H "Authorization: Bearer $T" \
  -X PATCH "http://hub:8080/api/devices/b8:27:eb:11:22:33?is_known=true&note=printer"
```

## DNS

### `GET /api/dns/top?hours=24&limit=50`
```json
[ { "qname": "example.com", "hits": 812, "flagged": false } ]
```

## Events & alerts

| Method | Path | Query |
|---|---|---|
| `GET` | `/api/events` | `kind=str`, `limit=int` |
| `GET` | `/api/alerts` | `unacknowledged_only=bool`, `limit=int` |
| `POST` | `/api/alerts/{id}/ack` | - |

Event `kind` values: `device.new`, `device.ip_change`, `dns.flag`, `dns.badip`,
`port.snapshot`, `port.open`, `port.close`.

## Errors

Standard FastAPI shape: `{ "detail": "..." }` with `401` (bad/missing token),
`404` (unknown mac / alert id), `422` (validation).
