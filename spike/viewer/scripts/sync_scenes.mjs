// Copies ../out/scenes/*.json (incl. index.json) into public/scenes/, keeping the local fixture and synthetic-gen rows.
import fs from 'node:fs';
import path from 'node:path';
const src = path.resolve('../out/scenes'), dst = path.resolve('public/scenes');
const KEEP = ['aws-mini.scene.json', 'synthetic-gen.scene.json'];
const localRows = [
  { view: 'aws-mini', title: 'AWS deployment (hand-written fixture)', kind: 'deployment', file: 'aws-mini.scene.json' },
  { view: 'synthetic-gen', title: 'Synthetic 120 nodes (viewer-local generator)', kind: 'synthetic', file: 'synthetic-gen.scene.json' },
];
const rows = JSON.parse(fs.readFileSync(path.join(src, 'index.json'), 'utf8'));
for (const f of fs.readdirSync(src).filter((x) => x.endsWith('.json') && x !== 'index.json')) fs.copyFileSync(path.join(src, f), path.join(dst, f));
const merged = [...rows, ...localRows.filter((l) => !rows.some((r) => r.view === l.view) && fs.existsSync(path.join(dst, l.file)))];
fs.writeFileSync(path.join(dst, 'index.json'), JSON.stringify(merged, null, 1) + '\n');
console.log(`synced ${rows.length} scenes + ${merged.length - rows.length} local (${KEEP.join(', ')})`);
