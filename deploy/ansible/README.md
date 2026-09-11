# Ansible deployment

Provisions the Pi(s) from your workstation in one command - two Pis (one role
each) or a single Pi running both roles.

## Prerequisites

* Ansible 2.15+ on your machine (`pipx install ansible`).
* SSH key access to the Pi(s), with a passwordless-sudo user (the Raspberry Pi
  Imager can set this up).
* Raspberry Pi OS Lite (64-bit, Bookworm), Pi 3B or newer.

## Use

```bash
cp inventory.example.ini inventory.ini
$EDITOR inventory.ini          # IPs, api_token, subnet, hub_url, notify backend
ansible-playbook -i inventory.ini site.yml
```

**One Pi, both roles:** put the *same* host in both the `[hub]` and `[sensor]`
groups (the example file has a commented block) and set
`netsentinel_hub_url=http://127.0.0.1:8080`. Both plays run against it; each
systemd unit pins its own role so the shared env file is fine.

Re-run at any time to pull the latest commit on `netsentinel_ref` and restart
the services.

## What it does

| Step | hub | sensor |
|---|:--:|:--:|
| apt deps (git, python venv; + nmap/libpcap on sensor) | ✓ | ✓ |
| `netsentinel` system user, `/opt/netsentinel`, `/var/lib/netsentinel` | ✓ | ✓ |
| clone repo + build venv (`.[sensor]` on the sensor) | ✓ | ✓ |
| render `/etc/netsentinel/netsentinel.env` from inventory vars | ✓ | ✓ |
| download IEEE OUI list | ✓ | ✓ |
| install + enable systemd unit | ✓ | ✓ |
| daily blocklist refresh cron | ✓ | |
| assert `local_subnet` is RFC1918 | | ✓ |
| health-check / log tail | ✓ | ✓ |

## Notes

* The env file is templated from inventory every run; put overrides in the
  inventory, not on the Pi.
* `ansible-playbook ... --limit sensor` to touch only one role.
* `--check --diff` for a dry run.
