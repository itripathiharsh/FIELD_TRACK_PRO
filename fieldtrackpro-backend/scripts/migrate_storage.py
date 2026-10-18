"""
Copy every stored object referenced by the database from a SOURCE storage
provider to a DESTINATION provider (e.g. Render local disk -> S3/R2 bucket, or
bucket -> bucket), verifying SHA-256 after each copy.

Safety properties
  * DRY-RUN by default: nothing is written anywhere unless --execute is given.
  * NEVER deletes anything from the source.
  * Idempotent / resumable: an object already present at the destination with
    the right SHA-256 is skipped, so an interrupted run can simply be re-run.
  * Source and destination are configured ONLY from explicit SRC_* / DST_*
    environment variables (not the app's single global storage settings):

      SRC_STORAGE_PROVIDER / DST_STORAGE_PROVIDER   LOCAL | MINIO
      SRC_MEDIA_STORAGE_PATH / DST_MEDIA_STORAGE_PATH            (LOCAL)
      SRC_MINIO_ENDPOINT, SRC_MINIO_ACCESS_KEY, SRC_MINIO_SECRET_KEY,
      SRC_MINIO_BUCKET, SRC_MINIO_SECURE (true/false), SRC_MINIO_REGION   (MINIO)
      ...and the same set with the DST_ prefix.

  * The database (DATABASE_URL, read from the app settings/.env) is only READ,
    except for the optional --update-provider-column (outlet_proofs.storage_provider).
  * Output is counts only - no keys, URLs or credentials are printed. Keys of
    missing/mismatched objects go to the CSV report (--report).

Usage
  python scripts/migrate_storage.py                      # dry-run
  python scripts/migrate_storage.py --execute --report storage_report.csv
  python scripts/migrate_storage.py --execute --update-provider-column
"""
from __future__ import annotations

import argparse
import asyncio
import csv
import hashlib
import mimetypes
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable, Mapping

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

# (table, id column, storage-key column, sha256 column or None, storage_provider column or None)
STORAGE_COLUMNS: tuple[tuple[str, str, str, str | None, str | None], ...] = (
    ("outlet_proofs", "id", "storage_key", "checksum_sha256", "storage_provider"),
    ("visit_media", "id", "storage_key", "checksum_sha256", None),
    ("visit_signatures", "id", "storage_key", "checksum_sha256", None),
    ("payment_proofs", "id", "storage_key", "checksum_sha256", None),
    ("customer_requirements", "id", "photo_storage_key", None, None),
)

# Outcomes
COPIED = "copied"
WOULD_COPY = "would_copy"
ALREADY_PRESENT = "already_present"
MISSING_SOURCE = "missing_source"
SRC_CHECKSUM_MISMATCH = "source_checksum_mismatch"  # copied faithfully, but the row's checksum disagrees
VERIFY_MISMATCH = "verify_mismatch"  # destination bytes differ after copy
COPY_ERROR = "copy_error"
SKIPPED_PLACEHOLDER = "skipped_placeholder"
REPORTED = {MISSING_SOURCE, SRC_CHECKSUM_MISMATCH, VERIFY_MISMATCH, COPY_ERROR}


@dataclass(frozen=True)
class Ref:
    table: str
    row_id: str
    key: str
    sha256: str | None


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def build_provider(prefix: str, environ: Mapping[str, str] | None = None):
    """Build a storage provider purely from <prefix>_* variables (prefix is 'SRC' or 'DST')."""
    from app.services.storage.local_provider import LocalStorageProvider
    from app.services.storage.minio_provider import MinIOStorageProvider

    e = os.environ if environ is None else environ

    def get(name: str, default: str | None = None) -> str | None:
        return e.get(f"{prefix}_{name}", default)

    kind = (get("STORAGE_PROVIDER") or "").upper()
    if kind == "LOCAL":
        path = get("MEDIA_STORAGE_PATH")
        if not path:
            raise SystemExit(f"ERROR: {prefix}_MEDIA_STORAGE_PATH is required for {prefix}_STORAGE_PROVIDER=LOCAL")
        return LocalStorageProvider(base_dir=path)
    if kind == "MINIO":
        missing = [n for n in ("MINIO_ENDPOINT", "MINIO_ACCESS_KEY", "MINIO_SECRET_KEY", "MINIO_BUCKET") if not get(n)]
        if missing:
            raise SystemExit(f"ERROR: missing {', '.join(prefix + '_' + m for m in missing)}")
        return MinIOStorageProvider(
            endpoint=get("MINIO_ENDPOINT"),
            access_key=get("MINIO_ACCESS_KEY"),
            secret_key=get("MINIO_SECRET_KEY"),
            bucket_name=get("MINIO_BUCKET"),
            secure=(get("MINIO_SECURE", "true") or "").lower() in ("1", "true", "yes"),
            region=get("MINIO_REGION") or None,
        )
    raise SystemExit(f"ERROR: {prefix}_STORAGE_PROVIDER must be LOCAL or MINIO")


async def collect_references(session) -> list[Ref]:
    """Every storage key referenced by a DB row (tables that do not exist yet are skipped)."""
    from sqlalchemy import inspect as sa_inspect
    from sqlalchemy import text

    conn = await session.connection()
    existing = await conn.run_sync(lambda c: set(sa_inspect(c).get_table_names()))
    refs: list[Ref] = []
    for table, id_col, key_col, sha_col, _prov in STORAGE_COLUMNS:
        if table not in existing:
            continue
        cols = f"{id_col}, {key_col}" + (f", {sha_col}" if sha_col else ", NULL")
        rows = (await session.execute(text(f"SELECT {cols} FROM {table} WHERE {key_col} IS NOT NULL AND {key_col} <> ''"))).all()
        for rid, key, sha in rows:
            refs.append(Ref(table, str(rid), key, sha))
    return refs


async def _fetch(provider, key: str) -> bytes | None:
    """Bytes of an object, or None when it does not exist / can not be read."""
    try:
        if not await provider.exists(key):
            return None
        return await provider.download(key)
    except Exception:
        return None


async def migrate_objects(
    refs: Iterable[Ref],
    src,
    dst,
    *,
    execute: bool,
    limit: int | None = None,
) -> tuple[dict[str, int], list[tuple[Ref, str, str]], set[str]]:
    """
    Returns (counts, report_rows, verified_keys). `verified_keys` = keys now present and
    verified at the destination (candidates for --update-provider-column).
    """
    counts: dict[str, int] = {}
    report: list[tuple[Ref, str, str]] = []
    verified: set[str] = set()
    seen: dict[str, str] = {}  # key -> outcome of first reference
    processed = 0

    def bump(outcome: str) -> None:
        counts[outcome] = counts.get(outcome, 0) + 1

    for ref in refs:
        if ref.key in seen:
            # Same object referenced twice: count once, but still report the same problem for this row.
            if seen[ref.key] in REPORTED:
                report.append((ref, seen[ref.key], "same key as an earlier row"))
            continue
        if limit is not None and processed >= limit:
            break
        processed += 1

        if ref.key.startswith("deleted/"):  # account-deletion placeholders point at nothing
            seen[ref.key] = SKIPPED_PLACEHOLDER
            bump(SKIPPED_PLACEHOLDER)
            continue

        src_bytes = await _fetch(src, ref.key)
        if src_bytes is None:
            # Maybe an earlier (interrupted) run already moved it and the source is gone: that is fine.
            dst_existing = await _fetch(dst, ref.key)
            if dst_existing is not None and (ref.sha256 is None or sha256_hex(dst_existing) == ref.sha256):
                seen[ref.key] = ALREADY_PRESENT
                bump(ALREADY_PRESENT)
                verified.add(ref.key)
            else:
                seen[ref.key] = MISSING_SOURCE
                bump(MISSING_SOURCE)
                report.append((ref, MISSING_SOURCE, "object not found at source"))
            continue

        actual = sha256_hex(src_bytes)
        mismatch = ref.sha256 is not None and actual != ref.sha256

        dst_existing = await _fetch(dst, ref.key)
        if dst_existing is not None and sha256_hex(dst_existing) == actual:
            outcome = ALREADY_PRESENT
            verified.add(ref.key)
        elif not execute:
            outcome = WOULD_COPY
        else:
            try:
                ctype = mimetypes.guess_type(ref.key)[0] or "application/octet-stream"
                await dst.upload(src_bytes, ref.key, ctype)
                back = await _fetch(dst, ref.key)
                if back is None or sha256_hex(back) != actual:
                    outcome = VERIFY_MISMATCH
                    report.append((ref, VERIFY_MISMATCH, "destination bytes differ after copy"))
                else:
                    outcome = COPIED
                    verified.add(ref.key)
            except Exception as exc:
                outcome = COPY_ERROR
                report.append((ref, COPY_ERROR, type(exc).__name__))

        if mismatch and outcome in (COPIED, WOULD_COPY, ALREADY_PRESENT):
            report.append((ref, SRC_CHECKSUM_MISMATCH, "stored bytes do not match the row checksum"))
            bump(SRC_CHECKSUM_MISMATCH)
        seen[ref.key] = outcome if not mismatch else SRC_CHECKSUM_MISMATCH
        bump(outcome)

    return counts, report, verified


def write_report(path: str, report: list[tuple[Ref, str, str]]) -> None:
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.writer(fh)
        w.writerow(["table", "row_id", "storage_key", "outcome", "detail"])
        for ref, outcome, detail in report:
            w.writerow([ref.table, ref.row_id, ref.key, outcome, detail])


async def update_provider_column(session, verified_keys: set[str], dst_provider_name: str) -> int:
    """Set storage_provider on rows whose object is verified at the destination. Returns rows updated."""
    from sqlalchemy import text

    total = 0
    for table, _id, key_col, _sha, prov_col in STORAGE_COLUMNS:
        if not prov_col or not verified_keys:
            continue
        for key in verified_keys:
            res = await session.execute(
                text(f"UPDATE {table} SET {prov_col} = :p WHERE {key_col} = :k AND {prov_col} <> :p"),
                {"p": dst_provider_name, "k": key},
            )
            total += res.rowcount or 0
    await session.commit()
    return total


async def run(args, src=None, dst=None, session_factory=None) -> int:
    src = src or build_provider("SRC")
    dst = dst or build_provider("DST")
    if session_factory is None:
        from app.database import AsyncSessionLocal as session_factory  # noqa: N813

    async with session_factory() as session:
        refs = await collect_references(session)
        counts, report, verified = await migrate_objects(refs, src, dst, execute=args.execute, limit=args.limit)
        updated = 0
        if args.execute and args.update_provider_column:
            dst_name = (os.environ.get("DST_STORAGE_PROVIDER") or "").upper() or "MINIO"
            updated = await update_provider_column(session, verified, dst_name)

    mode = "EXECUTE" if args.execute else "DRY-RUN (nothing written; pass --execute to copy)"
    print(f"mode: {mode}")
    print(f"referenced objects (rows): {len(refs)}")
    for outcome in sorted(counts):
        print(f"{outcome}: {counts[outcome]}")
    if args.execute and args.update_provider_column:
        print(f"storage_provider rows updated: {updated}")
    if args.report:
        write_report(args.report, report)
        print(f"report rows written: {len(report)}")
    problems = sum(counts.get(o, 0) for o in (MISSING_SOURCE, VERIFY_MISMATCH, COPY_ERROR, SRC_CHECKSUM_MISMATCH))
    return 1 if problems else 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--execute", action="store_true", help="actually copy (default is a dry-run)")
    ap.add_argument("--report", help="CSV path for missing/mismatched objects")
    ap.add_argument("--limit", type=int, help="process at most N distinct objects (for a trial run)")
    ap.add_argument("--update-provider-column", action="store_true",
                    help="with --execute: set outlet_proofs.storage_provider to the DST provider for verified objects")
    args = ap.parse_args(argv)
    return asyncio.run(run(args))


if __name__ == "__main__":
    raise SystemExit(main())
