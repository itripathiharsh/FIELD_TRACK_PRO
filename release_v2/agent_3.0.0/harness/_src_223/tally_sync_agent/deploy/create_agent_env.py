"""
Create the Tally sync agent in FieldTrack production and write a ready-to-use .env (agent key included) - run ON YOUR PC.

    python create_agent_env.py

Prompts for an ADMIN / SUPER_ADMIN email and password (password hidden, never printed or stored), logs in, registers ONE new agent
(POST /api/v1/integrations/tally/agents) and saves the one-time key to ".env" next to this script. The key is shown only once by
the server, so keep that file safe, copy it to the Tally server, then delete every copy you no longer need.
Refuses to overwrite an existing .env.
"""
import getpass
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

BASE = "https://51-79-158-138.sslip.io"
OUT = Path(__file__).resolve().parent / ".env"


def call(method, path, body=None, token=None):
    req = urllib.request.Request(BASE + path, method=method, data=json.dumps(body).encode() if body is not None else None,
                                 headers={"Content-Type": "application/json", **({"Authorization": "Bearer " + token} if token else {})})
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return r.status, json.loads(r.read() or b"null")
    except urllib.error.HTTPError as e:
        return e.code, None


def main() -> int:
    if OUT.exists():
        print(f"{OUT} already exists - not overwriting. Delete it first if you really want a new agent key.")
        return 1
    email = input("Admin / Super Admin email: ").strip()
    password = getpass.getpass("Password (hidden): ")
    name = input("Agent name [Client Tally Cloud]: ").strip() or "Client Tally Cloud"
    code, tok = call("POST", "/api/v1/auth/login", {"email": email, "password": password})
    password = ""
    if code != 200 or not tok or not tok.get("access_token"):
        print(f"Login failed (HTTP {code}).")
        return 1
    code, res = call("POST", "/api/v1/integrations/tally/agents", {"name": name, "organization_id": "default"}, tok["access_token"])
    if code not in (200, 201) or not res:
        print(f"Agent creation failed (HTTP {code}). Needs an ADMIN or SUPER_ADMIN account.")
        return 1
    agent = res["agent"]
    OUT.write_text(
        "TALLY_URL=http://127.0.0.1:9000\nTALLY_TIMEOUT_SECONDS=180\n"
        f"BACKEND_URL={BASE}\nBACKEND_TIMEOUT_SECONDS=60\n"
        f"AGENT_ID={agent['id']}\nAGENT_KEY={res['api_key']}\nORGANIZATION_ID={agent['organization_id']}\n"
        "TALLY_WRITEBACK_ENABLED=false\nBATCH_SIZE=100\nSYNC_INTERVAL_SECONDS=300\nHEARTBEAT_INTERVAL_SECONDS=60\nLOG_LEVEL=INFO\n",
        encoding="utf-8",
    )
    print(f"Agent '{name}' created (id {agent['id']}). Wrote {OUT} (read-only mode, key inside - keep it private).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
