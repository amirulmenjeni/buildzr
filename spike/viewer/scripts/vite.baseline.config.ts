// Baseline: React 19 + react-dom only ("hello"). Output goes to dist-baseline/ (ignored by git).
import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
export default defineConfig({ root: 'scripts/baseline', base: './', plugins: [react()], build: { outDir: '../../dist-baseline', emptyOutDir: true } });
