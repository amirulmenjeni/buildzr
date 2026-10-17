// Two sites in one store: `buildzr serve --store` serves the data set at / and at /pr/42/ with the real viewer.
// Makes two site folders (viewer bundle + the data dir), installs both into a new store through the Python store
// functions, starts the real `buildzr serve --store`, opens both sites and two viewerUrl links of each.
// Run: node tests/run.mjs --only viewerstore --data <dir>   (needs `uv` and the project's Python environment)
import { spawn, execFileSync } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { newPage, settle, T, ROOT, STATIC } from './lib.mjs';

const REPO = path.resolve(ROOT, '..');

const freePort = () => new Promise((resolve, reject) => {
  const s = net.createServer();
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
  s.on('error', reject);
});

async function waitFor(url, ms = 40000) {
  const end = Date.now() + ms;
  for (;;) {
    try { const r = await fetch(url); if (r.status === 200) return r.status; } catch { /* not up yet */ }
    if (Date.now() > end) throw new Error(`${url} did not answer in ${ms} ms`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

const INSTALL = `
import shutil, sys
from buildzr.site.store import Store
store = Store.open(sys.argv[1], create=True)
for i, (src, sp) in enumerate(((sys.argv[2], ""), (sys.argv[2], "pr/42"))):
    inc = sys.argv[1] + "/incoming/site" + str(i)
    shutil.copytree(src, inc)
    store.install(inc, sp)
`;

export default async function viewerstore(browser, srv, F, name) {
  const t = new T(`viewerstore:${name}`);
  const errors = [];
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'viewerstore-'));
  const site = path.join(tmp, 'site');
  fs.cpSync(STATIC, site, { recursive: true });
  fs.cpSync(srv.dir, path.join(site, 'data'), { recursive: true });
  const py = (process.env.BUILDZR_PY ?? `uv run --no-sync --project ${REPO} python`).split(' ');
  execFileSync(py[0], [...py.slice(1), '-c', INSTALL, path.join(tmp, 'store'), site], { stdio: ['ignore', 'ignore', 'inherit'] });
  const port = await freePort();
  const child = spawn(py[0], [...py.slice(1), '-m', 'buildzr.site.cli', 'serve', '--store', path.join(tmp, 'store'), '-p', String(port)],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  child.stderr.on('data', (d) => { stderr += d; });
  const base = `http://127.0.0.1:${port}`;
  try {
    t.eq(await waitFor(`${base}/_buildzr/v1/sites`), 200, `the store answers ${stderr}`);
    const sites = (await (await fetch(`${base}/_buildzr/v1/sites`)).json()).sites;
    t.eq(sites.map((s) => s.sitePath), ['', 'pr/42'], 'two sites listed');
    t.eq(sites.map((s) => s.modelHash), [F.model.modelHash, F.model.modelHash], 'both sites hold the data set');
    for (const s of sites) {
      const prefix = s.viewerUrl;
      const p = await newPage(browser, errors);
      await p.goto(base + prefix);
      await settle(p);
      t.ok(await p.locator('.react-flow__node').count() > 0, `${prefix}: the viewer drew nodes`);
      await p.context().close();
      const items = (await (await fetch(`${base}${s.apiUrl}elements?limit=200`)).json()).items;
      const drawn = items.filter((e) => F.byId.get(e.id) && ['Person', 'SoftwareSystem', 'Container', 'Component'].includes(e.type));
      const picks = [drawn.find((e) => e.childCount > 0), drawn.find((e) => e.childCount === 0)].filter(Boolean);
      t.ok(picks.length > 0, `${prefix}: elements to open`);
      for (const e of picks) {
        t.ok(e.viewerUrl.startsWith(prefix + '#/'), `${prefix}: viewerUrl ${e.viewerUrl} is under the site`);
        const q = await newPage(browser, errors);
        await q.goto(base + e.viewerUrl);
        await settle(q);
        t.eq(await q.locator(`[data-selected-id="${e.id}"]`).count(), 1, `${prefix}: ${e.id} is in the inspector`);
        t.eq(await q.locator(`[data-id="${e.id}"][data-selected="true"]`).count(), 1, `${prefix}: ${e.id} is selected on the canvas`);
        await q.context().close();
      }
    }
    const r = await fetch(`${base}/pr/42`, { redirect: 'manual' });
    t.eq([r.status, r.headers.get('location')], [308, '/pr/42/'], '/pr/42 redirects to /pr/42/');
  } finally {
    child.kill('SIGTERM');
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  t.eq(errors, [], 'no console errors');
  return t;
}
