// viewerUrl round trip: the links the Model API gives for elements open the viewer at that element.
// Starts the real `buildzr serve` on a built workspace (viewer bundle + the data dir + build.json, served at
// /site/), asks the API for 5 elements and opens each `viewerUrl` in the browser.
// Run: node tests/run.mjs --only viewerurl --data <dir>   (needs `uv` and the project's Python environment)
import { spawn } from 'node:child_process';
import fs from 'node:fs';
import net from 'node:net';
import os from 'node:os';
import path from 'node:path';
import { newPage, settle, T, ROOT, STATIC } from './lib.mjs';

const REPO = path.resolve(ROOT, '..');
const DRAWN = new Set(['Person', 'SoftwareSystem', 'Container', 'Component']);
const DEPLOYMENT = new Set(['DeploymentNode', 'InfrastructureNode', 'ContainerInstance', 'SoftwareSystemInstance']);

const freePort = () => new Promise((resolve, reject) => {
  const s = net.createServer();
  s.listen(0, '127.0.0.1', () => { const { port } = s.address(); s.close(() => resolve(port)); });
  s.on('error', reject);
});

async function waitFor(url, ms = 40000) {
  const end = Date.now() + ms;
  for (;;) {
    try { const r = await fetch(url); if (r.status === 200 || r.status === 503) return r.status; } catch { /* not up yet */ }
    if (Date.now() > end) throw new Error(`${url} did not answer in ${ms} ms`);
    await new Promise((r) => setTimeout(r, 250));
  }
}

/** Five elements: one of each drawn type that exists, expandable ones and leaves, then evenly spread others. */
function pick(els, byId) {
  const chosen = [];
  const add = (e) => { if (e && !chosen.includes(e.id) && chosen.length < 5) chosen.push(e.id); };
  for (const type of ['Person', 'SoftwareSystem', 'Container', 'Component']) {
    add(els.find((e) => e.type === type && e.children.length > 0));
    add(els.find((e) => e.type === type && e.children.length === 0));
  }
  for (let i = 0; chosen.length < 5 && i < els.length; i++) add(els[Math.floor((i * els.length) / 5) % els.length]);
  for (const e of els) add(e); // a small model: the spread above can pick the same element twice
  return chosen.slice(0, 5).map((id) => byId.get(id));
}

export default async function viewerurl(browser, srv, F, name) {
  const t = new T(`viewerurl:${name}`);
  const errors = [];
  const site = fs.mkdtempSync(path.join(os.tmpdir(), 'viewerurl-'));
  fs.cpSync(STATIC, site, { recursive: true });
  fs.cpSync(srv.dir, path.join(site, 'data'), { recursive: true });
  // A built workspace: buildzr serve recognises it by build.json and serves it at /<name>/.
  fs.writeFileSync(path.join(site, 'build.json'), JSON.stringify({ name: 'site', status: 'ok', modelHash: F.model.modelHash }));
  const port = await freePort();
  const py = (process.env.BUILDZR_PY ?? `uv run --no-sync --project ${REPO} python`).split(' ');
  const child = spawn(py[0], [...py.slice(1), '-m', 'buildzr.site.cli', 'serve', site, '-p', String(port)], { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  child.stderr.on('data', (d) => { stderr += d; });
  const base = `http://127.0.0.1:${port}/site`;
  try {
    const status = await waitFor(`${base}/api/v1/`);
    t.eq(status, 200, `the API answers on the served copy of the site ${stderr}`);
    const list = await (await fetch(`${base}/api/v1/elements?limit=200`)).json();
    const drawn = F.els.filter((e) => DRAWN.has(e.type));
    const chosen = pick(drawn, F.byId);
    t.eq(chosen.length, Math.min(5, drawn.length), 'five elements picked');
    t.eq(list.modelHash, F.model.modelHash, 'the API reads the same model as the viewer');
    for (const e of chosen) {
      const ans = await (await fetch(`${base}/api/v1/element?id=${encodeURIComponent(e.id)}`)).json();
      const link = ans.element.viewerUrl;
      t.ok(typeof link === 'string' && link.startsWith('/site/#/'), `${e.id}: viewerUrl ${link}`);
      const expanded = e.children.length > 0 ? e.id : (e.parent ?? '');
      t.eq(link, `/site/#/m${expanded ? '/' + expanded : ''}?sel=${e.id}`, `${e.id}: the link follows the grammar`);
      const p = await newPage(browser, errors);
      await p.goto(new URL(link, base).href);
      await settle(p);
      const hash = await p.evaluate(() => location.hash);
      t.eq(hash, `#/m${expanded ? '/' + expanded : ''}?sel=${e.id}`, `${e.id}: the viewer keeps the link's state`);
      t.eq(await p.locator(`[data-selected-id="${e.id}"]`).count(), 1, `${e.id}: the inspector shows it`);
      t.eq(await p.locator(`[role=treeitem][data-id="${e.id}"] > .row.selected`).count(), 1, `${e.id}: its tree row is selected`);
      t.eq(await p.locator(`[data-id="${e.id}"][data-selected="true"]`).count(), 1, `${e.id}: its box on the canvas is selected`);
      if (expanded) t.eq(await p.locator(`[data-id="${expanded}"][data-expanded="true"]`).count(), 1, `${e.id}: ${expanded} is expanded`);
      else t.eq(await p.locator('[data-expanded="true"]').count(), 0, `${e.id}: the landscape is shown`);
      await p.context().close();
    }
    // Deployment elements: the link opens the first deployment view that shows the element, with it selected.
    const deployed = F.model.elements.filter((e) => DEPLOYMENT.has(e.type) && e.views.length > 0);
    for (const e of [deployed.find((x) => x.type === 'DeploymentNode'), deployed.find((x) => x.instanceOf)].filter(Boolean)) {
      const ans = await (await fetch(`${base}/api/v1/element?id=${encodeURIComponent(e.id)}`)).json();
      const link = ans.element.viewerUrl;
      t.eq(link, `/site/#/v/${e.views[0]}?sel=${e.id}`, `${e.id}: the link opens its deployment view`);
      const p = await newPage(browser, errors);
      await p.goto(new URL(link, base).href);
      await settle(p);
      t.eq(await p.evaluate(() => location.hash), `#/v/${e.views[0]}?sel=${e.id}`, `${e.id}: the viewer keeps the link's state`);
      t.eq(await p.locator(`[data-selected-id="${e.id}"]`).count(), 1, `${e.id}: the inspector shows it`);
      t.eq(await p.locator(`[data-id="${e.id}"][data-selected="true"]`).count(), 1, `${e.id}: its box on the canvas is selected`);
      await p.context().close();
    }
  } finally {
    child.kill('SIGTERM');
    fs.rmSync(site, { recursive: true, force: true });
  }
  t.eq(errors, [], 'no console errors');
  return t;
}
