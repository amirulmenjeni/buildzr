// Test helpers: static server (built viewer + a data dir mounted at /data/), browser, store snapshots.
import http from 'node:http';
import fs from 'node:fs';
import path from 'node:path';
import { chromium } from 'playwright';

export const ROOT = path.resolve(import.meta.dirname, '..');
export const STATIC = path.resolve(ROOT, '../buildzr/site/static');
const MIME = { '.html': 'text/html', '.js': 'text/javascript', '.css': 'text/css', '.json': 'application/json', '.woff2': 'font/woff2', '.txt': 'text/plain' };

/** Serve STATIC at `base` and `dataDir` at <base>data/. base is '/' or a subpath such as '/sub/'.
 * `files` adds files at <base><name> (e.g. { 'build.json': '{...}' }); `requests` lists every path asked for. */
export async function serve(dataDir, base = '/', files = {}) {
  const requests = [];
  // A built workspace always has build.json next to index.html: the data set's own, else an empty one.
  const own = path.resolve(dataDir, '..', 'build.json');
  files = { 'build.json': fs.existsSync(own) ? fs.readFileSync(own, 'utf8') : '{}', ...files };
  const server = http.createServer((req, res) => {
    let p = decodeURIComponent(new URL(req.url, 'http://x').pathname);
    requests.push(p);
    if (!p.startsWith(base)) { res.writeHead(404); return res.end(); }
    p = p.slice(base.length - 1);
    if (Object.hasOwn(files, p.slice(1))) {
      res.writeHead(200, { 'content-type': MIME[path.extname(p)] ?? 'application/octet-stream' });
      return res.end(files[p.slice(1)]);
    }
    const root = p.startsWith('/data/') ? path.resolve(dataDir) : STATIC;
    const rel = p.startsWith('/data/') ? p.slice(5) : p;
    const f = path.join(root, rel === '/' ? '/index.html' : rel);
    if (!f.startsWith(root) || !fs.existsSync(f) || fs.statSync(f).isDirectory()) { res.writeHead(404); return res.end(); }
    res.writeHead(200, { 'content-type': MIME[path.extname(f)] ?? 'application/octet-stream' });
    fs.createReadStream(f).pipe(res);
  });
  await new Promise((r) => server.listen(0, r));
  return { url: `http://localhost:${server.address().port}${base}`, requests, close: () => server.close() };
}

export const launch = () => chromium.launch();

export class T {
  constructor(name) { this.name = name; this.fails = 0; this.checks = 0; this.notes = []; }
  ok(cond, msg) { this.checks++; if (!cond) { this.fails++; console.log(`  FAIL [${this.name}] ${msg}`); } return cond; }
  eq(a, b, msg) { return this.ok(JSON.stringify(a) === JSON.stringify(b), `${msg}: got ${JSON.stringify(a)}, want ${JSON.stringify(b)}`); }
  note(s) { this.notes.push(s); console.log(`  ${s}`); }
}

export async function newPage(browser, errors, opts = {}) {
  const ctx = await browser.newContext({ viewport: { width: 1600, height: 1000 }, reducedMotion: 'reduce', ...opts });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`console.${m.type()}: ${m.text()}`); });
  return p;
}

export const open = async (p, url, hash = '') => {
  await p.goto(url + hash);
  await settle(p);
};
/** Wait until the camera request has been served and every node is measured. */
export const settle = async (p) => {
  await p.waitForFunction(() => window.__viewer?.ready === true && Object.keys(window.__viewer.positions()).length > 0, null, { timeout: 20000 });
  await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
};
/** Run an action that changes the camera/path and wait for it to settle. */
export const act = async (p, fn) => {
  await p.evaluate(() => { window.__viewer.ready = false; });
  await fn();
  await p.waitForFunction(() => window.__viewer.ready === true, null, { timeout: 20000 });
  await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
};

/** FRESH snapshot: React Flow store absolute positions + DOM rects, taken now. */
export const snapshot = (p) => p.evaluate(() => ({
  store: window.__viewer.positions(),
  dom: Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map((n) => {
    const r = n.getBoundingClientRect(); return [n.dataset.id, [r.x, r.y, r.width, r.height]];
  })),
  vp: window.__viewer.viewport(),
  opac: Object.fromEntries([...document.querySelectorAll('.react-flow__node > div')].map((n) => [n.dataset.id, parseFloat(getComputedStyle(n).opacity)])),
}));
export const hashOf = (p) => p.evaluate(() => location.hash);

/** A point inside the node's box whose topmost element belongs to that node (edges and children may cover parts of it). */
export async function hitPoint(p, id) {
  const pt = await p.evaluate((id) => {
    const el = document.querySelector(`.react-flow__node[data-id="${CSS.escape(id)}"]`);
    const r = el.getBoundingClientRect();
    for (const fy of [0.5, 0.15, 0.85, 0.3, 0.7]) for (const fx of [0.5, 0.15, 0.85, 0.3, 0.7, 0.05, 0.95]) {
      const x = r.x + r.width * fx, y = r.y + r.height * fy;
      const top = document.elementFromPoint(x, y);
      if (top && el.contains(top) && top.closest('.react-flow__node') === el) return [x, y];
    }
    return null;
  }, id);
  if (!pt) throw new Error(`no free point on node ${id}`);
  return pt;
}
export const mouseClick = async (p, id) => { const [x, y] = await hitPoint(p, id); await p.mouse.click(x, y); };
export const mouseDbl = async (p, id) => { const [x, y] = await hitPoint(p, id); await p.mouse.dblclick(x, y); };

// ---- zoom helpers shared by the zoom, label and expand tests
export const raf = (p, n = 3) => p.evaluate((n) => new Promise((r) => { const f = (i) => (i ? requestAnimationFrame(() => f(i - 1)) : r()); f(n); }), n);

/** Zoom about the canvas centre, instantly (what a wheel zoom does to the viewport, minus the animation). */
export async function zoomTo(p, z) {
  await p.evaluate((z) => {
    const v = window.__viewer.viewport();
    const el = document.querySelector('.react-flow');
    const cx = el.clientWidth / 2, cy = el.clientHeight / 2;
    const k = z / v.zoom;
    window.__viewer.setViewport({ zoom: z, x: cx - (cx - v.x) * k, y: cy - (cy - v.y) * k });
  }, z);
  await raf(p, 3);
  await p.waitForTimeout(25);
}


export const fitOf = async (p, srv, hash) => { await open(p, srv.url, hash); return (await snapshot(p)).vp.zoom; };

