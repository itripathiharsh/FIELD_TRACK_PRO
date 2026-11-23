# FieldTrack Pro: source backup (agent, release scripts, QA builder)

Companion to the application repository. These folders were previously only on one PC.

| Folder | What it is |
|---|---|
| `tally_sync_agent/` | The Tally Sync Agent source (3.0.0). Build with `release_v2/agent_3.0.0/build_agent_3.0.0.py` |
| `release_v2/agent_3.0.0/` | Architecture/install docs, build script, replay harness, H2 test tooling, installer scripts |
| `release_v2/scope_3.1/` | Release 3.1 (Distribution-only scope) test-DB setup, dry-run, rollout and verification scripts |
| `qa-demo/` | The accountant QA/demo environment: dataset seeders, repo builder, Render blueprint, smoke test |
| `qa-dataset/` | Earlier local QA dataset generator |
| `AGENTS.md` | Project rules |

## Deliberately NOT included
Binaries (agent .exe, packages, APKs), databases and dumps, `.env` files and tokens, client spreadsheets, reports that list
real ledger names or amounts, test results/evidence, and anything under `private/`. Rebuild the agent from source; rebuild
the QA environment with `qa-demo/build_all.sh` + `build_qa_repo.py`.
