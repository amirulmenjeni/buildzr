// Settings panel: gear, popover, persistence, validation, keyboard, phone, axe (0 violations of any impact).
// Run: node tests/run.mjs --only settings --data <dir>
import { createRequire } from 'node:module';
import { newPage, open, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const KEY = 'buildzr-ui:settings';
const gear = (p) => p.locator('button.gear');
const panel = (p) => p.locator('[role=dialog][data-testid=settings-panel]');
const toggle = (p) => p.locator('[role=dialog] input[data-setting=zoomExpand]');
const setting = (p) => p.evaluate(() => window.__viewer.settings.zoomExpand);
const stored = (p) => p.evaluate((k) => localStorage.getItem(k), KEY);
const activeInfo = (p) => p.evaluate(() => ({ cls: document.activeElement?.className ?? '', tag: document.activeElement?.tagName, set: document.activeElement?.dataset?.setting ?? null }));

async function axe0(p, label, t) {
  await p.addScriptTag({ path: AXE });
  const res = await p.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ['violations'] });
    return r.violations.map((v) => `${v.id}[${v.impact}] ${v.nodes[0].target.join(' ')}`);
  });
  t.eq(res, [], `axe ${label}: violations`);
  t.note(`axe ${label}: ${res.length} violations`);
}

export default async function settings(browser, srv, F, name) {
  const t = new T(`settings:${name}`);
  const errors = [];

  // ---- desktop: defaults, toggle through the gear, persistence
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    t.eq(await setting(p), false, 'default: zoomExpand off');
    t.eq(await stored(p), null, 'nothing stored before the first change');
    t.eq(await gear(p).count(), 1, 'one gear button');
    t.eq(await gear(p).getAttribute('aria-label'), 'Settings', 'gear has an accessible name');
    t.eq(await gear(p).getAttribute('aria-expanded'), 'false', 'gear: aria-expanded false when closed');
    t.eq(await panel(p).count(), 0, 'panel closed at first');
    // position: bottom-right of the left panel
    const nb = await p.locator('nav.left').boundingBox(), gb = await gear(p).boundingBox();
    t.ok(nb.x + nb.width - (gb.x + gb.width) <= 16 && nb.y + nb.height - (gb.y + gb.height) <= 16, `gear at the bottom-right of the left panel (gap ${(nb.x + nb.width - gb.x - gb.width).toFixed(0)}, ${(nb.y + nb.height - gb.y - gb.height).toFixed(0)} px)`);
    t.ok(gb.x > nb.x + nb.width / 2, 'gear is in the right half of the left panel');
    await axe0(p, 'desktop/closed', t);
    await gear(p).click();
    t.eq(await panel(p).count(), 1, 'click opens the panel');
    t.eq(await gear(p).getAttribute('aria-expanded'), 'true', 'gear: aria-expanded true when open');
    t.ok((await panel(p).getAttribute('aria-labelledby')) !== null && (await p.locator('#' + (await panel(p).getAttribute('aria-labelledby'))).textContent()) === 'Settings', 'dialog is labelled "Settings"');
    t.eq((await p.locator('[role=dialog] label').first().textContent()), 'Zoom in to expand', 'label text');
    t.ok(((await p.locator('.setting-desc').first().textContent()) ?? '').length > 10, 'one-line description');
    t.eq((await toggle(p).getAttribute('aria-describedby')) === (await p.locator('.setting-desc').first().getAttribute('id')), true, 'toggle is described by the description');
    await axe0(p, 'desktop/open', t);
    t.eq((await activeInfo(p)).set, 'zoomExpand', 'focus moves to the toggle when the panel opens');
    await toggle(p).click();
    t.eq(await setting(p), true, 'toggle on');
    t.eq(JSON.parse(await stored(p)), { zoomExpand: true, theme: 'system' }, 'stored in localStorage');
    await p.keyboard.press('Escape');
    t.eq(await panel(p).count(), 0, 'Esc closes the panel');
    t.eq((await activeInfo(p)).cls.includes('gear'), true, 'Esc returns focus to the gear');
    // reload keeps the value
    await p.reload(); await p.waitForFunction(() => window.__viewer?.ready === true);
    t.eq(await setting(p), true, 'reload keeps the value');
    await gear(p).click();
    t.eq(await toggle(p).isChecked(), true, 'the toggle shows the stored value');
    await toggle(p).click();
    t.eq(await setting(p), false, 'toggle off');
    // click outside closes
    await p.mouse.click(700, 500);
    t.eq(await panel(p).count(), 0, 'a click outside closes the panel');
    await p.context().close();
  }

  // ---- keyboard only
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    await gear(p).focus();
    await p.keyboard.press('Enter');
    t.eq(await panel(p).count(), 1, 'Enter on the gear opens the panel');
    t.eq((await activeInfo(p)).set, 'zoomExpand', 'keyboard: focus on the toggle');
    await p.keyboard.press('Space');
    t.eq(await setting(p), true, 'Space toggles on');
    await p.keyboard.press('Space');
    t.eq(await setting(p), false, 'Space toggles off');
    await p.keyboard.press('Escape');
    t.eq(await panel(p).count(), 0, 'keyboard: Esc closes');
    t.eq((await activeInfo(p)).cls.includes('gear'), true, 'keyboard: focus back on the gear');
    await p.keyboard.press('Space');
    t.eq(await panel(p).count(), 1, 'Space on the gear opens it too');
    await p.context().close();
  }

  // ---- corrupted / hostile storage falls back to defaults without errors
  {
    const cases = ['not json {', '[1,2]', 'null', '"x"', '{"zoomExpand":"yes"}', '{"zoomExpand":1}', '{"unknown":true,"__proto__":{"zoomExpand":true}}', '{"zoomExpand":true,"unknown":7}'];
    const want = [false, false, false, false, false, false, false, true];
    for (let i = 0; i < cases.length; i++) {
      const p = await newPage(browser, errors);
      await p.addInitScript(([k, v]) => localStorage.setItem(k, v), [KEY, cases[i]]);
      await open(p, srv.url, '#/m');
      t.eq(await setting(p), want[i], `stored ${cases[i]} -> ${want[i]}`);
      await p.context().close();
    }
    // storage that throws
    const p = await newPage(browser, errors);
    await p.addInitScript(() => { Object.defineProperty(window, 'localStorage', { get() { throw new Error('blocked'); } }); });
    await open(p, srv.url, '#/m');
    t.eq(await setting(p), false, 'blocked storage: defaults');
    await gear(p).click(); await toggle(p).click();
    t.eq(await setting(p), true, 'blocked storage: the toggle still works for the session');
    await p.context().close();
  }

  // ---- phone
  {
    const p = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    await p.locator('button[aria-label="Open model navigation"]').click();
    await p.waitForTimeout(350);
    const nb = await p.locator('nav.left').boundingBox(), gb = await gear(p).boundingBox();
    t.ok(gb.width >= 44 && gb.height >= 44, `phone: gear is ${gb.width}x${gb.height} (>= 44)`);
    t.ok(Math.abs(nb.x + nb.width - (gb.x + gb.width)) <= 16 && Math.abs(nb.y + nb.height - (gb.y + gb.height)) <= 16, `phone: gear at the drawer's bottom-right (gap ${(nb.x + nb.width - gb.x - gb.width).toFixed(0)}, ${(nb.y + nb.height - gb.y - gb.height).toFixed(0)} px)`);
    await axe0(p, 'phone/closed', t);
    await gear(p).tap();
    t.eq(await panel(p).count(), 1, 'phone: tap opens the panel');
    const tb = await toggle(p).boundingBox(), lb = await p.locator('[role=dialog] label').first().boundingBox(), pb = await panel(p).boundingBox();
    t.ok(tb.width >= 14 && tb.width <= 16 && tb.height >= 14 && tb.height <= 16, `phone: toggle is ${tb.width}x${tb.height} (15 px, the label row is the 44 px target)`);
    t.ok(lb.height >= 44, `phone: label row is ${lb.height} px high`);
    t.ok(pb.x >= nb.x && pb.x + pb.width <= nb.x + nb.width + 0.5, 'phone: the panel stays inside the drawer');
    await axe0(p, 'phone/open', t);
    await toggle(p).tap();
    t.eq(await setting(p), true, 'phone: tap toggles');
    await p.keyboard.press('Escape');
    t.eq(await panel(p).count(), 0, 'phone: Esc closes the panel');
    t.eq(await p.locator('nav.left[data-open=true]').count(), 1, 'phone: Esc closed only the panel, not the drawer');
    await p.context().close();
  }

  // ---- every checkbox of the viewer (Settings, Inspector, Export) is one compact control, with a 44 px row on a phone
  for (const [kind, opts] of [['desktop', { viewport: { width: 1000, height: 700 } }], ['phone', { viewport: { width: 390, height: 844 }, hasTouch: true }]]) {
    const p = await newPage(browser, errors, opts);
    const phone = kind === 'phone';
    const tap = (loc, pos) => (phone ? loc.tap({ position: pos }) : loc.click({ position: pos }));
    await open(p, srv.url, `#/m?sel=${F.els[0].id}`);
    await p.waitForSelector(`[data-selected-id="${F.els[0].id}"]`);
    const surfaces = [
      ['inspector', p.locator('[data-testid=rolled]'), async () => {}],
      ['export', p.getByLabel('Transparent background'), async () => { await p.getByTestId('export-toggle').click(); await p.getByTestId('export').waitFor(); }],
      ['settings', toggle(p), async () => {
        if (phone) { await p.locator('button[aria-label="Open model navigation"]').click(); await p.waitForTimeout(350); }
        await gear(p).click(); await panel(p).waitFor();
      }],
    ];
    for (const [what, box, reveal] of surfaces) {
      await reveal();
      const f = await box.evaluate((e) => {
        const c = getComputedStyle(e), r = e.getBoundingClientRect(), row = (e.closest('label') ?? document.querySelector(`label[for="${e.id}"]`)).getBoundingClientRect();
        return { w: r.width, h: r.height, cw: parseFloat(c.width), ch: parseFloat(c.height), rowH: row.height, rowL: row.left, rowR: row.right, left: r.left, top: r.top, bottom: r.bottom };
      });
      t.ok(f.w >= 14 && f.w <= 16 && f.h >= 14 && f.h <= 16 && f.cw === 15 && f.ch === 15, `${kind} ${what}: the checkbox is ${f.w}x${f.h} (computed ${f.cw}x${f.ch})`);
      if (phone) t.ok(f.rowH >= 44 && f.rowL <= f.left && f.rowR <= 390, `phone ${what}: the label row is ${f.rowH} px high and holds the box`);
      const before = await box.isChecked();
      await box.focus();
      await p.keyboard.press('Space');
      t.eq(await box.isChecked(), !before, `${kind} ${what}: Space toggles it`);
      t.ok(await box.evaluate((e) => e.matches(':focus-visible') && parseFloat(getComputedStyle(e).outlineWidth) >= 2), `${kind} ${what}: a keyboard-focused box shows the focus ring`);
      await tap(box, { x: 7, y: 7 });
      t.eq(await box.isChecked(), before, `${kind} ${what}: a click on the box toggles it`);
      if (phone) {
        const lb = (await box.evaluate((e) => { const r = (e.closest('label') ?? document.querySelector(`label[for="${e.id}"]`)).getBoundingClientRect(); return { x: r.x, y: r.y, w: r.width, h: r.height }; }));
        await p.touchscreen.tap(lb.x + lb.w - 6, lb.y + lb.h - 4);
        t.eq(await box.isChecked(), !before, `phone ${what}: a tap at the far end of the 44 px row toggles it`);
        await box.uncheck(); if (before) await box.check();
      }
      if (what === 'export') await p.getByTestId('export-toggle').click();
      if (what === 'settings') await p.keyboard.press('Escape');
    }
    await p.context().close();
  }

  t.eq(errors, [], 'no console errors in settings tests');
  console.log(`  settings ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
