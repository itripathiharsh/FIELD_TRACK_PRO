#!/usr/bin/env bash
# FieldTrack Pro - one-time base setup of a FRESH Ubuntu 24.04 VPS (run as root or with sudo).
#
#   sudo ./00_base_setup.sh            # DRY RUN: prints every command it would run, changes nothing
#   sudo ./00_base_setup.sh --apply    # performs the setup
#
# Idempotent: safe to re-run. It does NOT touch SSH daemon settings (so it cannot lock you out) and does NOT create any
# database or secret - those are separate, deliberate steps in the README.
set -euo pipefail

APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
[ "$(id -u)" -eq 0 ] || { echo "run as root (sudo)"; exit 1; }
. /etc/os-release; [ "${VERSION_ID:-}" = "24.04" ] || { echo "expected Ubuntu 24.04, found ${PRETTY_NAME:-unknown}"; exit 1; }

run() { echo "+ $*"; if [ "$APPLY" -eq 1 ]; then eval "$@"; fi; }
note() { echo; echo "== $*"; }
[ "$APPLY" -eq 1 ] || echo "DRY RUN (nothing will be changed). Re-run with --apply."

note "1. timezone and unattended security updates"
run "timedatectl set-timezone Asia/Kolkata"
run "apt-get update -y"
run "DEBIAN_FRONTEND=noninteractive apt-get install -y unattended-upgrades fail2ban ufw curl gnupg ca-certificates lsb-release software-properties-common libmagic1 pipx"
run "dpkg-reconfigure -f noninteractive unattended-upgrades"

note "2. 2 GB swap (the VPS has ~3.8 GB RAM and no swap)"
if [ ! -f /swapfile ] && [ -z "$(swapon --show --noheadings)" ]; then
  run "fallocate -l 2G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile"
  run "grep -q '^/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab"
  run "sysctl -w vm.swappiness=10 && echo 'vm.swappiness=10' > /etc/sysctl.d/99-fieldtrack-swap.conf"
else
  echo "swap already present - skipped"
fi

note "3. firewall: SSH, HTTP, HTTPS only (brute force is handled by fail2ban). Also open 80/443 in the OVHcloud panel firewall if one is enabled."
run "ufw default deny incoming && ufw default allow outgoing"
run "ufw allow 22/tcp"
run "ufw allow 80/tcp && ufw allow 443/tcp"
run "ufw --force enable"
run "systemctl enable --now fail2ban"

note "4. PostgreSQL 17 + PostGIS (PGDG repository; the project is developed and tested on PostgreSQL 17)"
run "install -d /usr/share/postgresql-common/pgdg"
run "curl -fsSL -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc https://www.postgresql.org/media/keys/ACCC4CF8.asc"
run "echo \"deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc] https://apt.postgresql.org/pub/repos/apt \$(lsb_release -cs)-pgdg main\" > /etc/apt/sources.list.d/pgdg.list"
run "apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y postgresql-17 postgresql-17-postgis-3"
run "systemctl enable --now postgresql"
echo "(PostgreSQL listens on localhost only by default - leave it that way; do not open 5432 in the firewall.)"

note "5. Python 3.11 (the version the test-suite runs on; Ubuntu 24.04 ships 3.12 which has NOT been tested with this project)"
run "add-apt-repository -y ppa:deadsnakes/ppa"
run "apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y python3.11 python3.11-venv python3.11-dev"

note "6. Caddy (reverse proxy + automatic HTTPS)"
# Official Caddy instructions. The published list file ALREADY contains [signed-by=...]; do not edit it (an earlier
# version of this script added a second signed-by with sed, which made apt reject the file: "Malformed entry ... (URI parse)").
run "DEBIAN_FRONTEND=noninteractive apt-get install -y debian-keyring debian-archive-keyring apt-transport-https curl"
run "curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/gpg.key | gpg --dearmor --yes -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg"
run "curl -1sLf https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt -o /etc/apt/sources.list.d/caddy-stable.list"
run "chmod o+r /usr/share/keyrings/caddy-stable-archive-keyring.gpg /etc/apt/sources.list.d/caddy-stable.list"
run "apt-get update -y && DEBIAN_FRONTEND=noninteractive apt-get install -y caddy"

note "7. service account and directories"
run "id fieldtrack >/dev/null 2>&1 || useradd --system --home-dir /opt/fieldtrack --shell /usr/sbin/nologin fieldtrack"
run "install -d -o root -g root -m 0755 /opt/fieldtrack /opt/fieldtrack/releases"
run "install -d -o root -g fieldtrack -m 0750 /etc/fieldtrack"
run "install -d -o fieldtrack -g fieldtrack -m 0750 /var/lib/fieldtrack /var/lib/fieldtrack/media"
run "install -d -o root -g root -m 0700 /var/backups/fieldtrack /root/.fieldtrack"

note "done"
echo "Next (manual): README steps 2-6. Before disabling SSH password login, confirm key-based login works from a SECOND terminal."
