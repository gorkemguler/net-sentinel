#!/usr/bin/env bash
# Shared helpers for the install scripts. Source this; don't run it.
set -euo pipefail

NS_PREFIX="${NS_PREFIX:-/opt/netsentinel}"
NS_ETC="${NS_ETC:-/etc/netsentinel}"
NS_USER="${NS_USER:-netsentinel}"
NS_REPO_URL="${NS_REPO_URL:-https://github.com/gorkemguler/net-sentinel.git}"
NS_REF="${NS_REF:-main}"

log()  { printf '\033[1;36m[netsentinel]\033[0m %s\n' "$*"; }
die()  { printf '\033[1;31m[netsentinel] %s\033[0m\n' "$*" >&2; exit 1; }

require_root() { [ "$(id -u)" -eq 0 ] || die "run as root (sudo)"; }

ensure_packages() {
  log "installing OS packages: $*"
  if command -v apt-get >/dev/null; then
    apt-get update -qq
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "$@"
  else
    die "this script assumes apt (Raspberry Pi OS / Debian)"
  fi
}

ensure_user() {
  id "$NS_USER" >/dev/null 2>&1 || {
    log "creating system user $NS_USER"
    useradd --system --home-dir "$NS_PREFIX" --shell /usr/sbin/nologin "$NS_USER"
  }
}

sync_source() {
  mkdir -p "$NS_PREFIX"
  if [ -d "$NS_PREFIX/src/.git" ]; then
    log "updating source in $NS_PREFIX/src"
    git -C "$NS_PREFIX/src" fetch --depth 1 origin "$NS_REF"
    git -C "$NS_PREFIX/src" reset --hard "origin/$NS_REF"
  else
    log "cloning $NS_REPO_URL@$NS_REF"
    git clone --depth 1 --branch "$NS_REF" "$NS_REPO_URL" "$NS_PREFIX/src"
  fi
}

build_venv() {
  local extras="$1"
  log "building venv ($extras)"
  python3 -m venv "$NS_PREFIX/venv"
  "$NS_PREFIX/venv/bin/pip" install -q --upgrade pip
  "$NS_PREFIX/venv/bin/pip" install -q "$NS_PREFIX/src${extras}"
}

write_env_if_absent() {
  mkdir -p "$NS_ETC"
  if [ ! -f "$NS_ETC/netsentinel.env" ]; then
    log "writing starter $NS_ETC/netsentinel.env (EDIT IT)"
    local token
    token="$("$NS_PREFIX/venv/bin/netsentinel" gen-token)"
    sed "s/^NETSENTINEL_API_TOKEN=.*/NETSENTINEL_API_TOKEN=${token}/" \
        "$NS_PREFIX/src/.env.example" > "$NS_ETC/netsentinel.env"
    chmod 640 "$NS_ETC/netsentinel.env"
    chgrp "$NS_USER" "$NS_ETC/netsentinel.env"
  else
    log "$NS_ETC/netsentinel.env already exists, leaving it"
  fi
}

install_unit() {
  local unit="$1"
  log "installing systemd unit $unit"
  install -m 644 "$NS_PREFIX/src/deploy/systemd/$unit" "/etc/systemd/system/$unit"
  systemctl daemon-reload
}

refresh_oui() {
  local dest="/var/lib/netsentinel/oui.csv"
  mkdir -p /var/lib/netsentinel
  log "fetching IEEE OUI list -> $dest (best effort)"
  curl -fsSL --retry 2 -o "$dest" \
    "https://standards-oui.ieee.org/oui/oui.csv" || log "OUI download failed; using bundled sample"
  chown -R "$NS_USER" /var/lib/netsentinel
}
