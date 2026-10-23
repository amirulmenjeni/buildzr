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
    t.ok(tb.width >= 44 && tb.height >= 44, `phone: toggle is ${tb.width}x${tb.height} (>= 44)`);
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

  t.eq(errors, [], 'no console errors in settings tests');
  console.log(`  settings ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
