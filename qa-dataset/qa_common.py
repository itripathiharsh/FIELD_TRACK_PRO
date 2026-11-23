"""Shared guards for the LOCAL QA dataset scripts. Every write path calls assert_local() first."""
import json
import os
import re
import sys
import urllib.error
import urllib.request

EXPECTED_DB = "fieldtrackpro_dev"
EXPECTED_HOSTS = ("127.0.0.1", "localhost")
EXPECTED_PORT = 5432
LOCAL_API = "http://127.0.0.1:8000/api/v1"          # same server the phone reaches at http://192.168.1.40:8000
LAN_HEALTH = "http://192.168.1.40:8000/health"
FORBIDDEN = ("51-79-158-138", "sslip.io", "onrender.com", "vercel.app")
BACKEND_DIR = r"F:\Field track pro v2 for test\field track pro\fieldtrackpro-backend"
SECRETS_DIR = r"C:\Users\Admin\FieldTrackPro-TestAccounts"
MANIFEST = os.path.join(os.path.dirname(os.path.abspath(__file__)), "qa_manifest.json")
TEST_EMPLOYEE_ID = "f85a9f4e-5072-4588-b845-b740ba0145da"
TEST_MOBILE = "9999999999"


def abort(msg: str):
    sys.exit("STOPPED: " + msg)


def db_url() -> str:
    env = open(os.path.join(BACKEND_DIR, ".env"), encoding="utf-8").read()
    url = re.search(r"^DATABASE_URL=(.+)$", env, re.M).group(1).strip().strip('"')
    return url.replace("postgresql+asyncpg://", "postgresql://")


def check_url(url: str):
    low = url.lower()
    if any(f in low for f in FORBIDDEN):
        abort("a production host appears in the connection string")
    m = re.match(r"postgresql://[^@]*@([^:/]+):?(\d+)?/([^?]+)", url)
    if not m:
        abort("cannot parse database URL")
    host, port, db = m.group(1), int(m.group(2) or 5432), m.group(3)
    if host not in EXPECTED_HOSTS or port != EXPECTED_PORT or db != EXPECTED_DB:
        abort(f"database is {host}:{port}/{db}, expected 127.0.0.1:5432/{EXPECTED_DB}")


async def assert_local(con):
    """Live check on an asyncpg connection, before every write."""
    r = await con.fetchrow("select current_database() db, inet_server_addr()::text a, inet_server_port() p")
    if r["db"] != EXPECTED_DB or not str(r["a"]).startswith("127.0.0.1") or r["p"] != EXPECTED_PORT:
        abort(f"live connection is {r['a']}:{r['p']}/{r['db']}")


def http(method, path, body=None, headers=None, base=LOCAL_API):
    if not base.startswith("http://127.0.0.1:8000"):
        abort("refusing a non-local API base")
    req = urllib.request.Request(base + path, method=method, data=json.dumps(body, default=str).encode() if body is not None else None)
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            raw = r.read()
            return r.status, (json.loads(raw) if raw else None), {k.lower(): v for k, v in r.headers.items()}
    except urllib.error.HTTPError as e:
        raw = e.read().decode(errors="replace")
        try:
            return e.code, json.loads(raw), {}
        except Exception:
            return e.code, raw[:600], {}


def backend_is_local_and_up():
    with urllib.request.urlopen(LAN_HEALTH, timeout=10) as r:
        if r.status != 200:
            abort("local backend health check failed")


def secret(file: str, key: str) -> str:
    text = open(os.path.join(SECRETS_DIR, file), encoding="utf-8").read()
    return re.search(rf"^{key}: (.+)$", text, re.M).group(1).strip()
