"""Build the replay store from the RECORDED Tally answers (read-only on the recordings).

Input  : release_v2/agent_2.2.1/local_tally/raw_validate_2025-26 and raw_validate_2026-27 - every request the agent
         sent to the local TallyPrime copy of SGRG (18-Nov-2026 16:24 IST) and Tally's byte-for-byte answer.
Output : <out>/store.pkl
  vouchers : [{guid, date (ISO), alter, vtype, xml}]  - each VOUCHER element pruned to what the agent's lean fetch
             returns (header + ALLLEDGERENTRIES ledger name / amount / bill and bank allocations), as recorded
  masters  : raw answers of CompanyCol, FtpGroups, FtpLedgers, FtpVchTypes, FtpDebtors (FY 2025-26 scope),
             FtpCreditors (FY 2025-26 scope), Bills Receivable / Payable (as of 18-Nov-2026)
"""
from __future__ import annotations

import pickle
import re
import sys
import xml.etree.ElementTree as ET
from pathlib import Path

ILLEGAL = re.compile(r"[\x00-\x08\x0B\x0C\x0E-\x1F\x7F]|&#(?:[0-8]|1[124-9]|2[0-9]|3[01]);")
KEEP_HEADER = ("DATE", "GUID", "NARRATION", "VOUCHERTYPENAME", "PARTYLEDGERNAME", "VOUCHERNUMBER", "ISOPTIONAL",
               "ISCANCELLED", "ALTERID", "AMOUNT")


def _parse(path: Path) -> ET.Element:
    """Same cleaning as TallyClient._clean_xml (control characters, unbound UDF: prefixes)."""
    cleaned = ILLEGAL.sub("", path.read_text(encoding="utf-8", errors="replace"))
    return ET.fromstring(re.sub(r'<(/?)(\w+):', r'<\1\2_', cleaned))


def prune(v: ET.Element) -> ET.Element:
    out = ET.Element("VOUCHER", {k: v.attrib[k] for k in ("VCHTYPE",) if k in v.attrib})
    for tag in KEEP_HEADER:
        e = v.find(tag)
        if e is not None:
            ET.SubElement(out, tag).text = e.text
    lines = v.findall("./ALLLEDGERENTRIES.LIST") or v.findall("./LEDGERENTRIES.LIST")
    for line in lines:
        le = ET.SubElement(out, "ALLLEDGERENTRIES.LIST")
        for tag in ("LEDGERNAME", "AMOUNT"):
            e = line.find(tag)
            if e is not None:
                ET.SubElement(le, tag).text = e.text
        for sub in ("BILLALLOCATIONS.LIST", "BANKALLOCATIONS.LIST"):
            for b in line.findall("./" + sub):
                le.append(b)
    return out


def main(local_tally: Path, out: Path) -> None:
    out.mkdir(parents=True, exist_ok=True)
    vouchers, seen = [], set()
    masters = {}
    for fy in ("2025-26", "2026-27"):
        raw = local_tally / f"raw_validate_{fy}"
        for req in sorted(raw.glob("*.orig.xml")):
            s = req.read_text(encoding="utf-8", errors="replace")
            cid = (re.search(r"<ID>(.*?)</ID>", s) or [None, "?"])[1]
            resp = req.with_name(req.name.replace(".orig.xml", ".response.xml"))
            sv = re.findall(r'<SVFROMDATE TYPE="Date">(.*?)</SVFROMDATE><SVTODATE TYPE="Date">(.*?)</SVTODATE>', s)
            if cid == "FtpVch" and "<FILTER>FtpDay</FILTER>" in s and "FtpAlter" not in s and "VoucherNumber" in s:
                for v in _parse(resp).iter("VOUCHER"):
                    if not len(v):
                        continue
                    g = (v.findtext("GUID") or "").strip()
                    if not g or g in seen:
                        continue
                    seen.add(g)
                    d = (v.findtext("DATE") or "").strip()
                    a = (v.findtext("ALTERID") or "0").strip()
                    p = prune(v)
                    vouchers.append({"guid": g, "date": f"{d[:4]}-{d[4:6]}-{d[6:]}", "alter": int(a) if a.isdigit() else 0,
                                     "vtype": (v.findtext("VOUCHERTYPENAME") or "").strip(),
                                     "xml": ET.tostring(p, encoding="unicode")})
            elif fy == "2026-27" and cid in ("CompanyCol", "FtpGroups", "FtpLedgers", "FtpVchTypes") and cid not in masters:
                masters[cid] = resp.read_text(encoding="utf-8", errors="replace")
            elif fy == "2026-27" and cid in ("FtpDebtors", "FtpCreditors") and sv and sv[0] == ("1-Apr-2025", "31-Mar-2026"):
                masters.setdefault(cid, resp.read_text(encoding="utf-8", errors="replace"))
            elif fy == "2026-27" and cid in ("Bills Receivable", "Bills Payable"):
                masters[cid] = resp.read_text(encoding="utf-8", errors="replace")
    vouchers.sort(key=lambda r: (r["alter"], r["guid"]))
    with open(out / "store.pkl", "wb") as f:
        pickle.dump({"vouchers": vouchers, "masters": masters}, f, protocol=pickle.HIGHEST_PROTOCOL)
    by_fy = {}
    for r in vouchers:
        fy = r["date"][:4] if r["date"][5:7] >= "04" else str(int(r["date"][:4]) - 1)
        by_fy[fy] = by_fy.get(fy, 0) + 1
    print(f"vouchers={len(vouchers)} by FY start year={by_fy} masters={sorted(masters)} "
          f"xml_bytes={sum(len(r['xml']) for r in vouchers)}")


if __name__ == "__main__":
    main(Path(sys.argv[1]), Path(sys.argv[2]))
