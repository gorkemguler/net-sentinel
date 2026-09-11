#!/usr/bin/env bash
# Rebuild /var/lib/netsentinel/blocklist.txt from public feeds.
# Run from cron on the HUB, e.g. daily:  0 4 * * *  /opt/netsentinel/src/deploy/scripts/refresh-blocklist.sh
set -euo pipefail

DEST="${NETSENTINEL_BLOCKLIST_PATH:-/var/lib/netsentinel/blocklist.txt}"
TMP="$(mktemp)"
trap 'rm -f "$TMP"' EXIT

FEEDS=(
  "https://urlhaus.abuse.ch/downloads/hostfile/"
  "https://raw.githubusercontent.com/StevenBlack/hosts/master/hosts"
)

echo "# generated $(date -u +%FT%TZ) by refresh-blocklist.sh" > "$TMP"
for url in "${FEEDS[@]}"; do
  echo "fetching $url" >&2
  curl -fsSL --retry 2 "$url" \
    | sed -E 's/#.*$//; s/\r$//' \
    | awk '{ for (i=1;i<=NF;i++) if ($i !~ /^(0\.0\.0\.0|127\.0\.0\.1|::1?|localhost)$/) print tolower($i) }' \
    >> "$TMP" || echo "  (feed failed, skipping)" >&2
done

sort -u "$TMP" -o "$TMP"
install -m 644 "$TMP" "$DEST"
echo "wrote $(wc -l < "$DEST") indicators to $DEST"
