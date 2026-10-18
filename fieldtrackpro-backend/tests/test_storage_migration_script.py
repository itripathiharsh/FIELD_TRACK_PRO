"""scripts/migrate_storage.py: dry-run default, copy+verify, resume, reports, provider column, no secrets."""
from __future__ import annotations

import csv
import hashlib
import io
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.services.storage.local_provider import LocalStorageProvider
from app.services.storage.minio_provider import MinIOStorageProvider

SCRIPTS = Path(__file__).resolve().parents[1] / "scripts"


@pytest.fixture
def ms():
    sys.path.insert(0, str(SCRIPTS))
    sys.modules.pop("migrate_storage", None)
    import migrate_storage

    yield migrate_storage
    sys.path.remove(str(SCRIPTS))


class FakeMinio:
    """Minimal in-memory stand-in for the minio client used by MinIOStorageProvider."""

    def __init__(self):
        self.objects: dict[str, tuple[bytes, str]] = {}

    def put_object(self, bucket_name, object_name, data, length, content_type):
        self.objects[object_name] = (data.read(), content_type)

    def get_object(self, bucket, key):
        if key not in self.objects:
            raise RuntimeError("NoSuchKey")
        buf = io.BytesIO(self.objects[key][0])

        class R:
            def read(self_inner):
                return buf.read()

            def close(self_inner):
                pass

            def release_conn(self_inner):
                pass

        return R()

    def stat_object(self, bucket, key):
        if key not in self.objects:
            raise RuntimeError("NoSuchKey")
        return object()


def fake_minio_provider() -> tuple[MinIOStorageProvider, FakeMinio]:
    fake = FakeMinio()
    p = MinIOStorageProvider("s3.example.com", "AK", "SK", "bucket", True)
    p._client = fake
    return p, fake


def sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


async def seed(provider, items: dict[str, bytes]):
    for k, v in items.items():
        await provider.upload(v, k, "image/jpeg")


def refs_for(ms, items: dict[str, bytes], table="visit_media", with_sha=True):
    return [ms.Ref(table, str(uuid.uuid4()), k, sha(v) if with_sha else None) for k, v in items.items()]


@pytest.mark.asyncio
async def test_dry_run_writes_nothing_then_execute_copies_and_verifies(ms, tmp_path):
    src, dst = LocalStorageProvider(str(tmp_path / "src")), LocalStorageProvider(str(tmp_path / "dst"))
    items = {"visits/1/a.jpg": b"aaa", "outlet-proofs/2026/b.jpg": b"bbbb", "payments/c.jpg": b"c" * 100}
    await seed(src, items)
    refs = refs_for(ms, items)

    counts, report, verified = await ms.migrate_objects(refs, src, dst, execute=False)
    assert counts == {ms.WOULD_COPY: 3} and report == [] and verified == set()
    assert not any((tmp_path / "dst").rglob("*.jpg"))

    counts, report, verified = await ms.migrate_objects(refs, src, dst, execute=True)
    assert counts == {ms.COPIED: 3} and report == [] and verified == set(items)
    for k, v in items.items():
        assert await dst.download(k) == v
        assert await src.download(k) == v  # source never deleted


@pytest.mark.asyncio
async def test_resume_skips_already_copied(ms, tmp_path):
    src, dst = LocalStorageProvider(str(tmp_path / "s")), LocalStorageProvider(str(tmp_path / "d"))
    items = {"a.jpg": b"1", "b.jpg": b"2", "c.jpg": b"3"}
    await seed(src, items)
    refs = refs_for(ms, items)
    counts, *_ = await ms.migrate_objects(refs, src, dst, execute=True, limit=2)
    assert counts == {ms.COPIED: 2}
    counts, _, verified = await ms.migrate_objects(refs, src, dst, execute=True)
    assert counts == {ms.ALREADY_PRESENT: 2, ms.COPIED: 1} and verified == set(items)


@pytest.mark.asyncio
async def test_missing_and_checksum_mismatch_reported_and_csv(ms, tmp_path):
    src, dst = LocalStorageProvider(str(tmp_path / "s")), LocalStorageProvider(str(tmp_path / "d"))
    await seed(src, {"ok.jpg": b"ok", "bad.jpg": b"corrupted-on-disk"})
    refs = [
        ms.Ref("visit_media", "1", "ok.jpg", sha(b"ok")),
        ms.Ref("visit_media", "2", "gone.jpg", sha(b"x")),
        ms.Ref("payment_proofs", "3", "bad.jpg", sha(b"what-the-db-expects")),
        ms.Ref("customer_requirements", "4", "ok.jpg", None),  # same object referenced twice
        ms.Ref("visit_signatures", "5", "deleted/visit_signature/abc", None),
    ]
    counts, report, verified = await ms.migrate_objects(refs, src, dst, execute=True)
    assert counts[ms.MISSING_SOURCE] == 1 and counts[ms.SRC_CHECKSUM_MISMATCH] == 1
    assert counts[ms.SKIPPED_PLACEHOLDER] == 1 and counts[ms.COPIED] == 2
    assert {r[1] for r in report} == {ms.MISSING_SOURCE, ms.SRC_CHECKSUM_MISMATCH}
    path = tmp_path / "r.csv"
    ms.write_report(str(path), report)
    rows = list(csv.DictReader(open(path, encoding="utf-8")))
    assert {r["storage_key"] for r in rows} == {"gone.jpg", "bad.jpg"}
    assert await dst.download("bad.jpg") == b"corrupted-on-disk"  # copied faithfully, flagged


@pytest.mark.asyncio
async def test_verify_mismatch_detected(ms, tmp_path):
    src = LocalStorageProvider(str(tmp_path / "s"))
    await seed(src, {"k.jpg": b"payload"})

    class CorruptingDst(LocalStorageProvider):
        async def upload(self, file_bytes, storage_key, content_type):
            return await super().upload(file_bytes[:-1] + b"X", storage_key, content_type)

    dst = CorruptingDst(str(tmp_path / "d"))
    counts, report, verified = await ms.migrate_objects(refs_for(ms, {"k.jpg": b"payload"}), src, dst, execute=True)
    assert counts == {ms.VERIFY_MISMATCH: 1} and verified == set() and report[0][1] == ms.VERIFY_MISMATCH


@pytest.mark.asyncio
async def test_local_to_fake_minio_and_back(ms, tmp_path):
    local = LocalStorageProvider(str(tmp_path / "l"))
    minio, fake = fake_minio_provider()
    items = {"outlet-proofs/2026/x.jpg": b"img-bytes", "visits/9/y.png": b"\x89PNG-ish"}
    await seed(local, items)
    counts, _, _ = await ms.migrate_objects(refs_for(ms, items), local, minio, execute=True)
    assert counts == {ms.COPIED: 2}
    assert fake.objects["visits/9/y.png"][1] == "image/png"
    local2 = LocalStorageProvider(str(tmp_path / "l2"))
    counts, _, _ = await ms.migrate_objects(refs_for(ms, items), minio, local2, execute=True)
    assert counts == {ms.COPIED: 2}
    assert await local2.download("outlet-proofs/2026/x.jpg") == b"img-bytes"
    # destination already complete -> resume is a no-op
    counts, _, _ = await ms.migrate_objects(refs_for(ms, items), local, minio, execute=True)
    assert counts == {ms.ALREADY_PRESENT: 2}


def test_build_provider_from_prefixed_env_only(ms, tmp_path):
    env = {"SRC_STORAGE_PROVIDER": "LOCAL", "SRC_MEDIA_STORAGE_PATH": str(tmp_path / "s"),
           "DST_STORAGE_PROVIDER": "MINIO", "DST_MINIO_ENDPOINT": "x.r2.cloudflarestorage.com",
           "DST_MINIO_ACCESS_KEY": "AK", "DST_MINIO_SECRET_KEY": "SK", "DST_MINIO_BUCKET": "b",
           "DST_MINIO_REGION": "auto",
           "STORAGE_PROVIDER": "MINIO", "MINIO_BUCKET": "global-should-be-ignored"}
    assert isinstance(ms.build_provider("SRC", env), LocalStorageProvider)
    d = ms.build_provider("DST", env)
    assert isinstance(d, MinIOStorageProvider) and d.bucket_name == "b" and d.region == "auto" and d.secure is True
    with pytest.raises(SystemExit):
        ms.build_provider("DST", {"DST_STORAGE_PROVIDER": "MINIO"})
    with pytest.raises(SystemExit):
        ms.build_provider("SRC", {})


def test_storage_columns_cover_every_model_storage_key_column(ms):
    import app.models  # noqa: F401  (register all tables)
    from app.database import Base

    declared = {(t, k) for t, _i, k, _s, _p in ms.STORAGE_COLUMNS}
    found = {
        (t.name, c.name)
        for t in Base.metadata.tables.values()
        for c in t.columns
        if "storage_key" in c.name
    }
    assert found == declared, f"update STORAGE_COLUMNS: missing={found - declared} stale={declared - found}"
    for t, id_col, key_col, sha_col, prov_col in ms.STORAGE_COLUMNS:
        cols = Base.metadata.tables[t].columns
        assert id_col in cols and key_col in cols
        assert sha_col is None or sha_col in cols
        assert prov_col is None or prov_col in cols


@pytest.mark.asyncio
async def test_run_against_db_prints_counts_only_and_updates_provider_column(ms, tmp_path, capsys, monkeypatch):
    from sqlalchemy import delete, select

    from app.core.security import hash_password
    from app.database import AsyncSessionLocal
    from app.models.customer import Customer
    from app.models.outlet_proof import OutletProof
    from app.models.user import Role, User
    from tests.conftest import IS_DB_MIGRATED

    if not IS_DB_MIGRATED:
        pytest.skip("requires migrated DB")

    tag = uuid.uuid4().hex[:8]
    key = f"outlet-proofs/test/{tag}.jpg"
    data = b"proof-bytes-" + tag.encode()
    src, dst = LocalStorageProvider(str(tmp_path / "s")), LocalStorageProvider(str(tmp_path / "d"))
    await src.upload(data, key, "image/jpeg")
    async with AsyncSessionLocal() as s:
        u = User(email=f"ms_{tag}@fieldtrack.test", password_hash=hash_password("x"), role=Role.ADMIN, is_active=True)
        s.add(u)
        await s.flush()
        c = Customer(name=f"MS {tag}", contact_number="9" + str(int(tag, 16))[:9], address="x", created_by=u.id)
        s.add(c)
        await s.flush()
        pid = uuid.uuid4()
        s.add(OutletProof(
            id=pid, customer_id=c.id, kind="INITIAL", status="PENDING", storage_key=key, storage_provider="LOCAL",
            content_type="image/jpeg", size_bytes=len(data), checksum_sha256=hashlib.sha256(data).hexdigest(),
            latitude=28.6, longitude=77.2, accuracy_m=5, captured_at=datetime.now(timezone.utc), submitted_by=u.id,
        ))
        await s.commit()
        uid, cid = u.id, c.id
    try:
        monkeypatch.setenv("DST_STORAGE_PROVIDER", "MINIO")
        args = type("A", (), dict(execute=False, report=str(tmp_path / "rep.csv"), limit=None, update_provider_column=True))()
        assert await ms.run(args, src=src, dst=dst) in (0, 1)  # other rows in a shared DB may be missing objects
        out = capsys.readouterr().out
        assert "DRY-RUN" in out and f"{ms.WOULD_COPY}: " in out and key not in out
        assert not await dst.exists(key)

        args.execute = True
        await ms.run(args, src=src, dst=dst)
        out = capsys.readouterr().out
        assert "storage_provider rows updated: 1" in out and key not in out
        assert await dst.download(key) == data
        async with AsyncSessionLocal() as s:
            row = (await s.execute(select(OutletProof).where(OutletProof.id == pid))).scalar_one()
            assert row.storage_provider == "MINIO"

        # object vanishes from both sides -> reported in the CSV
        (tmp_path / "s" / key).unlink()
        (tmp_path / "d" / key).unlink()
        args.update_provider_column = False
        assert await ms.run(args, src=src, dst=dst) == 1
        rows = list(csv.DictReader(open(tmp_path / "rep.csv", encoding="utf-8")))
        assert any(r["storage_key"] == key and r["outcome"] == ms.MISSING_SOURCE for r in rows)
    finally:
        async with AsyncSessionLocal() as s:
            await s.execute(delete(OutletProof).where(OutletProof.customer_id == cid))
            await s.execute(delete(Customer).where(Customer.id == cid))
            await s.execute(delete(User).where(User.id == uid))
            await s.commit()
