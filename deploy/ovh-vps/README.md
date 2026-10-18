# FieldTrack Pro - OVH VPS deployment runbook

**Status: PREPARED, NOT EXECUTED.** Nothing in this folder has been run on the server. Every command below is for a person (or an
approved Claude session) to run, step by step, stopping at each checkpoint.

Target: Ubuntu 24.04 LTS, 3.8 GB RAM (no swap), 35 GB free disk, public IP `51.79.158.138`, user `ubuntu` with passwordless sudo.
Admin web app stays on **Vercel** for now. Backend + PostgreSQL/PostGIS run on the VPS.

```
Android app / Vercel admin app / Tally agent --HTTPS--> Caddy :443 --127.0.0.1:8000--> uvicorn (1 worker, systemd)
                                                                                          |--> PostgreSQL 17 + PostGIS (127.0.0.1:5432 only)
                                                                                          '--> /var/lib/fieldtrack/media (uploads)
```

## What was verified locally vs. what was not

| Verified on a pristine throw-away PostgreSQL 17 cluster with the real role/database names | NOT verifiable off-server (verify at the checkpoint) |
|---|---|
| `db/01_roles_and_database.sql` (creates roles + PostGIS database; refuses to run twice) | `apt` installs, PGDG / deadsnakes / Caddy repositories |
| `config/backend.env.template` passes the app's production validation (LOCAL storage + interim mock SMS/SMTP) | `systemd` units (syntax reviewed, not run) |
| `scripts/20_migrate.sh` pre-flight -> `alembic upgrade head` as the **non-superuser owner** -> `grant_runtime_role.sql` -> post-check | Caddy config and Let's Encrypt issuance |
| `scripts/30_bootstrap_admins.sh` (first admin + Super Admin; second run refused) | UFW / OVH panel firewall, fail2ban |
| API running as `fieldtrack_app` with `ENVIRONMENT=production`: `/health`, `/health/db`, docs hidden, full login/reset-password/role flow | `poetry install` on Python 3.11 on the VPS (lock file resolves: 87 packages; not installed) |
| `scripts/backup.sh` dump + media archive + retention; the dump restored into a new database with identical row counts | Python 3.12 (Ubuntu default) - **untested**, hence 3.11 from deadsnakes |

Two real bugs were found by this rehearsal and fixed before it was written up: a DB password containing `#` crashed the pre-flight
inspector (now robust, and DB passwords must be alphanumeric anyway), and a folder named `env/` was swallowed by the repo's `.gitignore`.

## Decisions you must make before step 4 (nothing here guesses them)

1. **API hostname.** No domain exists yet. Temporary: `51-79-158-138.sslip.io` (free wildcard DNS; Let's Encrypt works but sslip.io is a shared
   third-party domain with shared rate limits and is not something to depend on long term). Switching to a real domain later means changing
   Caddy, `VITE_API_BASE_URL` on Vercel, the Android `BASE_URL` and the Tally agent's `BACKEND_URL`.
2. **SMTP/SMS.** Not available. `ALLOW_MOCK_COMMUNICATIONS=true` is set in the template so the API can start; **OTP delivery then does not work** and the
   login page still says "a code was sent". Staff password recovery = an Admin clicks *Reset Password*. Remove the flag when real providers exist.
3. **Which data goes in.** The database is **fresh**. Loading genuine business data (30 staff, territories/areas, ~1,631 outlets, Tally invoices/payments) is a
   separate approved step - see "Loading real data" below. No test/dummy data is ever loaded.
4. **Off-server backups** (rclone remote or similar). `backup.sh` warns until one is configured.

## 0. Prepare the release package on your PC (no server access)

`deploy/` must be committed first (it is currently an uncommitted folder on the release branch).

```bash
cd "F:/Field track pro v2 for test/field track pro"
git status --short            # must be clean
REL=$(git rev-parse --short HEAD)
git archive --format=tar.gz -o "fieldtrack-release-$REL.tar.gz" HEAD fieldtrackpro-backend deploy
sha256sum "fieldtrack-release-$REL.tar.gz" > "fieldtrack-release-$REL.tar.gz.sha256"
# (no `git push` is involved; the server never needs GitHub access)
scp "fieldtrack-release-$REL.tar.gz" "fieldtrack-release-$REL.tar.gz.sha256" ubuntu@51.79.158.138:/tmp/
```

## 1. Base server setup  (checkpoint: SSH key login works from a SECOND terminal before you ever disable password login)

```bash
ssh ubuntu@51.79.158.138
sudo tar -xzf /tmp/fieldtrack-release-<REL>.tar.gz -C /tmp deploy
sudo bash /tmp/deploy/ovh-vps/scripts/00_base_setup.sh            # dry run: read it
sudo bash /tmp/deploy/ovh-vps/scripts/00_base_setup.sh --apply
```
Installs: swap (2 GB), UFW (22 rate-limited, 80, 443), fail2ban, unattended security upgrades, PostgreSQL 17 + PostGIS, Python 3.11, Caddy, libmagic,
the `fieldtrack` service user and directories. Also open **80 and 443 in the OVHcloud panel** if its firewall is enabled.
Check: `sudo ufw status`, `ss -tlnp` (only 22/80/443 public; 5432 and 8000 on 127.0.0.1), `free -h`, `psql --version`.
Optional afterwards: `pipx install poetry` (as root; used by step 3).

## 2. Secrets and database  (checkpoint: you can connect as both roles; nothing else yet)

```bash
sudo bash -c 'umask 077; openssl rand -hex 24 > /root/.fieldtrack/owner_db_pw; openssl rand -hex 24 > /root/.fieldtrack/app_db_pw'
sudo -u postgres psql -v ON_ERROR_STOP=1 \
     -v owner_pw="$(sudo cat /root/.fieldtrack/owner_db_pw)" -v app_pw="$(sudo cat /root/.fieldtrack/app_db_pw)" \
     -f /tmp/deploy/ovh-vps/db/01_roles_and_database.sql
# environment file: fill ONLY the <SET_*>/<GENERATE> placeholders; generate the three secrets on the server
sudo install -m 640 -o root -g fieldtrack /tmp/deploy/ovh-vps/config/backend.env.template /etc/fieldtrack/backend.env
sudo nano /etc/fieldtrack/backend.env
python3 -c "import secrets; print(secrets.token_urlsafe(48))"      # run three times: JWT_SECRET, MEDIA_SIGNING_SECRET, OTP_HMAC_SECRET
sudo grep -nE '<(SET|GENERATE)' /etc/fieldtrack/backend.env         # must print nothing (commented lines are fine)
```

## 3. Install the release

```bash
sudo bash /tmp/deploy/ovh-vps/scripts/10_install_release.sh /tmp/fieldtrack-release-<REL>.tar.gz            # installs, does not switch
```
Builds `/opt/fieldtrack/releases/<REL>/fieldtrackpro-backend/.venv` (Python 3.11, `poetry install --only main`).

## 4. Migrate the (empty) database  (checkpoint: pre-flight clean, then post-check shows revision b9c0d1e2f3a4, pending 0)

```bash
export RELEASE_DIR=/opt/fieldtrack/releases/<REL>
sudo -E bash $RELEASE_DIR/deploy/ovh-vps/scripts/20_migrate.sh            # read-only pre-flight; must say "matches nothing"
sudo -E bash $RELEASE_DIR/deploy/ovh-vps/scripts/20_migrate.sh --apply    # alembic (owner role) + runtime grants
```
The pre-flight is the guard against the demo-data purge migration (`k4l5m6n7o8p9`): on an empty database it runs harmlessly; on a populated one it previews
exactly what it would delete and **blocks** (exit 1). Never use `alembic stamp` to get around it.

## 5. First administrator and Super Admin

```bash
sudo -E bash $RELEASE_DIR/deploy/ovh-vps/scripts/30_bootstrap_admins.sh       # prompts; password is read silently, never stored
```

## 6. Start the API and the proxy  (checkpoint: HTTPS /health = UP, /api/v1/health/db = connected)

```bash
sudo ln -sfn $RELEASE_DIR /opt/fieldtrack/current
sudo cp /tmp/deploy/ovh-vps/systemd/fieldtrack-backend.service /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now fieldtrack-backend
journalctl -u fieldtrack-backend -n 40 --no-pager           # no tracebacks; "Application startup complete"
curl -s http://127.0.0.1:8000/health

sudo cp /tmp/deploy/ovh-vps/caddy/Caddyfile /etc/caddy/Caddyfile
sudo systemctl edit caddy      # add:  [Service]  Environment=API_HOST=51-79-158-138.sslip.io
sudo caddy validate --config /etc/caddy/Caddyfile && sudo systemctl restart caddy
curl -s https://51-79-158-138.sslip.io/health ; curl -s https://51-79-158-138.sslip.io/api/v1/health/db
```

## 7. Point the clients at it (each is a separate, reversible change)

* **Vercel (admin web):** set `VITE_API_BASE_URL=https://<API_HOST>/api/v1`, redeploy. The backend's `CORS_ALLOWED_ORIGINS` must equal the Vercel origin exactly.
* **Android:** the release `BASE_URL` is hard-coded in `app/build.gradle.kts` (currently Render). Change it, then build a signed release APK with the required
  inputs (keystore, `MAPLIBRE_TILE_URL`, `PRIVACY_POLICY_URL`, `DELETION_URL`, `google-services.json` or `ALLOW_NO_FCM=true`).
* **Tally sync agent** (later, on the Tally server): new `BACKEND_URL` and a new agent key.
* `.github/workflows/keep_alive.yml` pings Render/Vercel; it becomes noise after cut-over.

## 8. Backups

```bash
sudo cp /tmp/deploy/ovh-vps/systemd/fieldtrack-backup.{service,timer} /etc/systemd/system/
sudo systemctl daemon-reload && sudo systemctl enable --now fieldtrack-backup.timer
sudo systemctl start fieldtrack-backup.service && ls -la /var/backups/fieldtrack      # take one now
# Restore test (do it once, into a scratch database, never over the live one):
sudo -u postgres createdb restore_check && sudo -u postgres psql -d restore_check -c 'create extension postgis'
sudo -u postgres pg_restore -d restore_check --no-owner /var/backups/fieldtrack/db-<stamp>.dump && sudo -u postgres dropdb restore_check
```
**Off-server copy:** configure an rclone remote and set `Environment=BACKUP_RCLONE_REMOTE=<remote>:fieldtrack` in the backup service. Until then a disk loss loses everything.

## Loading real data (separate approval; not part of this runbook's commands)

The Excel/MIS import endpoints are permanently disabled by design; Tally sync is the source for customers, invoices and payments. Options, each needing its
own review before use on production: (a) the Tally sync agent for financial/customer data; (b) the env-driven operational scripts in
`fieldtrackpro-backend/scripts/` (`import_employees_from_csv.py`, `import_real_client_data.py`) for staff/territories/outlets - read them first, they were not exercised here;
(c) restoring a reviewed dump that contains **no** test data. Whatever is used: run `20_migrate.sh` pre-flight afterwards, and compare counts with the expected baseline
(30 staff `11001-11030`, 55 territories, 465 areas, ~1,631 outlets). Remember `AGENTS.md`: no `REP-*` / `emp_wb_*` / mock visits / `CURR-GPS-001` in production.

## Rollback

* **Code:** `sudo ln -sfn /opt/fieldtrack/releases/<previous> /opt/fieldtrack/current && sudo systemctl restart fieldtrack-backend` (previous releases are kept).
* **Database:** migrations here are forward-only for the data they add; restore from the last verified `db-*.dump` into a new database and switch `DATABASE_URL`. Take a dump
  (`backup.sh`) immediately before every `20_migrate.sh --apply` on a database that holds data.

## Security notes

* `/etc/fieldtrack/backend.env` is `root:fieldtrack 640`; never commit it. Rotate any secret that ever appears in a terminal log or chat.
* Treat the old hard-coded passwords and the Render database URL that existed in earlier commits/scripts as compromised; the VPS uses freshly generated ones only.
* After confirming key-based SSH: `PasswordAuthentication no` in `/etc/ssh/sshd_config.d/`, `PermitRootLogin no`, then `sudo systemctl reload ssh`.
* Single uvicorn worker is mandatory (in-process scheduler without locking).
