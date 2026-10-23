// Two workspaces in one build output: `buildzr serve OUT` serves the data set at /shop/ and at /billing/ with the
// real viewer, and the viewer's workspace switcher lists them (also a broken third, and in embed mode), changes page
// when one is picked, and is not drawn for a build output with one workspace. Makes two built workspaces (viewer bundle + the data dir + build.json), starts the real
// `buildzr serve` on their build output, opens both workspaces and two viewerUrl links of each.
// Run: node tests/run.mjs --only workspaces --data <dir>   (needs `uv` and the project's Python environment)
import { spawn } from 'node:child_process';
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

export default async function workspaces(browser, srv, F, name) {
  const t = new T(`workspaces:${name}`);
  const errors = [];
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'workspaces-'));
  const out = path.join(tmp, 'build');
  for (const ws of ['shop', 'billing']) {
    const folder = path.join(out, ws);
    fs.cpSync(STATIC, folder, { recursive: true });
    fs.cpSync(srv.dir, path.join(folder, 'data'), { recursive: true });
    fs.writeFileSync(path.join(folder, 'build.json'), JSON.stringify({ name: ws, status: 'ok', modelHash: F.model.modelHash }));
  }
  const py = (process.env.BUILDZR_PY ?? `uv run --no-sync --project ${REPO} python`).split(' ');
  const port = await freePort();
  const child = spawn(py[0], [...py.slice(1), '-m', 'buildzr.site.cli', 'serve', out, '-p', String(port)],
    { stdio: ['ignore', 'ignore', 'pipe'] });
  let stderr = '';
  child.stderr.on('data', (d) => { stderr += d; });
  const base = `http://127.0.0.1:${port}`;
  try {
    t.eq(await waitFor(`${base}/_buildzr/v1/workspaces`), 200, `the server answers ${stderr}`);
    const sites = (await (await fetch(`${base}/_buildzr/v1/workspaces`)).json()).workspaces;
    t.eq(sites.map((s) => s.path), ['/billing/', '/shop/'], 'two workspaces listed');
    t.eq(sites.map((s) => s.status), ['ok', 'ok'], 'both are ok');
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
        t.ok(e.viewerUrl.startsWith(prefix + '#/'), `${prefix}: viewerUrl ${e.viewerUrl} is under the workspace`);
        const q = await newPage(browser, errors);
        await q.goto(base + e.viewerUrl);
        await settle(q);
        t.eq(await q.locator(`[data-selected-id="${e.id}"]`).count(), 1, `${prefix}: ${e.id} is in the inspector`);
        t.eq(await q.locator(`[data-id="${e.id}"][data-selected="true"]`).count(), 1, `${prefix}: ${e.id} is selected on the canvas`);
        await q.context().close();
      }
    }
    const r = await fetch(`${base}/shop`, { redirect: 'manual' });
    t.eq([r.status, r.headers.get('location')], [308, '/shop/'], '/shop redirects to /shop/');

    // ---- the switcher: the viewer learns where the list is from a header of build.json, then asks for it
    const bj = await fetch(`${base}/shop/build.json`);
    t.eq(bj.headers.get('x-buildzr-workspaces'), '../_buildzr/v1/workspaces', 'build.json says where the list of workspaces is');
    const ledger = path.join(out, 'ledger');
    fs.cpSync(STATIC, ledger, { recursive: true });
    fs.writeFileSync(path.join(ledger, 'build.json'), JSON.stringify({ name: 'ledger', workspace: 'Ledger', status: 'broken', stage: 'model', errors: ['LedgerError: no table'] }));
    const labelsOf = (loc) => loc.locator('option').allTextContents();
    {
      const p = await newPage(browser, errors);
      await p.goto(base + '/shop/');
      await settle(p);
      const sel = p.getByLabel('Workspace');
      t.eq(await labelsOf(sel), ['billing', 'Ledger (broken)', 'shop'], 'shop: the switcher lists every workspace, a broken one marked');
      t.eq(await sel.inputValue(), 'shop', 'shop: the shown workspace is selected');
      t.ok(await sel.isVisible(), 'wide viewer: the selector is in the left panel');
      await Promise.all([p.waitForURL((u) => u.pathname === '/billing/'), sel.selectOption('billing')]);
      await settle(p);
      t.ok(await p.locator('.react-flow__node').count() > 0, 'billing: drawn after the switch');
      t.eq(await p.getByLabel('Workspace').inputValue(), 'billing', 'billing: the selector follows');
      await Promise.all([p.waitForURL((u) => u.pathname === '/shop/'), p.goBack()]);
      t.ok(true, 'Back returns to the previous workspace');
      await settle(p);
      await Promise.all([p.waitForURL((u) => u.pathname === '/ledger/'), p.getByLabel('Workspace').selectOption('ledger')]);
      await p.locator('[data-testid=broken-screen]').waitFor({ timeout: 10000 });
      t.eq(await p.locator('[data-testid=broken-screen]').getByLabel('Workspace').inputValue(), 'ledger', 'broken workspace: the selector is on its page');
      await Promise.all([p.waitForURL((u) => u.pathname === '/shop/'), p.getByLabel('Workspace').selectOption('shop')]);
      await settle(p);
      t.ok(true, 'and leads out of it');
      await p.context().close();
    }
    {
      const p = await newPage(browser, errors, { viewport: { width: 390, height: 800 } });
      await p.goto(base + '/shop/#/m');
      await settle(p);
      t.eq(await p.getByLabel('Workspace').isVisible(), false, 'phone: the selector waits in the closed drawer');
      await p.getByLabel('Open model navigation').click();
      const box = await p.getByLabel('Workspace').boundingBox();
      t.ok(box && box.height >= 44, `phone: a touch target (${box?.height} px)`);
      await Promise.all([p.waitForURL((u) => u.pathname === '/billing/'), p.getByLabel('Workspace').selectOption('billing')]);
      await settle(p);
      t.eq(await p.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, 'phone: no horizontal overflow');
      await p.context().close();
    }
    {
      const p = await newPage(browser, errors);
      await p.goto(base + '/shop/?embed=1&data=server#/m');
      await settle(p);
      await p.locator('.menu').click();
      await Promise.all([p.waitForURL(`${base}/billing/?embed=1&data=server`), p.getByLabel('Workspace').selectOption('billing')]);
      await settle(p);
      t.eq(await p.evaluate(() => window.__viewer.embed), true, 'embed with data=server: still an embed after the switch');
      await p.context().close();
    }
    fs.rmSync(ledger, { recursive: true, force: true });

    // ---- one workspace in the build output: the viewer asks for the list and draws no selector
    const solo = path.join(tmp, 'solo');
    fs.cpSync(path.join(out, 'shop'), path.join(solo, 'shop'), { recursive: true });
    const port2 = await freePort();
    const child2 = spawn(py[0], [...py.slice(1), '-m', 'buildzr.site.cli', 'serve', solo, '-p', String(port2)], { stdio: 'ignore' });
    try {
      await waitFor(`http://127.0.0.1:${port2}/_buildzr/v1/workspaces`);
      const p = await newPage(browser, errors);
      await p.goto(`http://127.0.0.1:${port2}/shop/`);
      await settle(p);
      await p.waitForTimeout(500); // the list is asked for after the first draw
      t.eq(await p.locator('[data-testid=workspace-switcher]').count(), 0, 'one workspace: no selector');
      t.eq(await p.getByLabel('Workspace').count(), 0, 'one workspace: nothing labelled Workspace');
      await p.context().close();
    } finally {
      child2.kill('SIGTERM');
    }
  } finally {
    child.kill('SIGTERM');
    fs.rmSync(tmp, { recursive: true, force: true });
  }
  t.eq(errors, [], 'no console errors');
  return t;
}
