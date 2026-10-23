// Broken workspaces: the viewer reads build.json first and says loudly when the workspace is broken.
// Three cases per data set: ok, broken with data (stage check: banner above a working diagram) and broken without
// data (stage model or layout: a full-page error, no diagram, no spinner, and data/ is never fetched).
// Run: node tests/run.mjs --only broken [--data <dir>]...
import path from 'node:path';
import { createRequire } from 'node:module';
import { serve, newPage, open, settle, hashOf, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');

const ERRORS = Array.from({ length: 12 }, (_, i) => `scene e/system-${i}: node <b>${i}</b> outside its frame`);
const BUILD = {
  ok: { status: 'ok', workspace: 'Shop', input: { file: 'shop.py' } },
  check: { status: 'broken', stage: 'check', errors: ERRORS, workspace: 'Shop', input: { file: 'shop.py' } },
  model: { status: 'broken', stage: 'model', errors: ['RuntimeError: boom', "shop.py, line 4: raise RuntimeError('boom')"], workspace: 'Shop', input: { file: 'shop.py' } },
  layout: { status: 'broken', stage: 'layout', errors: ERRORS, workspace: 'Shop', input: { file: 'nested/shop.py' } },
};

async function seriousAxe(p) {
  await p.addScriptTag({ path: AXE });
  return p.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ['violations'] });
    return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.nodes[0].target.join(' ')}`);
  });
}

const rect = (p, sel) => p.locator(sel).first().evaluate((e) => { const r = e.getBoundingClientRect(); return { top: r.top, bottom: r.bottom, left: r.left, right: r.right }; });

export default async function broken(browser, srv, F, name) {
  const t = new T(`broken:${name}`);
  const errors = [];
  const dir = srv.dir;

  // ---- ok: no banner, the diagram as before
  {
    const s = await serve(dir, '/', { 'build.json': JSON.stringify(BUILD.ok) });
    const p = await newPage(browser, errors);
    await open(p, s.url, '#/m');
    t.eq(await p.locator('[data-testid=broken-banner], [data-testid=broken-screen], [role=alert]').count(), 0, 'ok: no banner and no alert');
    t.ok((await p.locator('.react-flow__node').count()) > 0, 'ok: the diagram is drawn');
    t.ok(s.requests.indexOf('/build.json') >= 0 && s.requests.indexOf('/build.json') < s.requests.indexOf('/data/index.json'), 'ok: build.json is read before data/index.json');
    await p.context().close();
    s.close();
  }

  // ---- broken with data (stage check), desktop and phone
  for (const phone of [false, true]) {
    const label = phone ? 'check/phone' : 'check';
    const s = await serve(dir, '/', { 'build.json': JSON.stringify(BUILD.check) });
    const p = await newPage(browser, errors, phone ? { viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true } : {});
    await open(p, s.url, '#/m');
    const alert = p.locator('[role=alert]');
    t.eq(await alert.count(), 1, `${label}: one alert`);
    t.eq((await alert.textContent()).startsWith('This workspace is broken: the data failed its checks.'), true, `${label}: banner text`);
    t.ok((await p.locator('.react-flow__node').count()) > 0, `${label}: the diagram is still drawn below the banner`);
    t.eq(await p.locator('[data-testid=broken-banner] button[aria-label=Dismiss], [data-testid=broken-banner] .close').count(), 0, `${label}: the banner cannot be dismissed`);
    const banner = await rect(p, '.broken-banner');
    const top = await rect(p, 'header.top');
    t.ok(banner.top === 0 && banner.bottom <= top.top + 0.5, `${label}: banner above the toolbar, not over it (${banner.bottom} <= ${top.top})`);
    const canvas = await rect(p, 'main.center');
    t.ok(canvas.top >= top.bottom - 0.5, `${label}: the canvas starts below the toolbar`);
    const colours = await p.locator('.broken-banner').evaluate((e) => { const c = getComputedStyle(e); return [c.color, c.backgroundColor]; });
    t.eq(colours, ['rgb(255, 255, 255)', 'rgb(176, 0, 32)'], `${label}: white on dark red (7.4:1)`);
    const toggle = p.locator('.broken-toggle');
    t.eq(await toggle.textContent(), `Show the ${ERRORS.length} errors`, `${label}: the button says how many errors`);
    t.eq(await toggle.getAttribute('aria-expanded'), 'false', `${label}: the list starts closed`);
    await toggle.click();
    t.eq(await toggle.getAttribute('aria-expanded'), 'true', `${label}: the button opens the list`);
    const panel = p.locator('#broken-errors');
    t.eq(await panel.locator('pre').textContent(), ERRORS.join('\n'), `${label}: every error, as text (no HTML)`);
    t.eq(await p.locator('#broken-errors b').count(), 0, `${label}: error text is not rendered as HTML`);
    const scroll = await panel.evaluate((e) => getComputedStyle(e).overflowY);
    t.eq(scroll, 'auto', `${label}: the list scrolls`);
    t.ok((await p.locator('.react-flow__node').count()) > 0, `${label}: the diagram is still there with the list open`);
    t.eq(await seriousAxe(p), [], `${label}: no serious axe violations`);
    await toggle.click();
    t.eq(await panel.count(), 0, `${label}: the button closes the list`);
    // hash routes are unchanged: an element route opens as it does without the banner
    if (F.expandable.length) {
      const e = F.expandable[0];
      await open(p, s.url, '#/m/' + e);
      t.eq(await hashOf(p), '#/m/' + e, `${label}: hash route #/m/${e} kept`);
      t.eq(await p.locator('[role=alert]').count(), 1, `${label}: the banner stays after navigation`);
    }
    await p.context().close();
    s.close();
  }

  // ---- broken without data (stage model or layout): the full-page screen
  for (const stage of ['model', 'layout']) {
    const b = BUILD[stage];
    const s = await serve(dir, '/', { 'build.json': JSON.stringify(b) });
    const p = await newPage(browser, errors);
    await p.goto(s.url + '#/m');
    await p.waitForSelector('[data-testid=broken-screen]', { timeout: 20000 });
    const alert = p.locator('[role=alert]');
    t.eq(await alert.count(), 1, `${stage}: one alert`);
    t.eq(await alert.textContent(), `This workspace is broken: building it failed at the ${stage} step.`, `${stage}: banner text`);
    t.eq(await p.locator('.react-flow, .react-flow__node').count(), 0, `${stage}: no empty diagram`);
    t.eq(await p.getByText('Loading…').count(), 0, `${stage}: no spinner`);
    const shown = b.errors.slice(0, 10).join('\n');
    t.eq(await p.locator('pre.broken-list').textContent(), shown, `${stage}: the first errors in a monospaced block`);
    const mono = await p.locator('pre.broken-list').evaluate((e) => getComputedStyle(e).fontFamily);
    t.ok(/monospace/.test(mono), `${stage}: monospaced (${mono})`);
    t.eq(await p.locator('.broken-body h2').textContent(), b.errors.length > 10 ? `The first 10 of ${b.errors.length} errors` : 'The errors', `${stage}: how many errors`);
    t.eq((await p.locator('.broken-body p').textContent()).replace(/\s+/g, ' '),
      `Fix the error in ${b.input.file} and run buildzr build again, or restart buildzr serve.`, `${stage}: what to do`);
    t.eq(s.requests.filter((r) => r.startsWith('/data/')), [], `${stage}: data/ is never fetched`);
    t.eq(await seriousAxe(p), [], `${stage}: no serious axe violations`);
    await p.context().close();
    s.close();
  }

  t.eq(errors.filter((e) => !/Failed to load resource.*404/.test(e)), [], 'no console errors in the broken cases');
  t.note(`broken: ok, check (desktop + phone), model, layout on ${path.basename(dir)}`);
  return t;
}
