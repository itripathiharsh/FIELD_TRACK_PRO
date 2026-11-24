"""Release 3.3 one-off: set the approved production brand master.

Active after this: Usha, Zebronics, RR, Singer, VU (RR and Singer are created when missing). Every other brand is
DEACTIVATED, never deleted. No invoice, receipt, payment, allocation or customer-brand row is read for writing or
changed: their brand text stays exactly as Tally sent it, so every historical total is unchanged.

    python scripts/apply_brand_master.py            # dry run: shows what would change
    python scripts/apply_brand_master.py --execute  # apply
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import select  # noqa: E402

from app.database import AsyncSessionLocal  # noqa: E402
from app.models.brand import Brand  # noqa: E402

APPROVED = {"usha": "USHA", "zebronics": "Zebronics", "rr": "RR", "singer": "Singer", "vu": "VU"}


async def main(execute: bool) -> int:
    async with AsyncSessionLocal() as s:
        brands = {b.normalized_name: b for b in (await s.execute(select(Brand))).scalars().all()}
        plan = []
        for key, name in APPROVED.items():
            b = brands.get(key)
            if b is None:
                plan.append(("CREATE active", name))
                if execute:
                    s.add(Brand(name=name, normalized_name=key, is_active=True))
            elif not b.is_active:
                plan.append(("ACTIVATE", b.name))
                if execute:
                    b.is_active = True
            else:
                plan.append(("keep active", b.name))
        for key, b in sorted(brands.items()):
            if key in APPROVED:
                continue
            if b.is_active:
                plan.append(("DEACTIVATE", b.name))
                if execute:
                    b.is_active = False
            else:
                plan.append(("keep inactive", b.name))
        if execute:
            await s.commit()
    for action, name in plan:
        print(f"{action:14} {name}")
    print("APPLIED" if execute else "DRY RUN (use --execute to apply)")
    return 0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--execute", action="store_true")
    sys.exit(asyncio.run(main(ap.parse_args().execute)))
