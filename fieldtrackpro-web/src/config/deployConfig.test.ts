import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import path from 'node:path';
import { MAPLIBRE_WORKER_URL } from '../components/maps/tileConfig';

/**
 * Guards the deployment hardening in vercel.json and the self-hosted MapLibre
 * worker so a later edit cannot silently reintroduce a CDN dependency or HSTS preload.
 */
const root = path.resolve(__dirname, '../..');

interface VercelHeader {
  source: string;
  headers: { key: string; value: string }[];
}

function globalHeader(key: string): string {
  const cfg = JSON.parse(readFileSync(path.join(root, 'vercel.json'), 'utf8')) as { headers: VercelHeader[] };
  const entry = cfg.headers.find((h) => h.source === '/(.*)');
  const value = entry?.headers.find((h) => h.key === key)?.value;
  if (!value) throw new Error(`missing ${key}`);
  return value;
}

describe('vercel.json security headers', () => {
  it('CSP has upgrade-insecure-requests and no CDN allowance', () => {
    const csp = globalHeader('Content-Security-Policy');
    expect(csp).toContain('upgrade-insecure-requests');
    expect(csp).not.toContain('cdn.jsdelivr.net');
    expect(csp).toMatch(/script-src 'self';/);
    expect(csp).toMatch(/worker-src 'self' blob:;/);
    expect(csp).toContain("frame-ancestors 'none'");
  });

  it('HSTS keeps max-age but is not preload-listed and does not claim subdomains', () => {
    const hsts = globalHeader('Strict-Transport-Security');
    expect(hsts).toMatch(/max-age=\d{7,}/);
    expect(hsts).not.toMatch(/preload/i);
    expect(hsts).not.toMatch(/includeSubDomains/i);
  });
});

describe('self-hosted MapLibre worker', () => {
  it('points at a same-origin path, not a CDN', () => {
    expect(MAPLIBRE_WORKER_URL.startsWith('/')).toBe(true);
    expect(MAPLIBRE_WORKER_URL).not.toMatch(/^https?:/);
  });

  it('the worker and the shared chunk it imports exist in the installed maplibre-gl package', () => {
    const dist = path.join(root, 'node_modules/maplibre-gl/dist');
    const worker = path.join(dist, 'maplibre-gl-worker.mjs');
    expect(existsSync(worker)).toBe(true);
    expect(existsSync(path.join(dist, 'maplibre-gl-shared.mjs'))).toBe(true);
    expect(readFileSync(worker, 'utf8')).toContain('./maplibre-gl-shared.mjs');
    expect(path.basename(MAPLIBRE_WORKER_URL)).toBe('maplibre-gl-worker.mjs');
  });
});
