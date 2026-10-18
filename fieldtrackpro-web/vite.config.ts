import { defineConfig, loadEnv } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';
import { existsSync, readFileSync } from 'fs';

const apkContentType = (
  req: { url?: string },
  res: { setHeader: (k: string, v: string) => void },
  next: () => void,
) => {
  if (req.url && /\.apk(\?|$)/i.test(req.url)) {
    res.setHeader('Content-Type', 'application/vnd.android.package-archive');
  }
  next();
};

/**
 * Self-host MapLibre's web worker (and the shared chunk it imports) from the
 * INSTALLED maplibre-gl package instead of a CDN: same-origin, version-locked
 * to node_modules, covered by the CSP without cdn.jsdelivr.net. The files are
 * emitted at /maplibre/* in the build and served from node_modules in dev.
 */
const MAPLIBRE_DIST = path.resolve(__dirname, 'node_modules/maplibre-gl/dist');
const MAPLIBRE_WORKER_FILES = ['maplibre-gl-worker.mjs', 'maplibre-gl-shared.mjs'];

const selfHostMaplibreWorker = () => ({
  name: 'self-host-maplibre-worker',
  configureServer(server: { middlewares: { use: (fn: (req: { url?: string }, res: { setHeader: (k: string, v: string) => void; end: (b: Buffer) => void }, next: () => void) => void) => void } }) {
    server.middlewares.use((req, res, next) => {
      const name = (req.url ?? '').split('?')[0].replace(/^\/maplibre\//, '');
      if ((req.url ?? '').startsWith('/maplibre/') && MAPLIBRE_WORKER_FILES.includes(name)) {
        res.setHeader('Content-Type', 'text/javascript; charset=utf-8');
        res.end(readFileSync(path.join(MAPLIBRE_DIST, name)));
        return;
      }
      next();
    });
  },
  generateBundle(this: { emitFile: (f: { type: 'asset'; fileName: string; source: Buffer }) => void }) {
    for (const file of MAPLIBRE_WORKER_FILES) {
      const src = path.join(MAPLIBRE_DIST, file);
      if (!existsSync(src)) throw new Error(`maplibre-gl worker file missing: ${src} (run npm install)`);
      this.emitFile({ type: 'asset', fileName: `maplibre/${file}`, source: readFileSync(src) });
    }
  },
});

// https://vitejs.dev/config/
export default defineConfig(({ command, mode }) => {
  // Fail the production build loudly instead of shipping a bundle that would
  // silently talk to a guessed API origin.
  if (command === 'build' && mode === 'production') {
    const env = loadEnv(mode, process.cwd(), 'VITE_');
    const apiBase = (env.VITE_API_BASE_URL || '').trim();
    if (!apiBase) {
      throw new Error(
        'VITE_API_BASE_URL is required for production builds (e.g. https://api.example.com/api/v1). Set it in the build environment (Vercel project env vars).',
      );
    }
    if (!/^https:\/\//i.test(apiBase)) {
      throw new Error('VITE_API_BASE_URL must be an https:// URL for production builds.');
    }
  }
  return {
  plugins: [
    react(),
    selfHostMaplibreWorker(),
    {
      // Serve .apk with the Android MIME type from dev/preview (Vercel does this via vercel.json).
      name: 'apk-content-type',
      configureServer(server) {
        server.middlewares.use(apkContentType);
      },
      configurePreviewServer(server) {
        server.middlewares.use(apkContentType);
      },
    },
  ],
  resolve: {
    alias: {
      '@': path.resolve(__dirname, './src'),
    },
  },
  optimizeDeps: {
    // MapLibre GL v6 loads its worker file at runtime via dynamic import.
    // Vite's dep optimizer cannot trace this pattern and fails when trying
    // to pre-bundle the worker. Excluding it lets MapLibre handle worker
    // loading itself at runtime, which is the intended behavior.
    exclude: ['maplibre-gl'],
  },
  build: {
    // maplibre-gl alone is ~1 MB minified and cannot be shrunk; it is isolated in its own
    // lazily loaded chunk (only the map pages pull it in), so the warning threshold sits above it.
    chunkSizeWarningLimit: 1100,
    rollupOptions: {
      output: {
        manualChunks(id: string) {
          if (!id.includes('node_modules')) return undefined;
          if (id.includes('maplibre-gl')) return 'maplibre';
          if (/node_modules\/(react|react-dom|react-router|react-router-dom|scheduler)\//.test(id)) {
            return 'react-vendor';
          }
          return undefined;
        },
      },
    },
  },
  server: {
    port: 5173,
    host: true,
  },
};
});
