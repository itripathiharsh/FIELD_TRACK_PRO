"""Build the standalone QA repo (qa-demo/repo) from the release 3.1 commit. Production sources are only READ (git archive).

  python build_qa_repo.py          # export backend + web, patch web for QA mode, test, build, assemble the repo

Result layout (this is what is pushed to the new private GitHub repo and deployed by Render):
  repo/fieldtrackpro-backend/   backend 3.1 sources (no tests/docs/media) + qa_asgi.py (serves API + web from ONE address)
  repo/fieldtrackpro-backend/web_dist/     the QA web build (VITE_APP_ENV=qa: demo banner, same-origin API)
  repo/fieldtrackpro-backend/qa_media/     synthetic demo photographs
  repo/render.yaml, repo/README_QA.md
"""
from __future__ import annotations

import os
import shutil
import subprocess
import sys
import tarfile
import io
from pathlib import Path

HERE = Path(__file__).resolve().parent
MONO = Path(r"F:\Field track pro v2 for test\field track pro")
COMMIT = "77cfca0"
WORK = HERE / "work"
REPO = HERE / "repo"
WEB = WORK / "fieldtrackpro-web"
PROD_NODE_MODULES = MONO / "fieldtrackpro-web" / "node_modules"


def run(cmd, cwd=None, env=None, check=True):
    r = subprocess.run(cmd, cwd=cwd, env=env, capture_output=True, text=True, shell=isinstance(cmd, str))
    if check and r.returncode:
        sys.exit(f"FAILED: {cmd}\n{r.stdout[-2500:]}\n{r.stderr[-2500:]}")
    return r


def drop_junction(p: Path):
    """Remove a directory junction itself (cmd rmdir unlinks; it never deletes the target's contents)."""
    if os.path.lexists(p):
        r = subprocess.run(["cmd", "/c", "rmdir", str(p)], capture_output=True, text=True)
        assert not os.path.lexists(p), f"could not unlink {p}: {r.stderr}"


def export(path_in_repo: str, dest: Path):
    data = subprocess.run(["git", "-C", str(MONO), "archive", "--format=tar", COMMIT, path_in_repo], capture_output=True, check=True).stdout
    dest.mkdir(parents=True, exist_ok=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as t:
        t.extractall(dest)


def patch(path: Path, old: str, new: str, count=1):
    s = path.read_text(encoding="utf-8")
    assert old in s, f"patch anchor not found in {path.name}: {old[:60]!r}"
    path.write_text(s.replace(old, new, count), encoding="utf-8")


def main():
    for d in (WORK, REPO):
        if d.exists():
            drop_junction(WEB / "node_modules")      # unlink first: rmtree must never reach the production node_modules
            shutil.rmtree(d)
    WORK.mkdir()
    REPO.mkdir()

    # ------------------------------------------------------------------ web: export + QA patch
    export("fieldtrackpro-web", WORK)
    run(f'cmd /c mklink /J "{WEB / "node_modules"}" "{PROD_NODE_MODULES}"')

    patch(WEB / "src/config/env.ts",
          "  let apiBase = configured;\n  if (!configured) {\n    if (isProd) {",
          "  let apiBase = configured;\n  const isQa = (raw.VITE_APP_ENV ?? '') === 'qa';\n  if (!configured) {\n"
          "    if (isQa && typeof window !== 'undefined') {\n"
          "      // QA/demo build: the API is served from the same address as the web app (no build-time URL needed).\n"
          "      apiBase = window.location.origin;\n    } else if (isProd) {")
    (WEB / "src/components/ui/DemoBanner.tsx").write_text('''import React from 'react';
import { ENV } from '../../config/env';

/** True only in the QA/demo build (VITE_APP_ENV=qa). Production builds never render the banner. */
export const isDemoEnv = (): boolean => ENV.APP_ENV === 'qa';

/**
 * Persistent DEMO / TEST ENVIRONMENT banner (QA build only). It sits above everything, on the login page too,
 * so nobody can mistake this environment for production.
 */
export const DemoBanner: React.FC = () => {
  if (!isDemoEnv()) return null;
  return (
    <div
      role="status"
      data-testid="demo-banner"
      className="sticky top-0 z-[60] w-full bg-amber-400 px-3 py-1.5 text-center text-xs font-bold uppercase tracking-wide text-black shadow"
    >
      Demo / Test environment &mdash; all data is fictional &middot; not connected to production or the real Tally
    </div>
  );
};
''', encoding="utf-8")
    # The banner is mounted once at the app root, so it is on EVERY page including the login screen.
    patch(WEB / "src/App.tsx", "import { Layout } from './components/layout/Layout';",
          "import { Layout } from './components/layout/Layout';\nimport { DemoBanner } from './components/ui/DemoBanner';")
    patch(WEB / "src/App.tsx", "    <BrowserRouter>\n      <AuthProvider>\n        <AppContent />",
          "    <BrowserRouter>\n      <DemoBanner />\n      <AuthProvider>\n        <AppContent />")
    patch(WEB / "src/main.tsx", "import './index.css'\n",
          "import './index.css'\n\nif (ENV.APP_ENV === 'qa') {\n  document.documentElement.classList.add('qa-demo');\n  document.title = '[DEMO] ' + document.title;\n}\n")
    with open(WEB / "src/index.css", "a", encoding="utf-8") as f:
        f.write("\n/* QA/demo build: keep the fixed sidebar and sticky header below the demo banner (banner is 32px) */\n"
                "html.qa-demo aside.fixed { top: 32px; height: calc(100vh - 32px); }\n"
                "html.qa-demo header.sticky { top: 32px; }\n")
    (WEB / "src/components/ui/DemoBanner.test.tsx").write_text('''import { describe, expect, it, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

describe('DemoBanner', () => {
  it('renders in the QA build', async () => {
    vi.resetModules();
    vi.doMock('../../config/env', () => ({ ENV: { APP_ENV: 'qa' } }));
    const { DemoBanner } = await import('./DemoBanner');
    render(<DemoBanner />);
    expect(screen.getByTestId('demo-banner').textContent).toMatch(/Demo \\/ Test environment/i);
  });
  it('never renders in a production build', async () => {
    vi.resetModules();
    vi.doMock('../../config/env', () => ({ ENV: { APP_ENV: 'production' } }));
    const { DemoBanner } = await import('./DemoBanner');
    render(<DemoBanner />);
    expect(screen.queryByTestId('demo-banner')).toBeNull();
  });
});
''', encoding="utf-8")
    with open(WEB / "src/config/env.test.ts", "a", encoding="utf-8") as f:
        f.write('''
describe('resolveEnv QA mode', () => {
  it('QA build without VITE_API_BASE_URL uses the page origin and reports no config error', () => {
    const env = resolveEnv({ VITE_APP_ENV: 'qa' }, true);
    expect(env.APP_ENV).toBe('qa');
    expect(env.API_BASE_URL).toBe(window.location.origin);
    expect(env.CONFIG_ERRORS).toEqual([]);
  });
  it('production build without VITE_API_BASE_URL is still a configuration error', () => {
    expect(resolveEnv({}, true).CONFIG_ERRORS.length).toBe(1);
  });
});
''')
    print("web patched")

    # ------------------------------------------------------------------ web: tests + build
    r = run("npx vitest run src/config/env.test.ts src/components/ui/DemoBanner.test.tsx", cwd=WEB, check=False)
    print((r.stdout + r.stderr)[-900:])
    if r.returncode:
        sys.exit("web tests failed")
    env = {**os.environ, "VITE_APP_ENV": "qa", "VITE_API_BASE_URL": ""}
    r = run("npm run build -- --mode qa", cwd=WEB, env=env, check=False)   # mode qa: the production-only URL guard does not apply
    print((r.stdout + r.stderr)[-700:])
    if r.returncode:
        sys.exit("web build failed")
    drop_junction(WEB / "node_modules")     # remove the junction only (never the target)

    # ------------------------------------------------------------------ backend export
    export("fieldtrackpro-backend", REPO)
    be = REPO / "fieldtrackpro-backend"
    for junk in ("tests", "scratch", "data", "media_storage", "scripts", "cleanup_output.txt", "server_debug.log", "server_error.log",
                 "server_trace.log", ".env", ".env.example", "STORAGE_MIGRATION.md", "ADMIN_SECURITY.md", "README.md", "run_backend.py", ".pytest_cache"):
        p = be / junk
        if p.is_dir():
            shutil.rmtree(p)
        elif p.exists():
            p.unlink()
    shutil.copytree(WEB / "dist", be / "web_dist")
    shutil.copytree(HERE / "media_storage", be / "qa_media")
    shutil.copy2(HERE / "qa_asgi.py", be / "qa_asgi.py")
    shutil.copy2(HERE / "render.yaml", REPO / "render.yaml")
    shutil.copy2(HERE / "README_QA.md", REPO / "README_QA.md")
    (REPO / ".gitignore").write_text("*.env\n.env*\nprivate/\n*.dump\n__pycache__/\n", encoding="utf-8")
    size = sum(f.stat().st_size for f in REPO.rglob("*") if f.is_file())
    print(f"repo assembled: {REPO}  ({size / 1e6:.1f} MB, {sum(1 for f in REPO.rglob('*') if f.is_file())} files)")


if __name__ == "__main__":
    main()
