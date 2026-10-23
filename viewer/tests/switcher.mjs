// The workspace switcher for data an embedding page sends: several workspaces in one `buildzr:load` (a Run Code
// snippet that creates more than one). The selector is a native select in the navigation panel; it is not drawn for
// one workspace. Covers embed mode at 900 px and 360 px, axe in both themes, the keyboard, a broken workspace, no
// history entries, "Open in a new tab" (the new tab keeps the set) and the standalone viewer on a static host (no
// request for a list, no selector). The served catalogue is in workspaces.mjs.
// Run: node tests/run.mjs --only switcher --data <dir>
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { serve, newPage, open, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');

const PARENT = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Parent page</title></head><body style="margin:0">
<script>
window.msgs = [];
window.frame = (id, src, w, h) => {
  const f = document.createElement('iframe');
  f.id = id; f.src = src; f.title = 'Diagram ' + id; f.style.width = w + 'px'; f.style.height = h + 'px'; f.style.border = '1px solid #ccc';
  document.body.append(f);
  return f;
};
window.send = (id, msg) => document.getElementById(id).contentWindow.postMessage(msg, location.origin);
addEventListener('message', (e) => {
  const f = [...document.querySelectorAll('iframe')].find((x) => x.contentWindow === e.source);
  window.msgs.push({ from: f ? f.id : null, data: e.data });
});
</script></body></html>`;

function readFiles(dir) {
  const out = {};
  const walk = (d) => {
    for (const e of fs.readdirSync(d, { withFileTypes: true })) {
      const f = path.join(d, e.name);
      if (e.isDirectory()) walk(f);
      else if (e.name.endsWith('.json')) out[path.relative(dir, f).split(path.sep).join('/')] = fs.readFileSync(f, 'utf8');
    }
  };
  walk(dir);
  return out;
}

const ready = (fr) => fr.waitForFunction(() => window.__viewer?.ready === true && Object.keys(window.__viewer.positions()).length > 0, null, { timeout: 20000 });
const title = (fr) => fr.locator('header.top h1').textContent();
const msgs = (p, type) => p.evaluate((t) => window.msgs.filter((m) => m.data?.type === t).map((m) => m.data), type);

export default async function switcher(browser, srv, F, name) {
  const t = new T(`switcher:${name}`);
  const errors = [];
  const files = readFiles(srv.dir);
  // A second workspace: the same drawing under another name, so the title tells which one is shown.
  const rename = (n) => ({ ...files, [F.index.model.file]: JSON.stringify({ ...JSON.parse(files[F.index.model.file]), workspace: { name: n } }) });
  const A = { name: 'Shop', files: rename('Shop System') };
  const B = { name: 'Billing', files: rename('Billing System'), route: '#/m' };
  const BROKEN = { name: 'Ledger', files: { 'index.json': '{}' }, build: { status: 'broken', stage: 'model', errors: ['LedgerError: no such table'], workspace: 'Ledger' } };
  const own = await serve(srv.dir, '/', { 'parent.html': PARENT });

  const ctx = await browser.newContext({ viewport: { width: 1300, height: 1400 }, reducedMotion: 'reduce' });
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`console.${m.type()}: ${m.text()}`); });
  await p.goto(own.url + 'parent.html');
  await p.evaluate(() => window.frame('a', 'index.html?embed=1&theme=light', 900, 600));
  const fr = await (await p.$('#a')).contentFrame();
  await fr.waitForFunction(() => window.__viewer !== undefined);
  await p.waitForFunction(() => window.msgs.some((m) => m.data?.type === 'buildzr:ready'));
  const send = (msg) => p.evaluate(([m]) => window.send('a', m), [msg]);
  // Run an action that loads other data and wait for the viewer's `buildzr:loaded` that answers it, then for the canvas.
  const loads = () => p.evaluate(() => window.msgs.filter((m) => m.data?.type === 'buildzr:loaded').length);
  const after = async (action, canvas = true) => {
    const n = await loads();
    await action();
    await p.waitForFunction((n) => window.msgs.filter((m) => m.data?.type === 'buildzr:loaded').length > n, n, { timeout: 20000 });
    if (canvas) await ready(fr);
  };
  const drawer = async () => { if (!(await fr.locator('nav.left[data-open=true]').count())) await fr.locator('.menu').click(); };
  const switcherCount = () => fr.locator('[data-testid=workspace-switcher]').count();

  // ---- one workspace: no selector, in any way of sending it
  await after(() => send({ type: 'buildzr:load', workspaces: [A] }));
  await drawer();
  t.eq(await switcherCount(), 0, 'one workspace in workspaces: no selector');
  t.eq(await fr.getByLabel('Workspace').count(), 0, 'one workspace: nothing labelled Workspace');
  await after(() => send({ type: 'buildzr:load', files: A.files }));
  t.eq(await switcherCount(), 0, 'files only (the existing protocol): no selector');
  t.eq(await title(fr), 'Shop System', 'files only: drawn as before');

  // ---- two workspaces
  const hist0 = await fr.evaluate(() => history.length);
  await after(() => send({ type: 'buildzr:load', workspaces: [A, B], title: 'Example' }));
  t.eq(await title(fr), 'Shop System', 'the first workspace is shown');
  t.eq(await fr.locator('[data-testid=workspace-switcher]').isVisible(), false, 'the selector is in the closed navigation drawer, not on the page');
  await drawer();
  const sel = fr.getByLabel('Workspace');
  t.eq(await sel.count(), 1, 'a select labelled Workspace');
  t.eq(await sel.evaluate((s) => s.tagName), 'SELECT', 'a native select');
  t.eq(await sel.locator('option').allTextContents(), ['Shop', 'Billing'], 'options in the order sent');
  t.eq(await sel.inputValue(), 'Shop', 'the shown workspace is selected');
  t.eq((await msgs(p, 'buildzr:workspace')).at(-1), { type: 'buildzr:workspace', name: 'Shop' }, 'the parent is told which workspace is shown');

  await after(() => sel.selectOption('Billing'));
  t.eq(await title(fr), 'Billing System', 'picking Billing draws Billing');
  t.eq((await msgs(p, 'buildzr:workspace')).at(-1)?.name, 'Billing', 'the parent is told about the switch');
  t.eq(await fr.evaluate(() => location.hash.split('?')[0]), '#/m', 'the workspace opens on its own route');
  t.eq(await fr.evaluate(() => history.length), hist0, 'switching adds no history entry in an embed');
  t.eq(await fr.locator('[data-testid=live]').textContent(), 'Opened workspace Billing', 'announced to screen readers');
  t.eq(await fr.locator('nav.left[data-open=true]').count(), 0, 'the drawer closes after the choice, as for any navigation');
  await drawer();
  t.eq(await sel.inputValue(), 'Billing', 'the selector follows');
  t.eq(await sel.locator('option').allTextContents(), ['Shop', 'Billing'], 'the list stays');
  t.eq((await fr.locator('.react-flow__node').count()) > 0, true, 'the diagram is drawn');

  // ---- keyboard: the select takes focus and arrow keys change it
  await sel.focus();
  await after(() => p.keyboard.press('ArrowUp'));
  t.eq(await title(fr), 'Shop System', 'keyboard: ArrowUp on the select picks Shop');

  // ---- `active` opens the set on another one, a message route wins over the workspace's own
  await after(() => send({ type: 'buildzr:load', workspaces: [A, B], active: 'Billing', route: '#/m?sel=' + F.els[0].id }));
  t.eq(await title(fr), 'Billing System', 'active picks the workspace to show');
  t.eq(await fr.evaluate(() => location.hash.split('?')[1]), 'sel=' + F.els[0].id.replace(/[^/]+/g, encodeURIComponent), 'the route of the message is used');

  // ---- a broken workspace: its page has the selector, to leave it
  await after(() => send({ type: 'buildzr:load', workspaces: [A, BROKEN], active: 'Ledger' }), false);
  await fr.locator('[data-testid=broken-screen]').waitFor({ timeout: 8000 });
  t.eq(await fr.locator('[data-testid=broken-screen] [data-testid=workspace-switcher]').count(), 1, 'broken workspace: the selector is on the broken page');
  await after(() => fr.getByLabel('Workspace').selectOption('Shop'));
  t.eq(await title(fr), 'Shop System', 'leaving the broken workspace draws the other');
  await drawer();
  await after(() => fr.getByLabel('Workspace').selectOption('Ledger'), false);
  await fr.locator('[data-testid=broken-screen]').waitFor({ timeout: 8000 });
  t.ok(true, 'and back');

  // ---- axe, both themes, drawer open on the diagram and on the broken page
  await after(() => send({ type: 'buildzr:load', workspaces: [A, B] }));
  await drawer();
  for (const theme of ['light', 'dark']) {
    await send({ type: 'buildzr:theme', theme });
    await p.waitForTimeout(100);
    await fr.addScriptTag({ path: AXE }).catch(() => undefined);
    const v = await fr.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((x) => `${x.id}[${x.impact}]`));
    t.eq(v, [], `axe, ${theme}: violations with the selector`);
  }
  await send({ type: 'buildzr:theme', theme: 'light' });

  // ---- phone width: a 44 px control inside the drawer, nothing overflows
  await p.evaluate(() => { document.getElementById('a').style.width = '360px'; });
  await p.waitForTimeout(200);
  await drawer();
  const box = await fr.getByLabel('Workspace').boundingBox();
  t.ok(box.height >= 44, `phone: the select is a touch target (${box.height} px)`);
  const nav = await fr.locator('nav.left').boundingBox();
  t.ok(box.x >= nav.x && box.x + box.width <= nav.x + nav.width + 1, 'phone: the select is inside the drawer');
  t.eq(await fr.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, 'phone: no horizontal overflow');
  await after(() => fr.getByLabel('Workspace').selectOption('Billing'));
  t.eq(await title(fr), 'Billing System', 'phone: switching works');
  await p.evaluate(() => { document.getElementById('a').style.width = '900px'; });

  // ---- "Open in a new tab" keeps the set, with the workspace on screen
  await after(() => send({ type: 'buildzr:load', workspaces: [A, B], title: 'Example' }));
  await drawer();
  await after(() => fr.getByLabel('Workspace').selectOption('Billing'));
  const [tab] = await Promise.all([ctx.waitForEvent('page'), fr.locator('[data-testid=open-new-tab]').click()]);
  tab.on('pageerror', (e) => errors.push('tab pageerror: ' + e.message));
  await ready(tab);
  t.eq(await title(tab), 'Billing System', 'new tab: opens the workspace on screen');
  const tsel = tab.getByLabel('Workspace');
  t.eq(await tsel.locator('option').allTextContents(), ['Shop', 'Billing'], 'new tab: the switcher lists both');
  t.eq(await tsel.inputValue(), 'Billing', 'new tab: the shown one is selected');
  t.eq(await tab.evaluate(() => window.__viewer.embed), false, 'new tab: the full viewer');
  await tsel.selectOption('Shop');
  await ready(tab);
  t.eq(await title(tab), 'Shop System', 'new tab: switching works');
  const hash = await tab.evaluate(() => location.hash);
  t.ok(hash.startsWith('#/m'), `new tab: a route (${hash})`);
  t.eq(await tab.evaluate(() => history.length) >= 1, true, 'new tab: has history');
  await tab.reload(); // from the tab's own storage; the set is still all there
  await ready(tab);
  t.eq(await tab.getByLabel('Workspace').locator('option').allTextContents(), ['Shop', 'Billing'], 'new tab, reloaded: the switcher lists both');
  await p.close();
  await tab.reload();
  await ready(tab);
  t.eq(await tab.getByLabel('Workspace').count(), 1, 'after the opener closed, a reload still has the switcher');
  await ctx.close();
  own.close();

  // ---- the standalone viewer on a static host: one workspace, no list is ever asked for, no selector
  const q = await newPage(browser, errors);
  await open(q, srv.url, '#/m');
  t.eq(await q.locator('[data-testid=workspace-switcher]').count(), 0, 'static host: no selector');
  t.eq(await q.getByLabel('Workspace').count(), 0, 'static host: nothing labelled Workspace');
  t.eq(srv.requests.filter((r) => r.includes('_buildzr')), [], 'static host: the viewer asked for no list of workspaces');
  await q.context().close();

  t.eq(errors, [], 'no console errors');
  return t;
}
