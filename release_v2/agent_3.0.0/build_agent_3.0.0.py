"""
Build the Agent 3.0.0 client package locally (no network, no deployment).

    python release_v2/agent_3.0.0/build_agent_3.0.0.py

Same recipe as 2.1.0 (clean venv _build_venv_clean, PyInstaller one-file, the 2.0.0 spec).
Produces in release_v2/agent_3.0.0/:
  CLIENT_DEPLOYMENT_PACKAGE_v3.0.0/        exe, install/uninstall/preflight, env.template, README, UPGRADE, VERSION, SHA256SUMS
  FieldTrack_TallyAgent_Production_v3.0.0.zip
  agent-source-3.0.0.zip
  SHA256SUMS.txt
"""
from __future__ import annotations

import hashlib
import re
import shutil
import subprocess
import zipfile
from pathlib import Path

ROOT = Path(r"F:\Field track pro v2 for test")
AGENT = ROOT / "tally_sync_agent"
OUT = ROOT / "release_v2" / "agent_3.0.0"
VENV_PY = ROOT / "_build_venv_clean" / "Scripts" / "python.exe"
BUILD = ROOT / "_build_v3.0.0_clean"
VERSION = "3.0.0"
PKG = OUT / f"CLIENT_DEPLOYMENT_PACKAGE_v{VERSION}"


def sha(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def main():
    v = re.search(r'AGENT_VERSION\s*=\s*"([^"]+)"', (AGENT / "config" / "settings.py").read_text(encoding="utf-8")).group(1)
    assert v == VERSION, f"agent version is {v}"

    if BUILD.exists():
        shutil.rmtree(BUILD)
    BUILD.mkdir()
    shutil.copy(ROOT / "_build_v2.0.0_clean" / "FieldTrackTallyAgent.spec", BUILD / "FieldTrackTallyAgent.spec")
    r = subprocess.run([str(VENV_PY), "-m", "PyInstaller", "--clean", "--noconfirm", "FieldTrackTallyAgent.spec"],
                       cwd=BUILD, capture_output=True, text=True)
    (BUILD / "build_log.txt").write_text(r.stdout + r.stderr, encoding="utf-8")
    if r.returncode:
        raise SystemExit("PyInstaller failed - see build_log.txt")
    exe = BUILD / "dist" / "FieldTrackTallyAgent.exe"
    assert exe.exists()

    if PKG.exists():
        shutil.rmtree(PKG)
    PKG.mkdir(parents=True)
    shutil.copy(exe, PKG / exe.name)
    for name in ("install_agent.ps1", "uninstall_agent.ps1", "preflight_check.ps1", "env.template"):
        shutil.copy(AGENT / "deploy" / name, PKG / name)
    shutil.copy(ROOT / "release_v2" / "rc_2.1.0" / "README_DEPLOYMENT.md", PKG / "README_DEPLOYMENT.md")
    for doc in ("INSTALL_UPGRADE_ROLLBACK_3.0.0.md", "CHANGES_2.2.3_to_3.0.0.md", "ARCHITECTURE_3.0.md"):
        if (OUT / doc).exists():
            shutil.copy(OUT / doc, PKG / doc)
    (PKG / "VERSION.txt").write_text(
        f"FieldTrack Pro - Tally Sync Agent\nVersion: {VERSION}\nBuilt with: PyInstaller 6.22.3, Python 3.11.9, one-file, clean venv\n"
        f"EXE SHA256: {sha(PKG / exe.name)}\n"
        "3.0.0: reconciliation (ARCHITECTURE_3.0.md, CHANGES_2.2.3_to_3.0.0.md): AlterID fast path every cycle;\n"
        "       hourly headers-only reconciliation of today-31..today and nightly of the whole FY against the backend's\n"
        "       voucher index (missing / stale / extra), repairing only affected dates; quarantine is retry-only; the\n"
        "       post-dated register and catch-ups are removed; all state in one SQLite database; v1 code removed.\n"
        "Backend: REQUIRES release 3.0 (tally_voucher_index, POST /sync/reconcile; migration r3c0n1d2x3y4).\n"
        "Read-only towards Tally. Performs no write-back in any configuration.\n", encoding="utf-8", newline="\n")
    sums = "".join(f"{sha(p)} *{p.name}\n" for p in sorted(PKG.iterdir()) if p.name != "SHA256SUMS.txt")
    (PKG / "SHA256SUMS.txt").write_bytes(sums.encode("utf-8"))

    zp = OUT / f"FieldTrack_TallyAgent_Production_v{VERSION}.zip"
    with zipfile.ZipFile(zp, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(PKG.iterdir()):
            z.write(p, f"FieldTrack_TallyAgent_Production_v{VERSION}/{p.name}")
    src_zip = OUT / f"agent-source-{VERSION}.zip"
    with zipfile.ZipFile(src_zip, "w", zipfile.ZIP_DEFLATED) as z:
        for p in sorted(AGENT.rglob("*")):
            rel = p.relative_to(AGENT)
            if p.is_file() and not any(x in rel.parts for x in ("__pycache__", "data", ".pytest_cache", "_legacy_pre_1.2.2")) \
                    and p.suffix not in (".pyc", ".db", ".log") and p.name != ".env":
                z.write(p, f"tally_sync_agent/{rel.as_posix()}")
    arts = [zp, src_zip, PKG / exe.name]
    (OUT / "SHA256SUMS.txt").write_bytes("".join(f"{sha(p)} *{p.relative_to(OUT).as_posix()}\n" for p in arts).encode("utf-8"))
    print((OUT / "SHA256SUMS.txt").read_text())


if __name__ == "__main__":
    main()
