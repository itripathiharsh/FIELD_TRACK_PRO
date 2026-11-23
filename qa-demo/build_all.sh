#!/usr/bin/env bash
# Rebuild the QA build database from scratch and seed it (local only). Usage: bash build_all.sh
set -e
cd "$(dirname "$0")"
python setup_build_db.py create | tail -1
rm -f private/build_state.json; rm -rf media_storage
for p in A B C; do echo "=== phase $p"; python seed_qa_demo.py $p 2>&1 | grep -v -E "^\[20|DEBUG|INFO"; done
