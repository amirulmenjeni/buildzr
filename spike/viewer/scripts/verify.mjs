// Usage (from spike/viewer): npm run build && node scripts/verify.mjs
// Env: PLAYWRIGHT_BROWSERS_PATH must point at the shared cache. Serves dist/ with a tiny static server.
import http from 'node:http';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import zlib from 'node:zlib';
import { chromium } from 'playwright';

const DIST = path.resolve('dist');
const SHOTS = path.join(os.tmpdir(), 'spike-shots');
fs.mkdirSync(SHOTS, { recursive: true });
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json' };
const server = http.createServer((req, res) => {
  const f = path.join(DIST, decodeURIComponent(new URL(req.url, 'http://x').pathname).replace(/^\/$/, '/index.html'));
  if (!f.startsWith(DIST) || !fs.existsSync(f)) { res.writeHead(404); return res.end(); }
  res.writeHead(200, { 'content-type': MIME[path.extname(f)] ?? 'application/octet-stream' });
  fs.createReadStream(f).pipe(res);
});
await new Promise((r) => server.listen(0, r));
const BASE = `http://localhost:${server.address().port}/`;
const index = JSON.parse(fs.readFileSync(path.join(DIST, 'scenes/index.json'), 'utf8'));
const browser = await chromium.launch();
let failures = 0;
const fail = (m) => { failures++; console.log('FAIL: ' + m); };

const newPage = async () => {
  const p = await browser.newPage({ viewport: { width: 1600, height: 1000 } });
  p.on('pageerror', (e) => fail('pageerror ' + e.message));
  return p;
};
const open = async (p, view, hashExtra = '') => {
  await p.goto(`${BASE}#/v/${encodeURIComponent(view)}${hashExtra}`);
  await p.reload(); // make sure we start from the hash state
  await p.waitForFunction(() => window.__spike.ready, null, { timeout: 30000 });
};
const record = (p) => p.evaluate(() => ({
  store: window.__spike.positions(),
  dom: Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map((n) => {
    const r = n.getBoundingClientRect(); return [n.dataset.id, [r.x, r.y, r.width, r.height]];
  })),
  opac: Object.fromEntries([...document.querySelectorAll('.react-flow__node > div')].map((n) => [n.dataset.id, getComputedStyle(n).opacity])),
  eopac: [...document.querySelectorAll('.react-flow__edge-path')].map((n) => getComputedStyle(n).opacity),
}));
const setHash = async (p, h) => { await p.evaluate((x) => { location.hash = x; }, h); await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)))); };

// ---- 1. position invariance under filtering
const rows = [];
const SEARCH = {}, TAGS = {};
for (const e of index) {
  // derive a selective query and two tags from the scene itself
  const sc = JSON.parse(fs.readFileSync(path.join(DIST, 'scenes', e.file), 'utf8'));
  const els = sc.nodes.filter((n) => n.role === 'element');
  SEARCH[e.view] = (els[Math.floor(els.length / 2)] ?? sc.nodes[0]).name.toLowerCase(); // full name of a middle element (selective)
  const cnt = {}; for (const n of sc.nodes) for (const t of n.tags) cnt[t] = (cnt[t] ?? 0) + 1;
  const cand = Object.entries(cnt).filter(([, c]) => c < sc.nodes.length).sort((a, b) => Math.abs(a[1] - sc.nodes.length / 3) - Math.abs(b[1] - sc.nodes.length / 3)).map(([t]) => t);
  const covers = (ts) => sc.nodes.every((n) => n.tags.some((t) => ts.includes(t)));
  TAGS[e.view] = [cand[0], cand.slice(1).find((t) => !covers([cand[0], t])) ?? cand[0]];
}
for (const e of index) {
  const p = await newPage();
  await open(p, e.view);
  const base = await record(p);
  const v = encodeURIComponent(e.view);
  const [t1, t2] = TAGS[e.view] ?? [];
  const steps = {
    search: `#/v/${v}?q=${encodeURIComponent(SEARCH[e.view] ?? 'a')}`,
    'tags-or': `#/v/${v}?tags=${encodeURIComponent(t1 + ',' + t2)}&mode=or`,
    'tags-and': `#/v/${v}?tags=${encodeURIComponent(t1 + ',' + t2)}&mode=and`,
    'search+tags': `#/v/${v}?q=${encodeURIComponent(SEARCH[e.view] ?? 'a')}&tags=${encodeURIComponent(t1)}&mode=or`,
  };
  for (const [name, h] of Object.entries(steps)) {
    await setHash(p, h);
    const r = await record(p);
    let storeDiff = 0, domDiff = 0, maxDom = 0;
    for (const id of Object.keys(base.store)) {
      const a = base.store[id], b = r.store[id];
      if (!b || a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h) storeDiff++;
      const da = base.dom[id], db = r.dom[id];
      if (!db) { domDiff++; continue; }
      const m = Math.max(...da.map((x, i) => Math.abs(x - db[i])));
      maxDom = Math.max(maxDom, m);
      if (m > 0.01) domDiff++;
    }
    if (Object.keys(r.store).length !== Object.keys(base.store).length) storeDiff++;
    const dimmed = Object.values(r.opac).filter((o) => parseFloat(o) < 0.5).length;
    const edgesDimmed = r.eopac.filter((o) => parseFloat(o) < 0.5).length;
    const hit = Object.values(r.opac).filter((o) => parseFloat(o) >= 0.5).length;
    rows.push({ view: e.view, step: name, nodes: Object.keys(r.store).length, dimmedNodes: dimmed, undimmedNodes: hit, dimmedEdges: edgesDimmed, storeDiff, domDiff, maxDomDelta: maxDom.toFixed(4) });
    if (storeDiff) fail(`${e.view}/${name}: store positions changed`);
    if (domDiff) fail(`${e.view}/${name}: DOM rects changed (>0.01px)`);
    if (dimmed === 0) fail(`${e.view}/${name}: no node opacity changed`);
  }
  await p.close();
}
console.table(rows);

// ---- 1b. label overflow: rendered width of each label line vs node width
const overflow = [];
for (const e of index) {
  const p = await newPage();
  await open(p, e.view);
  await p.evaluate(() => document.fonts.ready);
  const r = await p.evaluate(() => {
    const out = { lines: 0, over: [], fontOk: document.fonts.check('14px Inter') && document.fonts.check('bold 14px Inter') };
    for (const n of document.querySelectorAll('.react-flow__node')) {
      const box = n.firstElementChild;
      const scale = n.getBoundingClientRect().width / box.offsetWidth; // viewport zoom
      for (const d of box.querySelectorAll('div > div')) {
        if (d.children.length || !d.textContent) continue;
        const rg = document.createRange(); rg.selectNodeContents(d);
        const w = rg.getBoundingClientRect().width / scale;
        out.lines++;
        if (w > box.offsetWidth + 1) out.over.push(`${n.dataset.id.split('/').pop()}: "${d.textContent}" ${w.toFixed(1)} > ${box.offsetWidth}`);
      }
    }
    return out;
  });
  overflow.push({ view: e.view, lines: r.lines, overflowing: r.over.length, fontOk: r.fontOk });
  if (r.over.length) console.log(`overflow ${e.view}:\n  ` + r.over.slice(0, 8).join('\n  '));
  await p.close();
}
console.table(overflow);

// ---- 2. screenshots
const shot = async (view, name, hash = '', clip) => {
  const p = await newPage();
  await open(p, view, hash);
  await p.screenshot({ path: `${SHOTS}/${name}.png`, clip });
  await p.close();
};
for (const e of index) await shot(e.view, `viewer-${e.view}`);
for (const v of ['aws-mini', 'synthetic-gen', 'aws-deployment-view', 'synthetic-120']) {
  if (!index.some((e) => e.view === v)) continue;
  await shot(v, `viewer-${v}-filtered`, '?tags=' + encodeURIComponent(TAGS[v][0]) + '&q=' + encodeURIComponent(SEARCH[v]));
}
// zoomed crops on an edge entering a nested box (aws: web-application -> database-schema crosses 3 boundaries); with and without the edge zIndex
for (const [name, qs] of [['viewer-edge-crossing-nested', ''], ['viewer-edge-crossing-nested-nozindex', '?nozindex=1']]) {
  const p = await newPage();
  await p.goto(`${BASE}${qs}#/v/aws-mini`);
  await p.waitForFunction(() => window.__spike.ready, null, { timeout: 30000 });
  await p.addStyleTag({ content: '.toolbar{display:none}' });
  for (let i = 0; i < 3; i++) await p.click('.react-flow__controls-zoomin');
  await p.waitForTimeout(300);
  const box = await p.locator('.edge-label[data-edge*="database-schema"]').boundingBox();
  await p.screenshot({ path: `${SHOTS}/${name}.png`, clip: { x: Math.max(0, box.x - 300), y: Math.max(0, box.y - 120), width: 900, height: 350 } });
  await p.close();
}

// ---- 3. render time + filter toggle (synthetic)
const timing = {};
for (const e of index.filter((x) => x.view === 'synthetic-gen' || /synthetic-120/.test(x.view))) {
  const runs = [];
  for (let i = 0; i < 5; i++) {
    const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 } }); // cold: new context, no cache
    const p = await ctx.newPage();
    await p.goto(`${BASE}#/v/${encodeURIComponent(e.view)}`);
    await p.waitForFunction(() => window.__spike.ready, null, { timeout: 60000 });
    runs.push(await p.evaluate(() => ({ init: window.__spike.metrics.initializedAtMs, paint: window.__spike.metrics.firstPaintAfterInitMs, hook: window.__spike.metrics.hookInitialized })));
    if (i === 4) {
      const toggles = [];
      const tag = TAGS[e.view][0];
      for (let k = 0; k < 10; k++) {
        const ms = await p.evaluate(async (t) => {
          const chip = document.querySelector(`.chip[data-tag="${t ?? document.querySelector('.chip')?.dataset.tag}"]`);
          const t0 = performance.now(); chip.click();
          await new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r)));
          return performance.now() - t0;
        }, tag);
        toggles.push(ms);
      }
      timing[e.view + ':toggle'] = toggles;
    }
    await ctx.close();
  }
  timing[e.view] = runs;
}
const med = (a) => [...a].sort((x, y) => x - y)[Math.floor(a.length / 2)];
for (const [k, v] of Object.entries(timing)) {
  if (k.endsWith(':toggle')) console.log(`${k}: filter toggle to 2nd frame ms median=${med(v).toFixed(1)} all=${v.map((x) => x.toFixed(0)).join(',')}`);
  else console.log(`${k}: nav-start -> nodes initialised ms median=${med(v.map((r) => r.init)).toFixed(0)} (runs ${v.map((r) => r.init.toFixed(0))}); -> 2 frames later median=${med(v.map((r) => r.paint)).toFixed(0)}; hookInitialized=${v.map((r) => r.hook)}`);
}

// ---- 5. keyboard
{
  const p = await newPage();
  await open(p, 'aws-mini');
  const info = [];
  await p.focus('body');
  for (let i = 0; i < 25; i++) {
    await p.keyboard.press('Tab');
    info.push(await p.evaluate(() => { const a = document.activeElement; return (a.dataset?.id ?? a.dataset?.testid ?? a.tagName + '.' + a.className).slice(0, 60) + (a.closest('.react-flow__node') ? ' [node]' : ''); }));
  }
  console.log('Tab order:', info.map((x, i) => `${i + 1}:${x}`).join(' | '));
  // focus first node, then Enter and arrows
  await p.evaluate(() => document.querySelector('.react-flow__node').focus());
  const before = await record(p);
  const vp0 = await p.evaluate(() => document.querySelector('.react-flow__viewport').style.transform);
  await p.keyboard.press('Enter');
  const sel = await p.evaluate(() => [...document.querySelectorAll('.react-flow__node.selected')].map((n) => n.dataset.id));
  await p.keyboard.press('ArrowRight'); await p.keyboard.press('ArrowDown');
  const after = await record(p);
  const vp1 = await p.evaluate(() => document.querySelector('.react-flow__viewport').style.transform);
  const moved = Object.keys(before.store).some((id) => before.store[id].x !== after.store[id].x || before.store[id].y !== after.store[id].y);
  console.log('Enter selects:', sel, '| arrows moved nodes:', moved, '| viewport changed:', vp0 !== vp1, '| focused after arrows:', await p.evaluate(() => document.activeElement.dataset?.id));
  await p.close();
}

// ---- 4. bundle size (fonts listed separately)
{
  const assets = path.join(DIST, 'assets');
  const groups = { 'js+css+html': [0, 0], 'fonts (woff2)': [0, 0], 'fonts (woff, fallback)': [0, 0] };
  for (const f of fs.readdirSync(assets).concat(['../index.html'])) {
    const b = fs.readFileSync(path.join(assets, f));
    const g = zlib.gzipSync(b, { level: 9 }).length;
    const k = f.endsWith('.woff2') ? 'fonts (woff2)' : f.endsWith('.woff') ? 'fonts (woff, fallback)' : 'js+css+html';
    groups[k][0] += b.length; groups[k][1] += g;
    console.log(`bundle ${path.basename(f)}: raw ${b.length} gzip-9 ${g}`);
  }
  for (const [k, v] of Object.entries(groups)) console.log(`bundle GROUP ${k}: raw ${v[0]} gzip-9 ${v[1]}`);
}
await browser.close(); server.close();
console.log(failures ? `\n${failures} FAILURE(S)` : '\nALL CHECKS PASSED');
process.exit(failures ? 1 : 0);
