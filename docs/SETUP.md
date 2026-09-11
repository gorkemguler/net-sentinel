# Manual setup

Prefer automation? Use [`deploy/ansible/`](../deploy/ansible/README.md). This
page is the by-hand equivalent, for **two Pis** (§1–2) or **one Pi** (§1b).

## Requirements checklist

| | Need |
|---|---|
| Board(s) | Raspberry Pi 3B or newer (3B/3B+/4B/5/Zero 2 W/CM3/CM4). Two for the split layout, one for all-in-one. Pi 4B 2 GB is the tested target. |
| microSD | 8 GB minimum, 16–32 GB recommended (a 64 GB card is plenty). Or a USB SSD for the data dir. |
| OS | Raspberry Pi OS Lite 64-bit (Bookworm) - ships Python 3.11. Ubuntu Server 24.04 also fine. |
| Python | 3.11+ (already on Bookworm). |
| Packages | `git`, `python3-venv` on both roles; **`nmap`, `libpcap0.8`** on the sensor. |
| Privilege | `sudo` for install. The sensor needs `CAP_NET_RAW`+`CAP_NET_ADMIN` (systemd unit grants them). |
| Network | Sensor on **wired Ethernet**. Only outbound sensor→hub connectivity is required. |
| Ideally | A switch mirror/SPAN port feeding the sensor NIC, so it sees other devices' traffic (see §3). |

See the README's **Hardware & requirements** for per-role RAM figures and the
board matrix.

## 0. Prepare the Pi(s)

* Flash Raspberry Pi OS Lite 64-bit (Bookworm). Enable SSH in Raspberry Pi Imager.
* Give a static DHCP lease. Example names/IPs used below:
  * two-Pi: `pi-hub` → `192.168.1.2`, `pi-sensor` → `192.168.1.3`
  * one-Pi: `pi-sentinel` → `192.168.1.2`
* Decide your LAN CIDR, e.g. `192.168.1.0/24`.

Generate one shared token and keep it handy:

```bash
python3 -c "import secrets; print(secrets.token_hex(32))"
```

## 1. Hub (`pi-hub`)

```bash
sudo apt update && sudo apt install -y git python3-venv
git clone https://github.com/gorkemguler/net-sentinel.git
cd net-sentinel
sudo NS_REPO_URL="$PWD/.git" deploy/scripts/install-hub.sh
```

or without the script:

```bash
python3 -m venv ~/ns && ~/ns/bin/pip install -e .
mkdir -p ~/ns-data
cat > ~/ns.env <<'EOF'
NETSENTINEL_ROLE=hub
NETSENTINEL_DATA_DIR=/home/pi/ns-data
NETSENTINEL_API_TOKEN=<paste the token>
NETSENTINEL_NOTIFY_BACKEND=ntfy
NETSENTINEL_NTFY_TOPIC=my-netsentinel-abc123
EOF
set -a && . ~/ns.env && set +a
~/ns/bin/netsentinel hub
```

Open `http://192.168.1.2:8080/`.

## 2. Sensor (`pi-sensor`)

```bash
sudo apt update && sudo apt install -y git python3-venv nmap libpcap0.8
git clone https://github.com/gorkemguler/net-sentinel.git && cd net-sentinel
sudo NS_HUB_URL=http://192.168.1.2:8080 \
     NS_TOKEN=<paste the token> \
     NS_SUBNET=192.168.1.0/24 \
     NS_IFACE=eth0 \
     deploy/scripts/install-sensor.sh
```

Verify it is reporting:

```bash
journalctl -u netsentinel-sensor -f
# then, on the hub:
curl -s -H "Authorization: Bearer <token>" http://192.168.1.2:8080/api/devices | jq length
```

## 1b. One Pi - hub **and** sensor on the same board

Do §0, then run **both** installers on the one Pi. The hub install writes
`/etc/netsentinel/netsentinel.env` (with a fresh token); the sensor install
reuses that file. Each systemd unit pins its own role, so one shared env file is
correct.

```bash
sudo apt update && sudo apt install -y git python3-venv nmap libpcap0.8
git clone https://github.com/gorkemguler/net-sentinel.git && cd net-sentinel

# 1) hub
sudo NS_REPO_URL="$PWD/.git" deploy/scripts/install-hub.sh

# 2) sensor (same box). Hub URL defaults to http://127.0.0.1:8080 - no need to set it.
sudo NS_REPO_URL="$PWD/.git" \
     NS_SUBNET=192.168.1.0/24 \
     NS_IFACE=eth0 \
     deploy/scripts/install-sensor.sh

# 3) set the notify backend once, then restart the hub
sudo sed -i 's/^NETSENTINEL_NOTIFY_BACKEND=.*/NETSENTINEL_NOTIFY_BACKEND=ntfy/' /etc/netsentinel/netsentinel.env
sudo sed -i 's/^NETSENTINEL_NTFY_TOPIC=.*/NETSENTINEL_NTFY_TOPIC=my-netsentinel-abc123/' /etc/netsentinel/netsentinel.env
sudo systemctl restart netsentinel-hub

systemctl status netsentinel-hub netsentinel-sensor --no-pager
```

Open `http://192.168.1.2:8080/`. Everything else on this page (notifications,
troubleshooting) applies unchanged - "the hub" and "the sensor" are just two
services on the one Pi.

Non-persistent alternative (dev): `netsentinel hub &` in one shell, then
`sudo NETSENTINEL_ROLE=sensor NETSENTINEL_MONITOR_INTERFACE=eth0 NETSENTINEL_LOCAL_SUBNET=192.168.1.0/24 netsentinel sensor` in another.

## 3. Seeing other devices' DNS

Passive DNS only sees traffic that reaches the sensor's NIC. Pick one:

* **Router plugin / SPAN port** - mirror LAN traffic to `pi-sensor`'s port.
* **Sensor as resolver** - set your router's DHCP "DNS server" option to
  `192.168.1.3`, and run a resolver (`unbound`/`dnsmasq`) on the sensor. NetSentinel
  still just sniffs; it does not resolve.
* **Single-host mode** - no mirror: you'll still get discovery, port-change
  detection and the sensor's own lookups.

## 4. Notifications

Set on the **hub** and restart it:

* **ntfy**: `NETSENTINEL_NOTIFY_BACKEND=ntfy`, `NETSENTINEL_NTFY_TOPIC=...`
  (subscribe on your phone with the ntfy app).
* **Telegram**: `..._BACKEND=telegram`, `..._TELEGRAM_BOT_TOKEN`, `..._CHAT_ID`.
* **Webhook**: `..._BACKEND=webhook`, `..._WEBHOOK_URL` (Home Assistant, n8n…).

Test: `netsentinel test-alert --severity high`.

## 5. SD-card longevity

* Put `NETSENTINEL_DATA_DIR` on a USB SSD if you can.
* Otherwise install `log2ram` and lengthen commit intervals.
* Default retention keeps the DB well under ~1 GB.

## Troubleshooting

| Symptom | Check |
|---|---|
| `/api/devices` empty | sensor logs; is `NETSENTINEL_LOCAL_SUBNET` your LAN? is `nmap` installed? |
| No DNS rows | sensor NIC isn't receiving other hosts' traffic (see §3); needs `CAP_NET_RAW` |
| Sensor `permission denied` on capture | run via the systemd unit (it grants caps) or `sudo setcap cap_net_raw,cap_net_admin+eip $(readlink -f venv/bin/python)` |
| Alerts not delivered | `netsentinel test-alert`; check `notify_backend` + creds on the hub |
| `401` from ingest | token mismatch between the two `.env` files |
