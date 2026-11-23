"""TEST-ONLY Educational-Mode date-window adapter for H2. Never shipped; the released agent is not modified.

    python edu_adapter.py            listen on 127.0.0.1:9001, forward to Tally at 127.0.0.1:9000

Results produced through it are "real TallyPrime (Educational Mode) through a test-only date adapter", NOT
licensed-Tally validation.

Why it is exact: in Educational Mode a voucher can only be dated the 1st, 2nd or 31st, and Tally rejects other days
as period ends / formula dates (measured: H2_EDU_FEASIBILITY.md). For ANY data in the company, [X, Y] therefore
selects the same vouchers as [next allowed day >= X, last allowed day <= Y]. The adapter rewrites ONLY:
    <SVFROMDATE> -> next allowed day      <SVTODATE> -> last allowed day   (left alone if the period has no allowed day)
    $Date >= $$Date:"X" -> next allowed   $Date <= $$Date:"X" -> last allowed     ($Date = $$Date:"X" left alone)
Everything else is forwarded byte for byte; Tally's answer is returned unchanged.

READ-ONLY: anything that is not TALLYREQUEST=Export, or carries an ACTION attribute / IMPORTDATA, is refused with
HTTP 403 and never reaches Tally. Every request (forwarded or refused) is logged with its original and transformed
date boundaries to results/adapter_requests.jsonl.
"""
from __future__ import annotations

import json
import re
import threading
import time
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOG = HERE / "results" / "adapter_requests.jsonl"
LISTEN = ("127.0.0.1", 9001)
TALLY = "http://127.0.0.1:9000"
EDU = (1, 2, 31)
_MON = ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec")
_lock = threading.Lock()


def allowed(d: date) -> bool:
    return d.day in EDU


def next_allowed(d: date) -> date:
    while not allowed(d):
        d += timedelta(days=1)
    return d


def prev_allowed(d: date) -> date:
    while not allowed(d):
        d -= timedelta(days=1)
    return d


def parse_tday(s: str) -> date:
    dd, mm, yy = s.strip().split("-")
    return date(int(yy), _MON.index(mm[:3].title()) + 1, int(dd))


def tday(d: date) -> str:
    return f"{d.day}-{_MON[d.month - 1]}-{d.year}"


WRITE_MARKERS = re.compile(r"ACTION\s*=|<IMPORTDATA|<TALLYMESSAGE", re.I)


def is_read_only(xml: str) -> tuple:
    m = re.search(r"<TALLYREQUEST>\s*([^<]*?)\s*</TALLYREQUEST>", xml, re.I)
    if not m:
        return False, "no TALLYREQUEST"
    if m.group(1).strip().lower() != "export":
        return False, f"TALLYREQUEST={m.group(1).strip()}"
    w = WRITE_MARKERS.search(xml)
    if w:
        return False, f"write marker {w.group(0)!r}"
    return True, ""


def rewrite(xml: str) -> tuple:
    """-> (xml, changes). changes: list of {kind, from, to}."""
    changes = []
    f = re.search(r'<SVFROMDATE TYPE="Date">([^<]+)</SVFROMDATE>', xml)
    t = re.search(r'<SVTODATE TYPE="Date">([^<]+)</SVTODATE>', xml)
    if f and t:
        a, b = parse_tday(f.group(1)), parse_tday(t.group(1))
        na, nb = next_allowed(a), prev_allowed(b)
        if na <= nb:
            if na != a:
                xml = xml.replace(f.group(0), f'<SVFROMDATE TYPE="Date">{tday(na)}</SVFROMDATE>', 1)
                changes.append({"kind": "SVFROMDATE", "from": str(a), "to": str(na)})
            if nb != b:
                xml = xml.replace(t.group(0), f'<SVTODATE TYPE="Date">{tday(nb)}</SVTODATE>', 1)
                changes.append({"kind": "SVTODATE", "from": str(b), "to": str(nb)})
        else:
            changes.append({"kind": "PERIOD_WITHOUT_ALLOWED_DAY", "from": f"{a}..{b}", "to": "unchanged"})

    def sub(op, fn):
        def repl(m):
            old = parse_tday(m.group(2))
            new = fn(old)
            if new != old:
                changes.append({"kind": f"$Date {op}", "from": str(old), "to": str(new)})
            return f'{m.group(1)}$$Date:"{tday(new)}"'
        return repl
    xml = re.sub(r'(\$Date\s*&gt;=\s*)\$\$Date:"([^"]+)"', sub(">=", next_allowed), xml)
    xml = re.sub(r'(\$Date\s*&lt;=\s*)\$\$Date:"([^"]+)"', sub("<=", prev_allowed), xml)
    return xml, changes


def _log(rec: dict) -> None:
    with _lock:
        LOG.parent.mkdir(exist_ok=True)
        with LOG.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(rec) + "\n")


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet console
        pass

    def _reply(self, code: int, body: bytes, ctype: str = "text/xml;charset=utf-8"):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Connection", "close")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        _log({"at": datetime.now().isoformat(timespec="seconds"), "status": "REFUSED", "why": "GET"})
        self._reply(405, b"<RESPONSE>H2 adapter: POST Export only</RESPONSE>")

    def do_POST(self):
        t0 = time.perf_counter()
        raw = self.rfile.read(int(self.headers.get("Content-Length") or 0))
        xml = raw.decode("utf-8", errors="replace")
        cid = (re.search(r"<ID>([^<]*)</ID>", xml) or re.search(r"<REPORTNAME>([^<]*)</REPORTNAME>", xml))
        rec = {"at": datetime.now().isoformat(timespec="milliseconds"), "id": cid.group(1) if cid else None}
        ok, why = is_read_only(xml)
        if not ok:
            rec.update(status="REFUSED", why=why)
            _log(rec)
            self._reply(403, b"<RESPONSE>H2 adapter: write request refused (read-only)</RESPONSE>")
            return
        new, changes = rewrite(xml)
        rec["changes"] = changes
        data = new.encode("utf-8")
        req = urllib.request.Request(TALLY, data=data, method="POST", headers={
            "Content-Type": "text/xml;charset=utf-8", "Connection": "close", "Content-Length": str(len(data))})
        try:
            with urllib.request.urlopen(req, timeout=300) as r:
                body = r.read()
            rec.update(status="FORWARDED", bytes=len(body), seconds=round(time.perf_counter() - t0, 3))
            _log(rec)
            self._reply(200, body)
        except (urllib.error.URLError, OSError) as ex:      # Tally down: the agent must see a connection failure
            rec.update(status="TALLY_UNREACHABLE", error=str(ex)[:200])
            _log(rec)
            self._reply(502, b"<RESPONSE>H2 adapter: Tally unreachable</RESPONSE>")


def main():
    srv = ThreadingHTTPServer(LISTEN, Handler)
    print(f"H2 Educational-Mode adapter on {LISTEN[0]}:{LISTEN[1]} -> {TALLY} (Export only)", flush=True)
    srv.serve_forever()


if __name__ == "__main__":
    main()
