#!/usr/bin/env python3
"""
Prepare a FieldTrack Pro release for in-app updates.

Reads the APK's package/version with aapt2, prints its signing certificate with apksigner, computes SHA-256 and size,
copies the APK to an immutable versioned file name and writes app-update.json. Nothing is uploaded or deployed:
the output folder is then copied into fieldtrackpro-web/public/downloads/ and deployed (with approval).

Example:
  python tools/make_update_manifest.py --apk app/build/outputs/apk/release/app-release.apk \
      --note "Faster dashboard" --note "Bug fixes" --out build/update-release \
      [--mandatory] [--min-supported 6] [--previous https://fieldtrack-pro-rosy.vercel.app/downloads/app-update.json]

Output:
  <out>/releases/FieldTrackPro-<versionName>-<versionCode>.apk
  <out>/app-update.json
"""
import argparse
import datetime
import glob
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import urllib.request

PACKAGE = "com.fieldtrackpro.android"
DEFAULT_BASE = "https://fieldtrack-pro-rosy.vercel.app/downloads"


def sdk_tool(name):
    sdk = os.environ.get("ANDROID_HOME") or os.environ.get("ANDROID_SDK_ROOT") or r"C:\Android\sdk"
    candidates = sorted(glob.glob(os.path.join(sdk, "build-tools", "*", name + "*")), reverse=True)
    if not candidates:
        sys.exit(f"Cannot find {name} under {sdk}/build-tools (set ANDROID_HOME).")
    return candidates[0]


def badging(apk):
    out = subprocess.run([sdk_tool("aapt2"), "dump", "badging", apk], capture_output=True, text=True, check=True).stdout
    m = re.search(r"package: name='([^']+)' versionCode='(\d+)' versionName='([^']+)'", out)
    if not m:
        sys.exit("Could not read package info from the APK.")
    return m.group(1), int(m.group(2)), m.group(3)


def signer_sha256(apk):
    out = subprocess.run([sdk_tool("apksigner"), "verify", "--print-certs", apk],
                         capture_output=True, text=True, shell=os.name == "nt").stdout
    m = re.search(r"Signer #1 certificate SHA-256 digest: ([0-9a-f]+)", out)
    return m.group(1) if m else None


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apk", required=True)
    ap.add_argument("--note", action="append", default=[], help="release-note line (repeatable)")
    ap.add_argument("--mandatory", action="store_true")
    ap.add_argument("--min-supported", type=int, default=0, help="installed versionCodes below this must update")
    ap.add_argument("--base-url", default=DEFAULT_BASE)
    ap.add_argument("--previous", help="URL or path of the currently published app-update.json (refuses a non-increasing versionCode)")
    ap.add_argument("--expected-cert", help="expected signer certificate SHA-256 (refuses an APK signed with another key)")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    if not a.base_url.startswith("https://"):
        sys.exit("--base-url must be https.")
    pkg, code, name = badging(a.apk)
    if pkg != PACKAGE:
        sys.exit(f"APK package is {pkg}, expected {PACKAGE}.")
    cert = signer_sha256(a.apk)
    if a.expected_cert and cert != a.expected_cert.lower():
        sys.exit(f"APK is signed with {cert}, expected {a.expected_cert}. Installed apps would refuse it.")
    if a.min_supported > code:
        sys.exit("--min-supported cannot be above the APK's versionCode.")
    if a.previous:
        raw = urllib.request.urlopen(a.previous).read() if a.previous.startswith("http") else open(a.previous, "rb").read()
        prev = json.loads(raw)
        if code <= int(prev.get("versionCode", 0)):
            sys.exit(f"versionCode {code} is not higher than the published {prev.get('versionCode')}. Bump it in app/build.gradle.kts.")

    os.makedirs(os.path.join(a.out, "releases"), exist_ok=True)
    file_name = f"FieldTrackPro-{name}-{code}.apk"
    dest = os.path.join(a.out, "releases", file_name)
    shutil.copyfile(a.apk, dest)

    manifest = {
        "schema": 1,
        "packageName": pkg,
        "versionCode": code,
        "versionName": name,
        "apkUrl": f"{a.base_url.rstrip('/')}/releases/{file_name}",
        "apkSha256": sha256(dest),
        "apkSizeBytes": os.path.getsize(dest),
        "minSupportedVersionCode": a.min_supported,
        "mandatory": bool(a.mandatory),
        "releaseNotes": a.note,
        "publishedAt": datetime.date.today().isoformat(),
    }
    with open(os.path.join(a.out, "app-update.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, indent=2, ensure_ascii=False)
    print(json.dumps(manifest, indent=2, ensure_ascii=False))
    print(f"\nSigner certificate SHA-256: {cert}")
    print(f"Copy {a.out}/app-update.json and {a.out}/releases/ into fieldtrackpro-web/public/downloads/, then deploy.")


if __name__ == "__main__":
    main()
