<p align="center"><img src="docs/logo.svg" width="72" height="72" alt=""></p>
<h1 align="center">NetSentinel</h1>

A home-network security monitor I built to run on a couple of spare Raspberry
Pis. One box watches the network, the other keeps the history and shows it to
you in a browser.

*[Türkçe README için buraya bakabilirsin](README.tr.md).*

![NetSentinel dashboard](docs/screenshot.png)

It runs as either two Pis or one, and it's built around three questions I
wanted answered without paying for a cloud service or installing an agent on
every device in the house:

1. **Who's actually on my network?** New device shows up, MAC vendor gets
   looked up, you get pinged.
2. **What is my network talking to?** Passive DNS logging, checked against a
   blocklist, with optional AbuseIPDB lookups for anything sketchy.
3. **What changed since yesterday?** Scheduled `nmap` scans of your own
   subnet flag newly opened ports before you find out the hard way.

Nothing leaves your LAN unless you turn on an enrichment API key or a push
notification backend. There's no phone-home telemetry in here.

The scanning stays inside `NETSENTINEL_LOCAL_SUBNET` - it won't touch
anything outside the range you configure. This is meant for a network you
own or administer, not for poking at other people's Wi-Fi.

---

## How it's put together

```
        ┌─────────────────────────┐          ┌──────────────────────────────┐
        │  Pi #1  -  sensor       │  HTTPS   │  Pi #2  -  hub               │
        │                         │  Bearer  │                              │
        │  • ARP/NDP discovery    │ ───────► │  • FastAPI  /api/*           │
        │  • passive DNS (scapy)  │  /api/   │  • ingest pipeline + rules   │
        │  • scheduled nmap       │  ingest  │  • SQLite (WAL)              │
        │  • batches + retries    │          │  • dashboard (Jinja2)        │
        │                         │          │  • notifier: ntfy/TG/webhook │
        └─────────────────────────┘          │  • APScheduler housekeeping  │
                                             └──────────────────────────────┘
```

Both sides are the same Python package, `netsentinel`; a systemd unit or an
env var (`NETSENTINEL_ROLE`) decides which one a given process becomes. I
usually run them on separate boards so the sensor sits closer to the switch,
but there's nothing stopping you from running both on one Pi - see below.

Data model and the actual detection rules are in
[`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md) if you want the details.

---

## Hardware you'll need

I run this on two Raspberry Pi 4B (2 GB) with a 64 GB card each, but that's
more than it actually needs.

### Picking a board per role

| Setup | Bare minimum | What I'd use | RAM in practice |
|---|---|---|---|
| hub only | Pi 3B / Zero 2 W, 512 MB free | Pi 4B 2 GB | ~90–140 MB |
| sensor only | Zero 2 W / Pi 3B, wired Ethernet | Pi 4B 2 GB | ~60–110 MB (scapy's the heavy part) |
| both roles, one Pi | Pi 3B, 1 GB | Pi 4B 2 GB | ~150–250 MB combined |
| more sensors | 1 hub + as many sensors as you want | a beefier hub board | one hub, many sensors |

Anything from a 3B up works fine. The Zero 2 W can run the sensor but I
wouldn't put the hub on it. There's no real ceiling on the upper end - a
bigger board just buys you more history and larger blocklists.

### SD card

8 GB is the floor (the OS image alone is ~2.5 GB). I'd get 16–32 GB, or point
the data directory at a USB SSD if you're worried about wear. At the default
retention settings the database grows something like 50–150 MB a month, so a
64 GB card will last you a long while.

### What you need installed

- Raspberry Pi OS Lite, 64-bit, Bookworm - it ships Python 3.11 already.
  32-bit works too, as does Ubuntu Server on a Pi.
- `nmap` on the sensor only (`sudo apt install nmap`). The hub doesn't need it.
- The sensor needs `CAP_NET_RAW` + `CAP_NET_ADMIN` to capture packets - the
  systemd unit grants just those, not full root.
- Wired Ethernet on the sensor if you can manage it. Wi-Fi mostly only sees
  its own traffic and broadcasts, which defeats the point of passive DNS.

### Actually seeing other devices' DNS traffic

This tripped me up the first time, so worth spelling out: the sensor only
sees packets that reach its network interface. Your options, roughly in order
of how much you'll actually see:

1. Mirror/SPAN port on your switch, feeding the sensor's NIC - best option.
2. Run the sensor directly on the router.
3. Point your router's DHCP-advertised DNS server at the sensor's IP - you
   only get DNS this way, but from every client on the network.
4. Don't bother with a mirror at all - you still get device discovery and
   port-change detection, just not other devices' lookups.

---

## Ways to run it

### Two Pis (what I actually run)

```
 Pi #1  "pi-sensor"                     Pi #2  "pi-hub"
 NETSENTINEL_ROLE=sensor  ──HTTPS/Bearer──►  NETSENTINEL_ROLE=hub
 discovery · passive DNS · nmap         API + dashboard on :8080
```

From your laptop:

```bash
git clone https://github.com/gorkemguler/net-sentinel.git
cd net-sentinel/deploy/ansible
cp inventory.example.ini inventory.ini     # fill in the two Pi IPs, a token, your subnet
ansible-playbook -i inventory.ini site.yml
```

That's it - it installs the package on both boxes, drops
`/etc/netsentinel/netsentinel.env`, and enables `netsentinel-hub` on one Pi
and `netsentinel-sensor` on the other. Dashboard's at `http://<hub-pi>:8080/`.
If you'd rather do it by hand, [`docs/SETUP.md`](docs/SETUP.md) walks through
each step.

### One Pi, both roles

Fine if you only have one board spare, or your network's small enough that
splitting roles doesn't buy you much. The sensor already defaults to talking
to the hub at `http://127.0.0.1:8080`, so there's nothing extra to configure.

```bash
sudo deploy/scripts/install-hub.sh
sudo NS_SUBNET=192.168.1.0/24 NS_IFACE=eth0 deploy/scripts/install-sensor.sh
systemctl status netsentinel-hub netsentinel-sensor
```

Or with Ansible, just put the same host under both `[hub]` and `[sensor]` in
your inventory - there's a commented example in `inventory.example.ini`.

`docker compose up --build` also works for this and includes a synthetic demo
sensor so you can see the dashboard without touching a real network; swap in
the commented `sensor` service in `docker-compose.yml` for a real capture
(host networking, `NET_RAW`/`NET_ADMIN`).

### Several sensors reporting to one hub

Give each sensor its own `NETSENTINEL_SENSOR_ID` and point all of them at the
same hub URL - one sensor per VLAN, or per physical site over a VPN. The hub
just merges everything into one inventory.

---

## Trying it without any Pi at all

```bash
docker compose up --build
# hub at http://localhost:8080, fed by a synthetic demo sensor
```

or, without Docker:

```bash
python -m venv .venv && . .venv/bin/activate
pip install -e ".[dev,sensor]"
cp .env.example .env
netsentinel gen-token           # put the result in .env as NETSENTINEL_API_TOKEN
netsentinel selftest
netsentinel hub                 # terminal 1
NETSENTINEL_ROLE=sensor netsentinel sensor   # terminal 2, needs sudo for live capture
```

---

## Configuration

Everything's an environment variable prefixed `NETSENTINEL_`, and a `.env`
file gets picked up automatically. The ones you'll actually touch:

| Variable | Default | What it does |
|---|---|---|
| `NETSENTINEL_ROLE` | `hub` | `hub` or `sensor` |
| `NETSENTINEL_API_TOKEN` | - | shared secret between sensor and hub; `netsentinel gen-token` |
| `NETSENTINEL_HUB_URL` | `http://127.0.0.1:8080` | where the sensor sends its data |
| `NETSENTINEL_LOCAL_SUBNET` | `192.168.1.0/24` | the only range the sensor will ever touch |
| `NETSENTINEL_MONITOR_INTERFACE` | `eth0` | which NIC the sensor captures on |
| `NETSENTINEL_NOTIFY_BACKEND` | `log` | `none` / `log` / `ntfy` / `telegram` / `webhook` |
| `NETSENTINEL_ABUSEIPDB_API_KEY` | - | optional, enables IP reputation lookups |
| `NETSENTINEL_DASHBOARD_USER` / `_PASSWORD` | - | basic auth on the dashboard, if you want it |

Everything else is documented in [`.env.example`](.env.example).

---

## The API

Swagger docs live at `/docs` on the hub. Short version:

| Method | Path | Does what |
|---|---|---|
| `POST` | `/api/ingest` | where a sensor pushes a batch (bearer auth) |
| `GET` | `/api/devices` | the inventory (`?unknown_only=true`, `?active_minutes=15`) |
| `PATCH` | `/api/devices/{mac}` | mark a device known, add a note |
| `GET` | `/api/dns/top` | most-queried names over a time window |
| `GET` | `/api/events` | raw event stream |
| `GET` | `/api/alerts` | alerts, newest first |
| `POST` | `/api/alerts/{id}/ack` | acknowledge one |
| `GET` | `/api/stats` | the numbers behind the dashboard |
| `GET` | `/healthz` | is it alive |

Full reference in [`docs/API.md`](docs/API.md).

---

## Running the tests

```bash
pip install -e ".[dev,sensor]"
ruff check .
pytest
```

## License

MIT - see [`LICENSE`](LICENSE).
