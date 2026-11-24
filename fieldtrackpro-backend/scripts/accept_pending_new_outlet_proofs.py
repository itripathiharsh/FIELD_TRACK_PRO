"""Release 3.3 one-off: apply the first-location auto-accept rule to new-outlet proofs that are still PENDING.

Before 3.3 the photo + GPS sent with a NEW-outlet request stayed PENDING in the Outlet Verification queue, although
the agreed rule is that a first submission is accepted automatically. This script re-checks every such proof against
the live-capture rules using what was stored at upload, and accepts only the ones that pass. It never touches a proof
of an existing outlet, a CHANGE_REQUEST, an UNATTACHED proof, or a proof whose request was already decided.

    python scripts/accept_pending_new_outlet_proofs.py            # dry run: report only
    python scripts/accept_pending_new_outlet_proofs.py --execute  # apply (prints and logs every decision)

Accepting = status APPROVED, auto_accepted = true, reviewed_by NULL (system), reviewed_at = now. The new-outlet
request itself stays PENDING for the admin. Nothing is deleted.
"""
from __future__ import annotations

import argparse
import asyncio
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal  # noqa: E402
from app.models.customer_prospect import CustomerProspect  # noqa: E402
from app.models.outlet_proof import OutletProof  # noqa: E402
from app.services.outlet_proof_service import INDIA_LAT_MAX, INDIA_LAT_MIN, INDIA_LON_MAX, INDIA_LON_MIN  # noqa: E402


def check(p: OutletProof) -> list[str]:
    """Reasons the stored capture would fail the live-capture rules ([] = passes)."""
    bad = []
    if p.is_mock_location:
        bad.append("mock location")
    if p.accuracy_m is None or p.accuracy_m > settings.outlet_proof_max_accuracy_m:
        bad.append(f"accuracy {p.accuracy_m} m > {settings.outlet_proof_max_accuracy_m:g} m")
    if p.latitude is None or p.longitude is None or not (
            INDIA_LAT_MIN <= p.latitude <= INDIA_LAT_MAX and INDIA_LON_MIN <= p.longitude <= INDIA_LON_MAX):
        bad.append("location missing or outside India")
    if p.captured_at and p.received_at:
        age = (p.received_at - p.captured_at).total_seconds()
        if age > settings.outlet_proof_max_age_seconds or age < -settings.outlet_proof_future_tolerance_seconds:
            bad.append(f"capture age {age:.0f}s outside the live window")
    if not p.storage_key or not p.size_bytes:
        bad.append("no stored photo")
    return bad


async def main(execute: bool) -> int:
    if not settings.outlet_proof_first_location_auto_accept:
        print("outlet_proof_first_location_auto_accept is OFF: nothing to do")
        return 0
    now = datetime.now(timezone.utc)
    decisions = []
    async with AsyncSessionLocal() as s:
        rows = (await s.execute(
            select(OutletProof, CustomerProspect.name, CustomerProspect.status)
            .join(CustomerProspect, CustomerProspect.id == OutletProof.prospect_id)
            .where(OutletProof.status == "PENDING", OutletProof.kind == "INITIAL",
                   OutletProof.customer_id.is_(None), OutletProof.prospect_id.is_not(None))
            .order_by(OutletProof.received_at)
        )).all()
        for p, name, pstatus in rows:
            pst = pstatus.value if hasattr(pstatus, "value") else str(pstatus)
            reasons = check(p) if pst == "PENDING" else [f"request already {pst}"]
            d = {"proof_id": str(p.id), "outlet_request": name, "request_status": pst,
                 "accuracy_m": p.accuracy_m, "captured_at": p.captured_at.isoformat() if p.captured_at else None,
                 "decision": "ACCEPT" if not reasons else "LEAVE PENDING", "reasons": reasons}
            decisions.append(d)
            if execute and not reasons:
                p.status, p.auto_accepted, p.reviewed_by, p.reviewed_at = "APPROVED", True, None, now
        if execute:
            await s.commit()
    for d in decisions:
        print(json.dumps(d, ensure_ascii=False))
    print(f"{'APPLIED' if execute else 'DRY RUN'}: {sum(d['decision'] == 'ACCEPT' for d in decisions)} accepted, "
          f"{sum(d['decision'] != 'ACCEPT' for d in decisions)} left pending")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().execute)))
