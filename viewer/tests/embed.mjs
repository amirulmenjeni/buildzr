// Embed mode in a real parent page: the postMessage protocol, the origin rule, the closed inspector, the theme message,
// two frames side by side, frame widths 360-1200 px, and "Open in a new tab" (the handoff, a reload, a closed opener).
// Run: node tests/run.mjs --only embed --data <dir>
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { serve, newPage, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');

const PARENT = `<!doctype html><html lang="en"><head><meta charset="utf-8"><title>Parent page</title></head><body style="margin:0">
<h1 style="font-size:16px">A docs page</h1>
<script>
window.msgs = [];
window.frame = (id, src, w, h, autoload, route) => {
  const f = document.createElement('iframe');
  f.id = id; f.src = src; f.title = 'Diagram ' + id; f.style.width = w + 'px'; f.style.height = h + 'px'; f.style.border = '1px solid #ccc';
  if (autoload) f.dataset.autoload = '1';
  if (route) f.dataset.route = route;
  document.body.append(f);
  return f;
};
addEventListener('message', (e) => {
  const f = [...document.querySelectorAll('iframe')].find((x) => x.contentWindow === e.source);
  window.msgs.push({ from: f ? f.id : null, origin: e.origin, data: e.data });
  if (e.data && e.data.type === 'buildzr:ready' && f && f.dataset.autoload) {
    f.contentWindow.postMessage({ type: 'buildzr:load', files: window.FILES, route: f.dataset.route || undefined, title: 'Example ' + f.id }, location.origin);
  }
});
</script></body></html>`;

/** Every file of a data dir, keyed by its path relative to the dir (what a page posts in `buildzr:load`). */
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

const frameOf = async (p, id) => (await p.$('#' + id)).contentFrame();
const readyIn = (fr) => fr.waitForFunction(() => window.__viewer?.ready === true && Object.keys(window.__viewer.positions()).length > 0, null, { timeout: 20000 });
const msgsOf = (p, type, from) => p.evaluate(([t, f]) => window.msgs.filter((m) => m.data?.type === t && (!f || m.from === f)), [type, from]);
const overflow = (fr) => fr.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);

export default async function embed(browser, srv, F, name) {
  const t = new T(`embed:${name}`);
  const errors = [];
  const files = readFiles(srv.dir);
  const own = serve(srv.dir, '/', { 'parent.html': PARENT });
  const s1 = await own;
  const landscape = JSON.parse(files[F.index.scenes.landscape.file]);
  const leaf = F.els.find((e) => !e.parent && !F.expandable.includes(e.id)) ?? F.els[0];
  const top = F.expandable.find((id) => !F.parentOf(id));
  const sel = leaf.id;

  const ctx = await browser.newContext({ viewport: { width: 1300, height: 1400 }, reducedMotion: 'reduce' });
  await ctx.addInitScript((f) => { window.FILES = f; }, files);
  const p = await ctx.newPage();
  p.on('pageerror', (e) => errors.push('pageerror: ' + e.message));
  p.on('console', (m) => { if (m.type() === 'error' || m.type() === 'warning') errors.push(`console.${m.type()}: ${m.text()}`); });
  await p.goto(s1.url + 'parent.html');
  const hist0 = await p.evaluate(() => history.length);
  await p.evaluate(([s]) => {
    window.frame('a', 'index.html?embed=1&theme=dark#/m?sel=' + encodeURIComponent(s), 900, 560, true);
    window.frame('b', 'index.html?embed=1&theme=light', 360, 560, true, '#/m');
  }, [sel]);
  const A = await frameOf(p, 'a'), B = await frameOf(p, 'b');
  await readyIn(A); await readyIn(B);

  // ---- protocol: ready, loaded, route
  t.eq((await msgsOf(p, 'buildzr:ready')).map((m) => [m.from, m.data.v, m.origin === new URL(s1.url).origin]).sort(), [['a', 1, true], ['b', 1, true]], 'ready from both frames, v 1, same origin');
  t.eq((await msgsOf(p, 'buildzr:loaded')).map((m) => [m.from, m.data.status]).sort(), [['a', 'ready'], ['b', 'ready']], 'loaded: ready');
  const routeA = (await msgsOf(p, 'buildzr:route', 'a')).at(-1)?.data;
  t.eq(routeA?.selection, sel, 'route message carries the selection of the route');
  t.eq(await A.evaluate(() => window.__viewer.embed), true, 'embed mode on');
  // ---- the diagram is drawn
  const drawn = await A.evaluate(() => document.querySelectorAll('.react-flow__node').length);
  t.eq(drawn, landscape.nodes.length, `frame a draws the landscape (${landscape.nodes.length} nodes)`);
  t.eq(await B.evaluate(() => document.querySelectorAll('.react-flow__node').length), landscape.nodes.length, 'frame b draws the landscape');
  // ---- no inspector on open, even with ?sel=
  t.eq(await A.evaluate(() => location.hash), '#/m?sel=' + sel.replace(/[^/]+/g, encodeURIComponent), 'the selection is applied');
  t.eq(await A.locator('aside.inspector').count(), 0, 'wide frame: no inspector on open');
  t.eq(await B.evaluate(() => document.querySelector('.sheet-wrap')?.dataset.sheet ?? 'none'), 'closed', 'narrow frame: the bottom sheet is closed on open');
  t.eq(await B.evaluate(() => document.querySelector('.app')?.dataset.phone ?? null), 'true', '360 px frame: phone layout');
  const targets = await B.evaluate(() => [...document.querySelectorAll('.menu, .searchbtn')].map((b) => { const r = b.getBoundingClientRect(); return Math.min(r.width, r.height); }));
  t.ok(targets.length === 2 && targets.every((x) => x >= 44), `360 px frame: menu and search buttons are 44 px touch targets (${targets})`);
  // ---- theme from the URL, then by message
  t.eq(await A.evaluate(() => document.documentElement.dataset.theme), 'dark', 'frame a: ?theme=dark');
  t.eq(await B.evaluate(() => document.documentElement.dataset.theme), 'light', 'frame b: ?theme=light');
  await p.evaluate(() => document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:theme', theme: 'light' }, location.origin));
  await A.waitForFunction(() => document.documentElement.dataset.theme === 'light');
  t.eq(await A.evaluate(() => window.__viewer.theme), 'light', 'theme message: light');
  await p.emulateMedia({ colorScheme: 'dark' });
  await p.evaluate(() => document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:theme', theme: 'system' }, location.origin));
  await A.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
  t.ok(true, 'theme message: system follows prefers-color-scheme (dark)');
  t.eq(await A.evaluate(() => localStorage.getItem('buildzr-ui:settings')), null, 'the forced theme is not stored');
  // ---- invalid messages and messages from another window are ignored
  const loadedBefore = (await msgsOf(p, 'buildzr:loaded', 'a')).length;
  await p.evaluate(() => {
    const w = document.getElementById('a').contentWindow;
    w.postMessage({ type: 'buildzr:load' }, location.origin);
    w.postMessage({ type: 'buildzr:load', files: { 'model.json': '{}' } }, location.origin);
    w.postMessage({ type: 'buildzr:theme', theme: 'blue' }, location.origin);
    w.postMessage('buildzr:theme', location.origin);
    w.postMessage({ type: 'buildzr:route', route: 'javascript:alert(1)' }, location.origin);
  });
  // the frame b posting to frame a: same origin, but not a's parent
  await B.evaluate(() => parent.document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:theme', theme: 'light' }, location.origin));
  await p.waitForTimeout(300);
  t.eq((await msgsOf(p, 'buildzr:loaded', 'a')).length, loadedBefore, 'invalid load messages are ignored');
  t.eq(await A.evaluate(() => [document.documentElement.dataset.theme, document.querySelectorAll('.react-flow__node').length]), ['dark', drawn], 'bad theme, a non-parent window: ignored; the diagram is still there');
  // ---- route message (focus), then clicks inside the frame do not step the parent's history
  if (top) {
    await A.evaluate(() => { window.__viewer.ready = false; });
    await p.evaluate((r) => document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:route', route: r }, location.origin), '#/m/' + top);
    await readyIn(A);
    t.eq(await A.evaluate(() => location.hash.split('?')[0]), '#/m/' + top, 'route message expands the frame');
    await p.waitForFunction((x) => window.msgs.filter((m) => m.from === 'a' && m.data?.type === 'buildzr:route').at(-1)?.data.path === x, top, { timeout: 3000 }).catch(() => undefined);
    t.eq((await msgsOf(p, 'buildzr:route', 'a')).at(-1)?.data.path, top, 'route message reported back');
  }
  await A.locator('.crumbs button').first().click();
  await readyIn(A);
  t.eq(await p.evaluate(() => history.length), hist0, 'the parent page history does not grow');
  t.eq(await B.evaluate(() => location.hash), '#/m', 'frame b keeps its own route (no shared state)');
  t.eq(await B.locator('.crumbs [aria-current=page]').textContent(), 'Landscape', 'frame b still on the landscape');
  // ---- an explicit selection opens the inspector; Esc closes it
  const box = await A.locator(`.react-flow__node[data-id="${sel}"]`).boundingBox();
  await A.locator(`.react-flow__node[data-id="${sel}"]`).click({ position: { x: Math.min(10, box.width / 2), y: box.height / 2 } });
  await A.locator('aside.inspector').waitFor({ timeout: 5000 });
  t.eq(await A.locator('aside.inspector [data-selected-id]').getAttribute('data-selected-id'), sel, 'a click opens the inspector on the element');
  await p.waitForFunction((s) => window.msgs.filter((m) => m.from === 'a' && m.data?.type === 'buildzr:route').at(-1)?.data.selection === s, sel, { timeout: 3000 }).catch(() => undefined);
  t.eq((await msgsOf(p, 'buildzr:route', 'a')).at(-1)?.data.selection, sel, 'selection change reported to the parent');
  await A.locator('aside.inspector').focus().catch(() => undefined);
  await p.keyboard.press('Escape');
  await p.waitForTimeout(150);
  t.eq(await A.locator('aside.inspector').count(), 0, 'Esc closes the inspector');
  // ---- widths 360 to 1200: no horizontal overflow; keyboard: Tab from the menu reaches the search button
  for (const w of [360, 480, 768, 1024, 1200]) {
    await p.evaluate((w) => { document.getElementById('a').style.width = w + 'px'; }, w);
    await p.waitForTimeout(150);
    t.eq(await overflow(A), 0, `frame ${w} px: no horizontal overflow`);
  }
  await A.locator('.menu').focus();
  await p.keyboard.press('Tab');
  t.ok(await A.evaluate(() => !!document.activeElement?.closest('.crumbs, .searchbtn')), 'Tab moves on from the menu button inside the frame');
  // axe in both themes, wide and narrow
  for (const [fr, label] of [[A, 'wide dark'], [B, 'narrow light']]) {
    await fr.addScriptTag({ path: AXE });
    const v = await fr.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((x) => `${x.id}[${x.impact}]`));
    t.eq(v, [], `axe ${label}: violations`);
  }

  // ---- a 360 px frame used with a mouse: a click on a collapsed frame expands it (a touch tap would select it)
  if (top) {
    await B.evaluate(() => { window.__viewer.ready = false; });
    const bb = await B.locator(`.react-flow__node[data-id="${top}"]`).boundingBox();
    await B.locator(`.react-flow__node[data-id="${top}"]`).click({ position: { x: bb.width / 2, y: Math.min(12, bb.height / 2) } });
    await readyIn(B);
    t.eq(await B.evaluate(() => location.hash.split('?')[0]), '#/m/' + top, 'narrow frame, mouse: a click expands the frame');
    t.eq(await B.evaluate(() => document.querySelector('.sheet-wrap')?.dataset.sheet), 'closed', 'narrow frame: expanding does not open the sheet');
  }

  // ---- Open in a new tab: visible and labelled at every width, reachable by keyboard
  for (const w of [360, 480, 768, 1024, 1200]) {
    await p.evaluate((w) => { document.getElementById('a').style.width = w + 'px'; }, w);
    await p.waitForTimeout(150);
    const b = A.locator('[data-testid=open-new-tab]');
    t.ok(await b.isVisible(), `frame ${w} px: Open in a new tab is visible`);
    const bb = await b.boundingBox();
    t.ok(bb.x + bb.width <= w + 1, `frame ${w} px: the button is inside the frame`);
    if (w <= 520) t.ok(bb.width >= 44 && bb.height >= 44, `frame ${w} px: the button is a 44 px touch target (${bb.width}x${bb.height})`);
    t.eq(await overflow(A), 0, `frame ${w} px: no horizontal overflow with the button`);
  }
  const nb = A.locator('[data-testid=open-new-tab]');
  t.eq(await nb.evaluate((b) => b.textContent.trim()), 'Open in a new tab', 'button label');
  t.ok(((await nb.getAttribute('title')) ?? '').length > 10, 'button tooltip');
  await A.locator('.menu').focus();
  let reached = false;
  for (let i = 0; i < 40 && !reached; i++) {
    await p.keyboard.press('Tab');
    reached = await A.evaluate(() => document.activeElement?.dataset.testid === 'open-new-tab');
  }
  t.ok(reached, 'Tab reaches Open in a new tab');
  // the new tab gets the data from the frame
  await A.evaluate(() => { window.__viewer.ready = false; });
  if (top) { await p.evaluate((r) => document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:route', route: r }, location.origin), '#/m/' + top); await readyIn(A); }
  const hashA = await A.evaluate(() => location.hash);
  const [tab] = await Promise.all([ctx.waitForEvent('page'), nb.click()]);
  tab.on('pageerror', (e) => errors.push('tab pageerror: ' + e.message));
  await readyIn(tab);
  const tu = new URL(tab.url());
  t.ok(/^[0-9a-f]{32}$/.test(tu.searchParams.get('handoff') ?? '') && !tu.searchParams.has('embed'), `new tab url: ${tu.search}`);
  t.eq(tu.hash, hashA, 'new tab opens on the frame\'s route');
  t.eq(await tab.evaluate(() => window.__viewer.embed), false, 'new tab: full viewer, not embedded');
  t.eq(await tab.title(), 'Example a', 'new tab: title from the parent page');
  t.ok(await tab.locator('nav.left').isVisible(), 'new tab: the model tree is there');
  t.eq((await msgsOf(p, 'buildzr:open', 'a')).length, 1, 'parent informed: buildzr:open');
  // reload works from the tab's own storage, even after the parent page is gone
  const id = tu.searchParams.get('handoff');
  t.ok(await tab.evaluate((id) => !!sessionStorage.getItem('buildzr-ui:handoff:' + id), id), 'new tab keeps the data for a reload');
  // a new run in the frame: the old id is unknown; a tab without its own copy is told so
  await p.evaluate(() => document.getElementById('a').contentWindow.postMessage({ type: 'buildzr:load', files: window.FILES }, location.origin));
  await tab.evaluate((id) => sessionStorage.removeItem('buildzr-ui:handoff:' + id), id);
  await tab.reload();
  await tab.locator('[data-testid=handoff-gone]').waitFor({ timeout: 8000 });
  t.ok(true, 'stale id (the frame re-ran): the tab says the diagram is no longer available');
  // a fresh tab, then the parent page closes: a reload still works from session storage
  await readyIn(A);
  const [tab2] = await Promise.all([ctx.waitForEvent('page'), A.locator('[data-testid=open-new-tab]').click()]);
  await readyIn(tab2);
  await p.close();
  await tab2.reload();
  await readyIn(tab2);
  t.eq(await tab2.evaluate(() => document.querySelectorAll('.react-flow__node').length) > 0, true, 'after the opener closed, a reload of the tab still draws (session storage)');
  // an id with no opener at all: the clear message, at once
  const lone = await ctx.newPage();
  const t0 = Date.now();
  await lone.goto(s1.url + 'index.html?handoff=' + 'b'.repeat(32));
  await lone.locator('[data-testid=handoff-gone]').waitFor({ timeout: 8000 });
  t.ok(Date.now() - t0 < 3000, `no opener: the message shows at once (${Date.now() - t0} ms)`);
  t.ok(((await lone.locator('[data-testid=handoff-gone]').textContent()) ?? '').includes('Open in a new tab'), 'the message says what to do');
  await ctx.close();

  // ---- another origin frames the viewer: no ready message reaches it, its load is ignored
  {
    const s2 = await serve(srv.dir, '/', { 'parent.html': PARENT.replace('location.origin);\n  }', "'*');\n  }") });
    const c2 = await browser.newContext({ reducedMotion: 'reduce' });
    await c2.addInitScript((f) => { window.FILES = f; }, files);
    const q = await c2.newPage();
    await q.goto(s2.url + 'parent.html');
    await q.evaluate((src) => window.frame('x', src, 800, 500, true), s1.url + 'index.html?embed=1');
    await q.waitForTimeout(1500);
    t.eq(await q.evaluate(() => window.msgs.length), 0, 'cross-origin parent: no message from the viewer');
    await q.evaluate(() => document.getElementById('x').contentWindow.postMessage({ type: 'buildzr:load', files: window.FILES }, '*'));
    await q.waitForTimeout(800);
    const fx = await frameOf(q, 'x');
    t.eq(await fx.evaluate(() => document.querySelectorAll('.react-flow__node').length), 0, 'cross-origin load is ignored');
    t.eq((await fx.locator('.fatal').textContent())?.trim(), 'Loading…', 'the frame keeps waiting');
    await c2.close();
    s2.close();
  }

  // ---- data=server: the frame reads data/ itself; the button opens the plain viewer
  {
    const c3 = await browser.newContext({ viewport: { width: 1000, height: 700 }, reducedMotion: 'reduce' });
    const q = await c3.newPage();
    await q.goto(s1.url + 'parent.html');
    await q.evaluate(() => window.frame('s', 'index.html?embed=1&data=server', 800, 500, false));
    const fs_ = await frameOf(q, 's');
    await readyIn(fs_);
    t.eq(await fs_.evaluate(() => document.querySelectorAll('.react-flow__node').length), landscape.nodes.length, 'data=server: draws from data/');
    const [tab3] = await Promise.all([c3.waitForEvent('page'), fs_.locator('[data-testid=open-new-tab]').click()]);
    await readyIn(tab3);
    t.eq(new URL(tab3.url()).search, '', 'data=server: the new tab is the plain viewer');
    t.eq(await tab3.evaluate(() => window.opener), null, 'data=server: opened without an opener');
    await c3.close();
  }

  // ---- standalone is unchanged: no embed button, the inspector column is there, history entries are pushed
  {
    const q = await newPage(browser, errors);
    await q.goto(s1.url + '#/m');
    await readyIn(q);
    t.eq(await q.locator('[data-testid=open-new-tab]').count(), 0, 'standalone: no Open in a new tab');
    t.eq(await q.locator('aside.inspector').count(), 1, 'standalone: inspector column');
    t.eq(await q.evaluate(() => window.__viewer.embed), false, 'standalone: embed off');
    await q.context().close();
  }
  s1.close();
  t.eq(errors, [], 'no console errors in embed');
  t.note(`embed ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
