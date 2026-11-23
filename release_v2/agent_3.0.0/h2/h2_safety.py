"""H2 safety lock: every H2 tool calls these guards before it touches Tally, the database or the file system.

    python h2_safety.py preflight     READ-ONLY: Tally company, company folder, backend database, agent .env (if present)
    python h2_safety.py rollback-plan READ-ONLY: prints exactly what rollback would delete (nothing is deleted)

Only Tally EXPORT requests are sent here. Nothing is written anywhere.
"""
from __future__ import annotations

import json
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

HERE = Path(__file__).resolve().parent
LOCK = json.loads((HERE / "h2_lock.json").read_text(encoding="utf-8"))

_COMPANY_EXPORT = """<ENVELOPE><HEADER><VERSION>1</VERSION><TALLYREQUEST>Export</TALLYREQUEST><TYPE>Collection</TYPE>
<ID>H2CmpList</ID></HEADER><BODY><DESC><STATICVARIABLES><SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT></STATICVARIABLES>
<TDL><TDLMESSAGE><COLLECTION NAME="H2CmpList" ISMODIFY="No"><TYPE>Company</TYPE>
<FETCH>Name, Guid, Destination, CompanyNumber, BooksFrom</FETCH></COLLECTION></TDLMESSAGE></TDL></DESC></BODY></ENVELOPE>"""


class LockViolation(SystemExit):
    pass


def _export(xml: str) -> ET.Element:
    assert "<TALLYREQUEST>Export</TALLYREQUEST>" in xml and "Import" not in xml, "h2_safety sends Export only"
    req = urllib.request.Request(LOCK["tally_url"], data=xml.encode("utf-8"), method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        body = r.read().decode("utf-8", "replace")
    return ET.fromstring(re.sub(r"&#(?:[0-8]|1[0-9]|2[0-9]|3[01]);", "", body))


def loaded_companies() -> list:
    out = []
    for c in _export(_COMPANY_EXPORT).iter("COMPANY"):
        if c.get("NAME") is None and not c.findtext("GUID"):
            continue  # scalar <COMPANY> count fields are not companies
        out.append({"name": (c.get("NAME") or c.findtext("NAME") or "").strip(),
                    "guid": (c.findtext("GUID") or "").strip(),
                    "folder": (c.findtext("DESTINATION") or "").strip(),
                    "number": (c.findtext("COMPANYNUMBER") or "").strip(),
                    "books_from": (c.findtext("BOOKSFROM") or "").strip()})
    return out


def assert_test_company() -> dict:
    """Raises LockViolation unless exactly the locked test company is loaded. Called before EVERY Tally write."""
    cs = loaded_companies()
    for c in cs:
        if c["guid"] in LOCK["rejected_company_guids"]:
            raise LockViolation(f"REFUSED: rejected company loaded ({LOCK['rejected_company_guids'][c['guid']]})")
        if any(f.lower() in c["name"].lower() for f in LOCK["rejected_company_name_fragments"]):
            raise LockViolation(f"REFUSED: a company named like '{c['name']}' is loaded")
    if len(cs) != 1:
        raise LockViolation(f"REFUSED: exactly one company must be loaded, found {len(cs)}: {[c['name'] for c in cs]}")
    c = cs[0]
    if c["name"] != LOCK["company_name"] or c["guid"] != LOCK["company_guid"]:
        raise LockViolation(f"REFUSED: loaded company {c['name']} / {c['guid']} is not the locked test company")
    if Path(c["folder"]).resolve() != Path(LOCK["company_folder"]).resolve():
        raise LockViolation(f"REFUSED: company folder {c['folder']} is not {LOCK['company_folder']}")
    return c


def assert_company_folder() -> dict:
    """The company folder is a direct child of Tally's data folder and holds a Tally company, nothing else."""
    folder, parent = Path(LOCK["company_folder"]), Path(LOCK["tally_data_parent"])
    if folder.parent.resolve() != parent.resolve() or folder.name != str(LOCK["company_number"]):
        raise LockViolation(f"REFUSED: {folder} is not <data>\\{LOCK['company_number']}")
    if not (folder / "Company.1800").is_file():
        raise LockViolation(f"REFUSED: {folder} holds no Tally company")
    subdirs = [p.name for p in folder.iterdir() if p.is_dir()]
    if subdirs:
        raise LockViolation(f"REFUSED: unexpected sub-folders in the company folder: {subdirs}")
    siblings = sorted(p.name for p in parent.iterdir())
    return {"folder": str(folder), "files": len(list(folder.iterdir())),
            "bytes": sum(p.stat().st_size for p in folder.iterdir()), "data_parent_entries": siblings}


def assert_backend_target(database_url: str, backend_url: str) -> None:
    host = re.search(r"@([^/:]+)", database_url).group(1)
    db = database_url.rsplit("/", 1)[-1].split("?")[0]
    if host not in ("127.0.0.1", "localhost"):
        raise LockViolation(f"REFUSED: database host {host} is not local")
    if db != LOCK["backend_db"] or db in LOCK["forbidden_dbs"]:
        raise LockViolation(f"REFUSED: database {db} is not {LOCK['backend_db']}")
    if backend_url.rstrip("/") != LOCK["backend_url"] or any(h in backend_url for h in LOCK["forbidden_backend_hosts"]):
        raise LockViolation(f"REFUSED: backend URL {backend_url} is not {LOCK['backend_url']}")


def assert_agent_env(env_path: Path) -> dict:
    env = {}
    for line in env_path.read_text(encoding="utf-8-sig").splitlines():
        if "=" in line and not line.lstrip().startswith("#"):
            k, v = line.split("=", 1)
            env[k.strip()] = v.strip()
    checks = {
        "EXPECTED_COMPANY_GUID": env.get("EXPECTED_COMPANY_GUID") == LOCK["company_guid"],
        "BACKEND_URL": env.get("BACKEND_URL", "").rstrip("/") == LOCK["backend_url"],
        "AGENT_INSTANCE_NAME": env.get("AGENT_INSTANCE_NAME") == LOCK["agent_instance_name"],
        "ALLOW_NAMED_INSTANCE_ON_PRODUCTION": env.get("ALLOW_NAMED_INSTANCE_ON_PRODUCTION", "false").lower() == "false",
        "TALLY_URL": env.get("TALLY_URL") == LOCK.get("agent_tally_url", LOCK["tally_url"]),
        "HISTORY_UPLOAD empty": not env.get("HISTORY_UPLOAD"),
    }
    bad = [k for k, ok in checks.items() if not ok]
    if bad:
        raise LockViolation(f"REFUSED: agent .env fails the lock on {bad}")
    return {k: "OK" for k in checks}  # values (incl. the agent key) are never printed


def rollback_plan() -> dict:
    """The ONE folder rollback deletes. Never the parent data folder, never any SGRG folder."""
    folder = Path(LOCK["company_folder"]).resolve()
    parent = Path(LOCK["tally_data_parent"]).resolve()
    assert folder != parent and folder.parent == parent and folder.name == str(LOCK["company_number"])
    assert "sgrg" not in str(folder).lower()
    return {"delete_tally_company_folder": str(folder), "keep": [str(parent), r"F:\Tally SGRG Data (all)", r"F:\tally\tally.ini"],
            "drop_database": LOCK["backend_db"], "delete_agent_folder": r"F:\FT_H2\agent",
            "precondition": "Tally must have the company CLOSED (or Tally exited) before the folder is deleted"}


def main(cmd: str) -> None:
    if cmd == "preflight":
        res = {"tally_company": assert_test_company(), "company_folder": assert_company_folder()}
        sys.path.insert(0, str(HERE.parent / "harness"))
        import setup_backend as sb
        sb.HARNESS_DB = LOCK["backend_db"]
        env = sb.harness_env()
        assert_backend_target(env["DATABASE_URL"], LOCK["backend_url"])
        assert_backend_target(env["MIGRATION_DATABASE_URL"], LOCK["backend_url"])
        res["backend_db"] = {"database": LOCK["backend_db"], "host": "local", "url_masked": re.sub(r":[^:@/]+@", ":***@", env["DATABASE_URL"])}
        envp = Path(r"F:\FT_H2\agent\.env")
        res["agent_env"] = assert_agent_env(envp) if envp.exists() else "not created yet (step S2)"
        res["rejected_guids"] = list(LOCK["rejected_company_guids"])
        print(json.dumps(res, indent=1))
        print("PREFLIGHT OK")
    elif cmd == "rollback-plan":
        print(json.dumps(rollback_plan(), indent=1))
    else:
        raise SystemExit(__doc__)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "")
