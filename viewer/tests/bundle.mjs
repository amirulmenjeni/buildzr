// Bundle size: gzip -9 of HTML + JS + CSS (fonts and licence listed separately), against the spike's 130 KB baseline.
import fs from 'node:fs';
import path from 'node:path';
import zlib from 'node:zlib';
import { STATIC } from './lib.mjs';

const walk = (d) => fs.readdirSync(d, { withFileTypes: true }).flatMap((e) => (e.isDirectory() ? walk(path.join(d, e.name)) : [path.join(d, e.name)]));
let total = 0;
for (const f of walk(STATIC)) {
  const raw = fs.readFileSync(f);
  const gz = zlib.gzipSync(raw, { level: 9 }).length;
  const code = /\.(html|js|css)$/.test(f);
  if (code) total += gz;
  console.log(`${code ? '*' : ' '} ${path.relative(STATIC, f).padEnd(52)} raw ${String(raw.length).padStart(7)}  gzip-9 ${String(gz).padStart(7)}`);
}
console.log(`JS+CSS+HTML gzip -9: ${(total / 1000).toFixed(1)} KB (decimal) = ${(total / 1024).toFixed(1)} KiB; spike baseline 130 KB`);
