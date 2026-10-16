// Generates a 120-node (30 boundaries + 90 elements, nested 3 levels), ~200-edge scene in buildzr.scene/1.
// Usage: node scripts/make_synthetic.mjs [outfile]   (default public/scenes/synthetic-gen.scene.json)
import { writeFileSync } from 'node:fs';

const out = process.argv[2] ?? 'public/scenes/synthetic-gen.scene.json';
let seed = 12345;
const rnd = () => ((seed = (seed * 1664525 + 1013904223) >>> 0) / 2 ** 32);

const EW = 160, EH = 80, GAP = 20, PAD = 20, LAB = 50;
const bstyle = { color: '#000000', dash: [6, 4], fill: '#ffffff', fontSize: 13, stroke: '#888888' };
const estyle = { color: '#000000', fill: '#dddddd', fontSize: 14, stroke: '#9a9a9a' };
const nodes = [];
const pad2 = (n) => String(n).padStart(2, '0');
const boundary = (id, name, parent, x, y, w, h, tags) => nodes.push({
  id, modelId: String(nodes.length + 1), name, parent, role: 'boundary', type: 'DeploymentNode', shape: 'Box', x, y, w, h, style: bstyle,
  label: { anchor: 'bottom-left', lines: [{ text: name, weight: 'bold' }, { text: '[Deployment Node]', size: 11 }] }, tags,
});
const shapes = ['Box', 'RoundedBox', 'Cylinder', 'Person', 'Box'];
const types = ['Container', 'Container', 'Container', 'Person', 'Component'];
const elements = [];
const innerW = 3 * EW + 2 * GAP + 2 * PAD, innerH = PAD + 2 * EH + GAP + LAB;
const midW = 2 * innerW + GAP + 2 * PAD, midH = PAD + innerH + LAB;
const topW = midW + 2 * PAD, topH = PAD + 3 * midH + 2 * GAP + LAB;
const M = 20, TG = 60;
for (let t = 0; t < 3; t++) {
  const tx = M + t * (topW + TG), ty = M, tid = `t${t}`;
  boundary(tid, `Tier ${t}`, null, tx, ty, topW, topH, ['Element', 'Tier', `Tier ${t}`]);
  for (let m = 0; m < 3; m++) {
    const mx = tx + PAD, my = ty + PAD + m * (midH + GAP), mid = `${tid}/m${m}`;
    boundary(mid, `Zone ${t}.${m}`, tid, mx, my, midW, midH, ['Element', 'Zone', `Tier ${t}`]);
    for (let i = 0; i < 2; i++) {
      const ix = mx + PAD + i * (innerW + GAP), iy = my + PAD, iid = `${mid}/i${i}`;
      boundary(iid, `Pool ${t}.${m}.${i}`, mid, ix, iy, innerW, innerH, ['Element', 'Pool', i ? 'Blue' : 'Green']);
      for (let e = 0; e < 5; e++) {
        const col = e % 3, row = Math.floor(e / 3);
        const k = (t * 3 + m) * 2 + i;
        const tagsx = ['Element', i ? 'Blue' : 'Green', e % 2 ? 'Cache' : 'Service'];
        if (e === 2) tagsx.push('Database');
        const el = {
          id: `${iid}/n${e}`, modelId: String(nodes.length + 1), name: `Node ${pad2(k)}-${e}`, parent: iid, role: 'element', type: types[e], shape: shapes[e],
          x: ix + PAD + col * (EW + GAP), y: iy + PAD + row * (EH + GAP), w: EW, h: EH, style: estyle,
          label: { anchor: 'center', lines: [{ text: `Node ${pad2(k)}-${e}`, weight: 'bold' }, { text: `[${types[e]}: Tech ${e}]`, size: 12 }] },
          tags: tagsx, technology: `Tech ${e}`, description: `Synthetic element ${k}-${e}`,
        };
        if (el.shape === 'Cylinder') el.label.lines[1].text = '[Container]';
        nodes.push(el); elements.push(el);
      }
    }
  }
}
const edges = new Map();
let guard = 0;
while (edges.size < 200 && guard++ < 5000) {
  const a = elements[Math.floor(rnd() * elements.length)], b = elements[Math.floor(rnd() * elements.length)];
  if (a === b) continue;
  const id = `${a.id}->${b.id}`;
  if (edges.has(id)) continue;
  const right = b.x > a.x + a.w;
  const left = b.x + b.w < a.x;
  let pts;
  const ay = a.y + a.h / 2, by = b.y + b.h / 2;
  if (right || left) {
    const sx = right ? a.x + a.w : a.x, ex = right ? b.x : b.x + b.w;
    const mx = Math.round((sx + ex) / 2 + (rnd() - 0.5) * 20);
    pts = [[sx, ay], [mx, ay], [mx, by], [ex, by]];
  } else {
    const below = b.y > a.y;
    const sy = below ? a.y + a.h : a.y, ey = below ? b.y : b.y + b.h;
    const sx = a.x + a.w / 2, ex = b.x + b.w / 2;
    const my = Math.round((sy + ey) / 2);
    pts = sx === ex ? [[sx, sy], [ex, ey]] : [[sx, sy], [sx, my], [ex, my], [ex, ey]];
  }
  const e = {
    id, modelId: String(1000 + edges.size), source: a.id, target: b.id, points: pts, tags: ['Relationship'],
    style: { arrow: 'end', dash: [5, 5], stroke: '#707070' },
  };
  if (edges.size % 4 === 0) {
    const mid = pts[Math.floor(pts.length / 2)];
    e.description = 'Calls'; e.label = { lines: [{ size: 12, text: 'Calls' }], w: 40, h: 18, x: mid[0] - 20, y: mid[1] - 9 };
  }
  edges.set(id, e);
}
const sortKeys = (v) => Array.isArray(v) ? v.map(sortKeys) : v && typeof v === 'object'
  ? Object.fromEntries(Object.keys(v).sort().map((k) => [k, sortKeys(v[k])])) : v;
// Pre-order DFS with siblings sorted by id: the generation order already satisfies it ('t0' < 't1', 'i0' < 'i1', 'n0' < 'n1').
const W = M * 2 + 3 * topW + 2 * TG, H = M * 2 + topH;
const scene = {
  schema: 'buildzr.scene/1', view: 'synthetic-gen', kind: 'synthetic', title: 'Synthetic 120 nodes (viewer-local generator)',
  modelHash: 'sha256:unknown', layout: { engine: 'hand', inputHash: 'sha256:unknown', version: '0' }, bounds: [0, 0, W, H],
  nodes, edges: [...edges.values()].sort((p, q) => (p.id < q.id ? -1 : 1)),
};
writeFileSync(out, JSON.stringify(sortKeys(scene)) + '\n');
console.log(`${out}: ${nodes.length} nodes, ${edges.size} edges, bounds ${W}x${H}`);
