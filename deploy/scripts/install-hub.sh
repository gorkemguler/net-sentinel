#!/usr/bin/env bash
# Install NetSentinel as the HUB on this Raspberry Pi.
#   sudo NS_REPO_URL=https://github.com/you/net-sentinel.git ./install-hub.sh
set -euo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=common.sh
. "$HERE/common.sh"

require_root
ensure_packages git python3 python3-venv python3-dev curl ca-certificates
ensure_user
sync_source
build_venv "[]"          # hub needs no scapy
write_env_if_absent
sed -i 's/^NETSENTINEL_ROLE=.*/NETSENTINEL_ROLE=hub/' "$NS_ETC/netsentinel.env"
install -d -o "$NS_USER" -g "$NS_USER" /var/lib/netsentinel
refresh_oui
install_unit netsentinel-hub.service

systemctl enable --now netsentinel-hub.service
log "hub is up on http://$(hostname -I | awk '{print $1}'):8080/"
log "next: edit $NS_ETC/netsentinel.env (token, notify backend) then: systemctl restart netsentinel-hub"
