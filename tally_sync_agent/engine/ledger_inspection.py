"""
Read-only inspection of the client's debtor ledgers: which Tally fields are
actually populated, and in what shape - so field mappings (outlet codes, mobile,
email, GSTIN, closing-balance sign) are based on the real company data, not guesses.

Privacy: only counts and masked value shapes are reported (letters -> A,
digits -> 9, punctuation kept), never the values themselves.
"""
from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional
import xml.etree.ElementTree as ET

from tally_sync_agent.config.settings import DATA_DIR
from tally_sync_agent.core.logger import logger

MAX_SHAPES = 8
_SHAPE_LEN = 32

_EXPLICIT_FETCH = (
    "Name, Parent, Guid, AlterId, MasterId, Address.List, PinCode, StateName, CountryName, LedgerPhone, "
    "LedgerMobile, Mobile, LedgerFax, Email, EmailCC, Website, LedgerContact, PartyGstin, IncomeTaxNumber, "
    "OpeningBalance, ClosingBalance, BillCreditPeriod, IsBillWiseOn, MailingName, LanguageName.List, "
    "LedMailingDetails.List, LedGstRegDetails.List"
)


def mask(value: str) -> str:
    v = re.sub(r"[A-Za-z]", "A", value.strip())
    v = re.sub(r"\d", "9", v)
    return v[:_SHAPE_LEN] + ("…" if len(v) > _SHAPE_LEN else "")


def _query(fetch_clause: str) -> str:
    return f"""<ENVELOPE>
  <HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE><ID>DebtorInspectCol</ID></HEADER>
  <BODY><DESC>
    <STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
    <TDL><TDLMESSAGE>
      <COLLECTION NAME="DebtorInspectCol">
        <TYPE>Ledger</TYPE><CHILDROF>$$GroupSundryDebtors</CHILDROF><BELONGSTO>Yes</BELONGSTO>
        {fetch_clause}
      </COLLECTION>
    </TDLMESSAGE></TDL>
  </DESC></BODY>
</ENVELOPE>"""


def summarize_ledgers(root: ET.Element) -> Dict[str, Any]:
    """Per tag path under LEDGER: ledgers with a non-empty value, and masked shapes."""
    ledgers = root.findall(".//LEDGER")
    filled: Counter = Counter()
    shapes: Dict[str, Counter] = defaultdict(Counter)

    def walk(elem: ET.Element, path: str, seen: set):
        for child in elem:
            p = f"{path}/{child.tag}" if path else child.tag
            text = (child.text or "").strip()
            if text and p not in seen:
                seen.add(p)
                filled[p] += 1
            if text:
                shapes[p][mask(text)] += 1
            walk(child, p, seen)

    for led in ledgers:
        walk(led, "", set())

    return {
        "ledger_count": len(ledgers),
        "fields": {
            p: {
                "ledgers_with_value": filled[p],
                "top_shapes": [{"shape": s, "count": n} for s, n in shapes[p].most_common(MAX_SHAPES)],
            }
            for p in sorted(filled)
        },
    }


def inspect_debtor_ledgers(tally_client, report_dir: Optional[Path] = None) -> Dict[str, Any]:
    root = tally_client.execute_tdl(_query("<NATIVEMETHOD>*</NATIVEMETHOD>"))
    method = "NATIVEMETHOD_ALL"
    if not root.findall(".//LEDGER"):
        root = tally_client.execute_tdl(_query(f"<FETCH>{_EXPLICIT_FETCH}</FETCH>"))
        method = "EXPLICIT_FETCH"
    report = {"generated_at": datetime.now().isoformat(timespec="seconds"), "fetch_method": method}
    report.update(summarize_ledgers(root))
    target = Path(report_dir or DATA_DIR)
    target.mkdir(parents=True, exist_ok=True)
    path = target / f"ledger_inspection_{report['generated_at'].replace(':', '').replace('-', '')}.json"
    path.write_text(json.dumps(report, indent=2, sort_keys=True), encoding="utf-8")
    report["report_path"] = str(path)
    logger.info(f"LEDGER_INSPECTION_FINISHED ledgers={report['ledger_count']} report={path}")
    return report
