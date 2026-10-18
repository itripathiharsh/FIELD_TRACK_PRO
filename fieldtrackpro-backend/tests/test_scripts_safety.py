"""
Safety tests for operational scripts: no embedded credentials/DB URLs,
bootstrap_admin never resets an existing admin, purge is dry-run by default.
"""
from __future__ import annotations

import importlib
import re
import sys
import uuid
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.config import settings

BACKEND = Path(__file__).resolve().parents[1]
SCRIPTS = BACKEND / "scripts"


@pytest.fixture(autouse=True)
def _scripts_on_path():
    sys.path.insert(0, str(SCRIPTS))
    yield
    sys.path.remove(str(SCRIPTS))


def _load(name):
    sys.modules.pop(name, None)
    return importlib.import_module(name)


def test_no_hardcoded_credentials_or_db_urls_in_scripts_or_app():
    forbidden = [
        re.compile(r"AdminPass123|EmployeePass123|Imharsh|DEFAULT_TEMP_PASSWORD|Password@123|onrender.com"),
        re.compile(r"postgres(?:ql)?(?:\+\w+)?://[^\s\"'/@:]+:[^\s\"'@]+@(?!\{)"),
    ]
    offenders = []
    for root in (SCRIPTS, BACKEND / "app", BACKEND / "alembic"):
        for p in root.rglob("*.py"):
            text = p.read_text(encoding="utf-8", errors="ignore")
            for pat in forbidden:
                if pat.search(text):
                    offenders.append(f"{p.relative_to(BACKEND)}: {pat.pattern[:30]}")
    assert offenders == []


def test_seed_demo_data_removed_and_bootstrap_present():
    assert not (SCRIPTS / "seed_demo_data.py").exists()
    assert (SCRIPTS / "bootstrap_admin.py").exists()


# ---------------------------------------------------------------- bootstrap_admin

def test_bootstrap_refuses_production_without_flag(monkeypatch, capsys):
    mod = _load("bootstrap_admin")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "a-long-enough-password")
    with patch.object(settings, "environment", "production"), patch.object(mod, "bootstrap") as boot:
        assert mod.main([]) == 2
        boot.assert_not_called()
        assert mod.main(["--i-understand-production"]) == 0
        boot.assert_called_once()
    assert "a-long-enough-password" not in capsys.readouterr().out


def test_bootstrap_requires_env_and_strong_password(monkeypatch):
    mod = _load("bootstrap_admin")
    monkeypatch.delenv("ADMIN_BOOTSTRAP_EMAIL", raising=False)
    monkeypatch.delenv("ADMIN_BOOTSTRAP_PASSWORD", raising=False)
    assert mod.main([]) == 2
    monkeypatch.setenv("ADMIN_BOOTSTRAP_EMAIL", "boss@example.com")
    monkeypatch.setenv("ADMIN_BOOTSTRAP_PASSWORD", "short")
    assert mod.main([]) == 2


def test_bootstrap_never_resets_existing_user():
    from sqlalchemy import create_engine, text

    mod = _load("bootstrap_admin")
    email = f"a2_bootstrap_{uuid.uuid4().hex[:8]}@fieldtrack.test"
    engine = create_engine(settings.database_url.replace("postgresql+asyncpg://", "postgresql://"))
    try:
        assert mod.bootstrap(email, "FirstPassword-123456", engine) == "created"
        with engine.connect() as c:
            h1 = c.execute(text("SELECT password_hash FROM users WHERE email=:e"), {"e": email}).scalar()
        assert mod.bootstrap(email.upper(), "SecondPassword-654321", engine) == "exists"
        with engine.connect() as c:
            h2, role = c.execute(text("SELECT password_hash, role::text FROM users WHERE email=:e"), {"e": email}).one()
        assert h1 == h2 and role == "ADMIN"
    finally:
        with engine.begin() as c:
            c.execute(text("DELETE FROM users WHERE email=:e"), {"e": email})
        engine.dispose()


# ---------------------------------------------------------------- purge_all_test_data

@pytest.fixture
def purge_mod(monkeypatch):
    mod = _load("purge_all_test_data")
    conn = MagicMock()
    monkeypatch.setattr(mod.psycopg2, "connect", lambda *_a, **_k: conn)
    monkeypatch.setattr(mod, "purge", lambda cur: None)
    monkeypatch.delenv("CONFIRM_PURGE_DATABASE", raising=False)
    return mod, conn


def test_purge_defaults_to_dry_run_and_rolls_back(purge_mod):
    mod, conn = purge_mod
    assert mod.main([]) == 0
    conn.rollback.assert_called()
    conn.commit.assert_not_called()


def test_purge_execute_requires_database_name_confirmation(purge_mod, monkeypatch):
    mod, conn = purge_mod
    assert mod.main(["--execute"]) == 2
    monkeypatch.setenv("CONFIRM_PURGE_DATABASE", "some_other_db")
    assert mod.main(["--execute"]) == 2
    conn.commit.assert_not_called()
    from urllib.parse import urlparse

    db_name = urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://")).path.lstrip("/")
    monkeypatch.setenv("CONFIRM_PURGE_DATABASE", db_name)
    assert mod.main(["--execute"]) == 0
    conn.commit.assert_called_once()


def test_purge_refuses_production_without_flag(purge_mod, monkeypatch):
    mod, conn = purge_mod
    with patch.object(settings, "environment", "production"):
        assert mod.main([]) == 2
        assert mod.main(["--execute"]) == 2
    conn.commit.assert_not_called()


def test_purge_rolls_back_on_error(purge_mod, monkeypatch):
    mod, conn = purge_mod

    def boom(cur):
        raise RuntimeError("x")

    monkeypatch.setattr(mod, "purge", boom)
    from urllib.parse import urlparse

    monkeypatch.setenv(
        "CONFIRM_PURGE_DATABASE",
        urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://")).path.lstrip("/"),
    )
    assert mod.main(["--execute"]) == 1
    conn.commit.assert_not_called()


def test_script_env_helpers(monkeypatch):
    mod = _load("_script_env")
    assert mod.random_password() != mod.random_password()
    monkeypatch.delenv("SOME_MISSING_VAR_A2", raising=False)
    with pytest.raises(SystemExit):
        mod.env("SOME_MISSING_VAR_A2")


# ---------------------------------------------------------------- verify_production_readiness / render.yaml

class _FakeSettings:
    environment = "production"
    storage_provider = "MINIO"
    sms_provider = "msg91"
    model_fields_set = {
        "environment", "database_url", "jwt_secret", "media_signing_secret", "cors_allowed_origins",
        "storage_provider", "sms_provider", "smtp_host", "minio_endpoint", "minio_access_key",
        "minio_secret_key", "minio_bucket",
    }


def _fake_exec(overrides=None):
    answers = {
        "alembic_version": [("HEAD1",)],
        "pg_enum": [("ADMIN",), ("EMPLOYEE",)],
        "@fieldtrack.test": [(0,)],
        "REP-": [(0,)],
        "CURR-GPS-001": [(0,)],
        "FROM employees WHERE employee_code ~": [(30,)],
        "SELECT count(*) FROM employees": [(30,)],
        "SELECT count(*) FROM customers": [(1650,)],
        "territories": [(55,)],
        "areas": [(465,)],
    }
    answers.update(overrides or {})

    def run(sql, params=None):
        for key, val in answers.items():
            if key in sql:
                return val
        raise AssertionError(f"unexpected SQL: {sql}")

    return run


def test_readiness_all_pass_for_clean_production_shape(capsys):
    mod = _load("verify_production_readiness")
    report = mod.run_checks(_FakeSettings(), _fake_exec(), "HEAD1")
    out = capsys.readouterr().out
    assert report.failed == 0 and "FAIL" not in out


def test_readiness_flags_test_data_wrong_counts_local_storage_and_drift(capsys):
    mod = _load("verify_production_readiness")

    class S(_FakeSettings):
        storage_provider = "LOCAL"
        environment = "dev"

    report = mod.run_checks(
        S(),
        _fake_exec({"@fieldtrack.test": [(3,)], "territories": [(9,)], "pg_enum": [("ADMIN",), ("EMPLOYEE",), ("MANAGER",)]}),
        "HEAD2",
    )
    out = capsys.readouterr().out
    assert report.failed >= 6
    for needle in ("ENVIRONMENT", "test users", "territories", "role_enum", "alembic current", "storage provider"):
        assert any(needle in line and "FAIL" in line for line in out.splitlines()), needle


def test_readiness_never_prints_secret_values(capsys, monkeypatch):
    mod = _load("verify_production_readiness")
    monkeypatch.setenv("JWT_SECRET", "SUPERSECRETVALUE-123")
    mod.run_checks(_FakeSettings(), _fake_exec(), "HEAD1")
    assert "SUPERSECRETVALUE" not in capsys.readouterr().out


def test_render_yaml_is_safe_for_production():
    import yaml

    render = yaml.safe_load((BACKEND.parent / "render.yaml").read_text(encoding="utf-8"))
    svc = render["services"][0]
    assert "seed_demo_data" not in svc["startCommand"] and "alembic upgrade head" in svc["startCommand"]
    env = {e["key"]: e for e in svc["envVars"]}
    assert env["ENVIRONMENT"]["value"] == "production"
    assert env["STORAGE_PROVIDER"]["value"] == "MINIO"
    for k in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET", "MINIO_SECURE",
              "SMS_PROVIDER", "SMS_API_KEY", "SMTP_HOST", "SMTP_USER", "SMTP_PASSWORD", "CORS_ALLOWED_ORIGINS"):
        assert env[k].get("sync") is False and "value" not in env[k], k
    for k in ("JWT_SECRET", "MEDIA_SIGNING_SECRET"):
        assert env[k].get("generateValue") is True
    assert "vercel" not in str(env["CORS_ALLOWED_ORIGINS"]) and "localhost" not in str(env["CORS_ALLOWED_ORIGINS"])


# ---------------------------------------------------------------- hardening batch additions

def test_no_live_hostnames_baked_into_scripts():
    """Scripts read SCRIPT_API_URL / SCRIPT_FRONTEND_URL from the environment instead."""
    offenders = []
    for p in SCRIPTS.glob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if re.search(r"onrender\.com|fieldtrack-pro[\w-]*\.vercel\.app", text):
            offenders.append(p.name)
    assert offenders == []


def test_every_bulk_writing_script_is_gated():
    """Any script that DELETEs/TRUNCATEs/bulk-UPDATEs must be dry-run-by-default (--execute + confirmation)."""
    bulk = re.compile(r"DELETE FROM|TRUNCATE|DROP TABLE|UPDATE\s+[a-z_]+\s+SET", re.IGNORECASE)
    gates = ("--execute", "destructive_script_main", "guard_write_script", "CONFIRM_RESET_ALL_PASSWORDS")
    ungated = []
    for p in SCRIPTS.glob("*.py"):
        text = p.read_text(encoding="utf-8", errors="ignore")
        if bulk.search(text) and not any(g in text for g in gates):
            ungated.append(p.name)
    assert ungated == []


def test_guard_write_script_is_dry_run_by_default_and_requires_confirmation(monkeypatch, capsys):
    mod = _load("_script_env")
    monkeypatch.delenv("CONFIRM_PURGE_DATABASE", raising=False)
    with pytest.raises(SystemExit) as dry:
        mod.guard_write_script("demo", [])
    assert dry.value.code == 0 and "DRY-RUN" in capsys.readouterr().out
    with pytest.raises(SystemExit) as refused:
        mod.guard_write_script("demo", ["--execute"])
    assert "CONFIRM_PURGE_DATABASE" in str(refused.value.code)
    from urllib.parse import urlparse

    db_name = urlparse(settings.database_url.replace("postgresql+asyncpg://", "postgresql://")).path.lstrip("/")
    monkeypatch.setenv("CONFIRM_PURGE_DATABASE", db_name)
    assert mod.guard_write_script("demo", ["--execute"]) is None  # allowed
    with patch.object(settings, "environment", "production"):
        with pytest.raises(SystemExit) as prod:
            mod.guard_write_script("demo", ["--execute"])
        assert "i-understand-production" in str(prod.value.code)


def test_script_env_requires_api_url_from_environment(monkeypatch):
    mod = _load("_script_env")
    monkeypatch.delenv("SCRIPT_API_URL", raising=False)
    with pytest.raises(SystemExit):
        mod.api_url()
    monkeypatch.setenv("SCRIPT_API_URL", "https://api.example.test/")
    assert mod.api_url() == "https://api.example.test"


def test_grant_runtime_role_sql_is_idempotent_and_protects_the_audit_table():
    sql = (SCRIPTS / "grant_runtime_role.sql").read_text(encoding="utf-8")
    assert "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO fieldtrack_app" in sql
    assert "USAGE, SELECT ON ALL SEQUENCES" in sql
    assert "REVOKE UPDATE, DELETE, TRUNCATE ON TABLE geo_verification_logs FROM fieldtrack_app" in sql
    assert "ALTER DEFAULT PRIVILEGES FOR ROLE" in sql
    assert "CREATE TABLE" not in sql.upper()  # grants only


def test_purge_payment_selection_only_matches_test_markers():
    """The old filter (`source='MANUAL' OR visit_id IS NOT NULL`) would delete every real field collection."""
    import psycopg2

    mod = _load("purge_all_test_data")
    assert "source = 'MANUAL'" not in Path(mod.__file__).read_text(encoding="utf-8")

    tag = uuid.uuid4().hex[:8]
    ids = {k: str(uuid.uuid4()) for k in ("u_real", "u_test", "e_real", "e_test", "c_real", "c_test", "p1", "p2", "p3", "p4")}
    dsn = settings.database_url.replace("postgresql+asyncpg://", "postgresql://")
    conn = psycopg2.connect(dsn)
    conn.autocommit = True
    cur = conn.cursor()
    try:
        for uid, email in ((ids["u_real"], f"real.{tag}@sgrgservices.com"), (ids["u_test"], f"emp_wb_{tag}@fieldtrack.test")):
            cur.execute(
                "INSERT INTO users (id,email,password_hash,role,is_active,created_at,updated_at) "
                "VALUES (%s,%s,'x','EMPLOYEE',true,now(),now())",
                (uid, email),
            )
        cur.execute(
            "INSERT INTO employees (id,user_id,full_name,employee_code,created_at) VALUES (%s,%s,'Real Rep',%s,now())",
            (ids["e_real"], ids["u_real"], f"110{int(tag[:2], 16) % 90 + 10}"),
        )
        cur.execute(
            "INSERT INTO employees (id,user_id,full_name,employee_code,created_at) VALUES (%s,%s,'Test Rep',%s,now())",
            (ids["e_test"], ids["u_test"], f"REP-{tag}"),
        )
        for cid, name, code in ((ids["c_real"], f"Real Outlet {tag}", f"UPDD{tag}"), (ids["c_test"], f"__itest__Outlet {tag}", f"ITEST{tag}")):
            cur.execute(
                "INSERT INTO customers (id,name,outlet_code,contact_number,address,geofence_radius_m,created_by,created_at,updated_at) "
                "VALUES (%s,%s,%s,'+919800000000','addr',100,%s,now(),now())",
                (cid, name, code, ids["u_real"]),
            )
        pay = lambda pid, cust, emp: cur.execute(  # noqa: E731
            "INSERT INTO payments (id,customer_id,employee_id,amount,payment_method,payment_date,created_by,created_at,updated_at) "
            "VALUES (%s,%s,%s,100,'CASH',current_date,%s,now(),now())",
            (pid, cust, emp, ids["u_real"]),
        )
        pay(ids["p1"], ids["c_real"], ids["e_real"])  # real rep on real outlet -> MUST be kept
        pay(ids["p2"], ids["c_real"], ids["e_test"])  # test rep
        pay(ids["p3"], ids["c_test"], ids["e_real"])  # test outlet
        pay(ids["p4"], ids["c_test"], ids["e_test"])
        cur.execute(mod.TEST_PAYMENT_IDS_SQL)
        selected = {str(r[0]) for r in cur.fetchall()} & {ids["p1"], ids["p2"], ids["p3"], ids["p4"]}
        assert selected == {ids["p2"], ids["p3"], ids["p4"]}
    finally:
        cur.execute("DELETE FROM payments WHERE id = ANY(%s::uuid[])", ([ids[k] for k in ("p1", "p2", "p3", "p4")],))
        cur.execute("DELETE FROM customers WHERE id = ANY(%s::uuid[])", ([ids["c_real"], ids["c_test"]],))
        cur.execute("DELETE FROM employees WHERE id = ANY(%s::uuid[])", ([ids["e_real"], ids["e_test"]],))
        cur.execute("DELETE FROM users WHERE id = ANY(%s::uuid[])", ([ids["u_real"], ids["u_test"]],))
        conn.close()
