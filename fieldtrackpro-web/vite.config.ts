import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import path from 'path';

// https://vitejs.dev/config/
export default defineConfig({
  plugins: [react()],
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
  server: {
    port: 5173,
    host: true,
  },
});
