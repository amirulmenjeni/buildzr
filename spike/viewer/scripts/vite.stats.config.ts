// Per-package attribution of the real bundle: writes stats JSON to .stats/ (ignored by git).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { visualizer } from 'rollup-plugin-visualizer';
export default defineConfig({ base: './', plugins: [react(), visualizer({ template: 'raw-data', filename: '.stats/stats.json', gzipSize: true })], build: { outDir: 'dist-stats', emptyOutDir: true } });
