#!/usr/bin/env bash
# Install NetSentinel as the SENSOR on this Raspberry Pi.
#   sudo NS_HUB_URL=http://192.168.1.2:8080 NS_TOKEN=... ./install-sensor.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$HERE/common.sh"

require_root
ensure_packages git python3 python3-venv python3-dev nmap libpcap0.8 iproute2 curl ca-certificates
ensure_user
sync_source
build_venv "[sensor]"
write_env_if_absent

ENV="$NS_ETC/netsentinel.env"
sed -i 's/^NETSENTINEL_ROLE=.*/NETSENTINEL_ROLE=sensor/' "$ENV"
[ -n "${NS_HUB_URL:-}" ] && sed -i "s#^NETSENTINEL_HUB_URL=.*#NETSENTINEL_HUB_URL=${NS_HUB_URL}#" "$ENV"
[ -n "${NS_TOKEN:-}" ]   && sed -i "s/^NETSENTINEL_API_TOKEN=.*/NETSENTINEL_API_TOKEN=${NS_TOKEN}/" "$ENV"
[ -n "${NS_SUBNET:-}" ]  && sed -i "s#^NETSENTINEL_LOCAL_SUBNET=.*#NETSENTINEL_LOCAL_SUBNET=${NS_SUBNET}#" "$ENV"
[ -n "${NS_IFACE:-}" ]   && sed -i "s/^NETSENTINEL_MONITOR_INTERFACE=.*/NETSENTINEL_MONITOR_INTERFACE=${NS_IFACE}/" "$ENV"

install -d -o "$NS_USER" -g "$NS_USER" /var/lib/netsentinel
refresh_oui
install_unit netsentinel-sensor.service

systemctl enable --now netsentinel-sensor.service
log "sensor started. IMPORTANT: confirm NETSENTINEL_LOCAL_SUBNET in $ENV is YOUR network."
log "check it is reporting:  journalctl -u netsentinel-sensor -f"
