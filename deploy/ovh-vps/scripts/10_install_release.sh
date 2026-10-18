#!/usr/bin/env bash
# FieldTrack Pro - unpack a release tarball into /opt/fieldtrack/releases/<id>, build its virtualenv and (optionally) switch `current`.
#
#   sudo ./10_install_release.sh /tmp/fieldtrack-release-<id>.tar.gz [--switch]
#
# The tarball is made on your PC with `git archive` (see README step 3) and contains fieldtrackpro-backend/ and deploy/.
# Without --switch the new release is only installed (so you can run migrations/preflight against it first); with --switch the
# `current` symlink is moved to it. The previous release directory is kept for rollback. Secrets live in /etc/fieldtrack, never here.
set -euo pipefail

TARBALL="${1:-}"; SWITCH=0; [ "${2:-}" = "--switch" ] && SWITCH=1
[ -f "$TARBALL" ] || { echo "usage: $0 <release.tar.gz> [--switch]"; exit 2; }
[ "$(id -u)" -eq 0 ] || { echo "run as root"; exit 1; }

if [ -f "$TARBALL.sha256" ]; then (cd "$(dirname "$TARBALL")" && sha256sum -c "$(basename "$TARBALL").sha256"); else echo "WARNING: no .sha256 next to the tarball - integrity not checked"; fi

ID="$(basename "$TARBALL" .tar.gz | sed 's/^fieldtrack-release-//')"
DEST="/opt/fieldtrack/releases/$ID"
[ ! -e "$DEST" ] || { echo "$DEST already exists - refusing to overwrite a release"; exit 1; }
mkdir -p "$DEST"
tar -xzf "$TARBALL" -C "$DEST"
[ -f "$DEST/fieldtrackpro-backend/pyproject.toml" ] || { echo "tarball does not contain fieldtrackpro-backend/"; rm -rf "$DEST"; exit 1; }

# Poetry (installed once with: pipx install poetry). Build the venv INSIDE the release directory.
export PATH="$PATH:/root/.local/bin"
command -v poetry >/dev/null || { echo "poetry not found: run  pipx install poetry"; exit 1; }
cd "$DEST/fieldtrackpro-backend"
poetry config virtualenvs.in-project true --local
poetry env use python3.11
poetry install --only main --no-root --no-interaction

chown -R root:root "$DEST"
# Explicit modes, independent of the caller's umask: root owns and writes, everyone else (notably the unprivileged `fieldtrack`
# service user) can read and traverse. A restrictive umask (e.g. 077 from a detached/nohup wrapper) otherwise leaves the release
# root-only and the service cannot start. The release holds no secrets (those live in /etc/fieldtrack).
chmod -R u=rwX,go=rX "$DEST"
chmod 0755 "$DEST"/deploy/ovh-vps/scripts/*.sh || true
echo "installed release $ID at $DEST"

if [ "$SWITCH" -eq 1 ]; then
  PREV="$(readlink -f /opt/fieldtrack/current 2>/dev/null || true)"
  ln -sfn "$DEST" /opt/fieldtrack/current.new && mv -T /opt/fieldtrack/current.new /opt/fieldtrack/current
  echo "current -> $DEST   (previous: ${PREV:-none}; roll back with:  ln -sfn '${PREV:-<previous>}' /opt/fieldtrack/current && systemctl restart fieldtrack-backend)"
else
  echo "not switched. To run migrations/preflight against this release use:  cd $DEST/fieldtrackpro-backend  (see README step 5)"
fi
