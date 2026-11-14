"""
READ-ONLY: compare a Tally full-extraction GUID manifest (agent `sync --full`,
file `full_extraction_<ts>_guids.json`) with the database.

Lists, per entity, how many Tally-sourced records the database holds that the real
Tally company does NOT contain (test / deleted / stale vouchers), and how many Tally
records the database does not have yet. Nothing is changed: the session is a READ
ONLY transaction and the script refuses to run otherwise.

    CHECK_DATABASE_URL='<postgresql url>' python scripts/compare_tally_guid_manifest.py <manifest.json> [--list]

`--list` prints the database-only record ids (UUIDs + Tally GUIDs; no names or amounts)
for review. Exit codes: 0 = database matches Tally, 1 = differences found, 2 = could not run.
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

QUERIES = {
    "invoices": "SELECT id::text, source_reference FROM invoices WHERE source = 'TALLY'",
    "payments": "SELECT id::text, source_reference FROM payments WHERE source = 'TALLY'",
    "customers": "SELECT id::text, tally_guid FROM customers WHERE tally_guid IS NOT NULL",
}


def compare(manifest: dict, db_rows: dict[str, list[tuple[str, str | None]]]) -> dict:
    out = {}
    for entity, rows in db_rows.items():
        tally = set(manifest.get(entity, []))
        db_refs = {ref for _, ref in rows if ref}
        out[entity] = {
            "tally_count": len(tally),
            "database_count": len(rows),
            "database_without_reference": [rid for rid, ref in rows if not ref],
            "database_not_in_tally": sorted((rid, ref) for rid, ref in rows if ref and ref not in tally),
            "tally_not_in_database": len(tally - db_refs),
        }
    return out


def main(argv: list[str]) -> int:
    if not argv or argv[0].startswith("-"):
        print(__doc__)
        return 2
    manifest = json.loads(Path(argv[0]).read_text(encoding="utf-8"))
    show = "--list" in argv

    from sqlalchemy import create_engine, text

    raw = os.environ.get("CHECK_DATABASE_URL")
    if not raw:
        from app.config import settings

        raw = settings.database_url
    engine = create_engine(raw.replace("postgresql+asyncpg://", "postgresql://"), connect_args={
        "connect_timeout": 10, "options": "-c default_transaction_read_only=on -c statement_timeout=60000"})
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        if conn.execute(text("SHOW transaction_read_only")).scalar() != "on":
            print("REFUSING: session is not read-only")
            return 2
        rows = {e: [tuple(r) for r in conn.execute(text(q)).all()] for e, q in QUERIES.items()}

    result = compare(manifest, rows)
    differences = 0
    print(f"Manifest generated {manifest.get('generated_at')} for company {manifest.get('company_guid')}")
    for entity, r in result.items():
        extra = len(r["database_not_in_tally"]) + len(r["database_without_reference"])
        differences += extra + r["tally_not_in_database"]
        print(f"  {entity:9s} tally={r['tally_count']:6d} database={r['database_count']:6d} "
              f"database_not_in_tally={len(r['database_not_in_tally'])} "
              f"without_reference={len(r['database_without_reference'])} "
              f"tally_not_in_database={r['tally_not_in_database']}")
        if show:
            for rid, ref in r["database_not_in_tally"]:
                print(f"      {entity} {rid} {ref}")
    return 1 if differences else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
