import { defineConfig, type Plugin } from 'vite';
import react from '@vitejs/plugin-react';
import fs from 'node:fs';
import path from 'node:path';

/** Dev only: serve $VIEWER_DATA (a built `data/` directory) at /data/. The production build never contains data. */
function devData(): Plugin {
  return {
    name: 'viewer-dev-data',
    apply: 'serve',
    configureServer(server) {
      const dir = process.env.VIEWER_DATA;
      if (!dir) return;
      server.middlewares.use('/data', (req, res, next) => {
        const f = path.join(path.resolve(dir), decodeURIComponent((req.url ?? '/').split('?')[0]));
        if (!f.startsWith(path.resolve(dir)) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) return next();
        res.setHeader('content-type', 'application/json');
        fs.createReadStream(f).pipe(res);
      });
    },
  };
}

export default defineConfig({
  base: './',
  plugins: [react(), devData()],
  build: {
    outDir: '../buildzr/site/static',
    emptyOutDir: true,
    sourcemap: false,
    // Fonts and their licence text land together under assets/fonts/.
    rollupOptions: {
      output: {
        assetFileNames: (info) => {
          const n = info.names?.[0] ?? '';
          return /\.(woff2|txt)$/.test(n) ? 'assets/fonts/[name]-[hash][extname]' : 'assets/[name]-[hash][extname]';
        },
      },
    },
  },
});
