// Dynamic views: step through the interactions with the step bar. Only dynamic views have it; the default drawing is the
// one without it; a step marks its arrows and dims what comes later, the layout never moves; bounds, Play and Pause, the
// keyboard, reduced motion, both themes, an embedded frame and a phone; the camera follows the current step. Data sets without a dynamic view only check that
// nothing new shows. Run: node tests/run.mjs --only dynamic --data tests/site/fixtures/dynamic
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { newPage, open, act, hashOf, hitPoint, mouseClick, raf, settle, snapshot, T, zoomTo } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const bar = '[data-testid=steps]';
const btn = (id) => `[data-testid=steps-${id}]`;

/** Test-side steps: the orders of the scene's edges, numerically where they are numbers. */
function stepsOf(scene) {
  const orders = [...new Set(scene.edges.map((e) => e.order).filter((o) => o !== undefined && o !== null && o !== ''))];
  orders.sort((a, b) => a.localeCompare(b, 'en', { numeric: true }));
  return orders.map((o) => scene.edges.filter((e) => e.order === o));
}

/** What step k (1-based) should look like: edge id -> earlier | current | later, and the nodes no step up to k reaches. */
function expected(steps, k) {
  const edges = {};
  steps.forEach((s, i) => { for (const e of s) edges[e.id] = i + 1 < k ? 'earlier' : i + 1 === k ? 'current' : 'later'; });
  const reached = new Set(steps.slice(0, k).flat().flatMap((e) => [e.source, e.target]));
  const later = [...new Set(steps.flat().flatMap((e) => [e.source, e.target]))].filter((id) => !reached.has(id)).sort();
  return { edges, later };
}

/** On screen: each edge's data-step and opacity, each node's opacity, the current step's label. React Flow drops every arrow
 * for one frame when the boxes change (a selection does the same), so this waits a few frames first. */
const look = async (p) => { await raf(p, 3); return p.evaluate(() => ({
  edges: Object.fromEntries([...document.querySelectorAll('g.rolled-edge')].map((g) => [g.dataset.edge, [g.dataset.step ?? null, parseFloat(getComputedStyle(g).opacity)]])),
  nodes: Object.fromEntries([...document.querySelectorAll('.react-flow__node > div')].map((n) => [n.dataset.id, parseFloat(getComputedStyle(n).opacity)])),
  currentLabels: [...document.querySelectorAll('.edge-label[data-step=current]')].map((l) => l.dataset.edge).sort(),
  step: document.querySelector('[data-testid=steps]')?.dataset.step ?? null,
  count: document.querySelector('[data-testid=steps-count]')?.textContent ?? null,
  text: document.querySelector('[data-testid=steps-text]')?.textContent ?? null,
  live: document.querySelector('[data-testid=live]')?.textContent ?? '',
})); };
const stepOf = async (p) => Number(await p.locator(bar).getAttribute('data-step'));

/** Wait until the camera move of the last step is over (Canvas: StepCamera). */
const camDone = async (p) => { await p.waitForFunction(() => window.__viewer.stepCamera?.done ?? true, null, { timeout: 5000 }); await raf(p, 3); };
/** In page px: the part of the canvas that the step bar and the phone's sheet leave free, and the current step on screen (its
 * arrows, their labels and the boxes at both ends). Read from the DOM, not from the viewer's own numbers. */
const framing = (p) => p.evaluate(() => {
  const c = document.querySelector('.react-flow').getBoundingClientRect();
  let top = c.top, bottom = c.bottom;
  const b = document.querySelector('[data-testid=steps]')?.getBoundingClientRect();
  if (b && b.height > 0) top = Math.max(top, b.bottom);
  const sh = document.querySelector('.sheet-wrap[data-sheet]:not([data-sheet=closed])')?.getBoundingClientRect();
  if (sh && sh.height > 0) bottom = Math.min(bottom, sh.top);
  const rs = [];
  for (const g of document.querySelectorAll('g.rolled-edge[data-step=current]')) {
    rs.push(g.querySelector('.react-flow__edge-path').getBoundingClientRect());
    for (const id of g.dataset.edge.split('#')[0].split('->')) {
      const n = document.querySelector(`.react-flow__node[data-id="${CSS.escape(id)}"]`);
      if (n) rs.push(n.getBoundingClientRect());
    }
  }
  for (const l of document.querySelectorAll('.edge-label[data-step=current]')) rs.push(l.getBoundingClientRect());
  const box = rs.length ? [Math.min(...rs.map((r) => r.left)), Math.min(...rs.map((r) => r.top)), Math.max(...rs.map((r) => r.right)), Math.max(...rs.map((r) => r.bottom))] : null;
  return { free: [c.left, top, c.right, bottom], box, vp: window.__viewer.viewport(), cam: window.__viewer.stepCamera ?? {} };
});
const inside = (f) => !!f.box && f.box[0] >= f.free[0] - 0.5 && f.box[1] >= f.free[1] - 0.5 && f.box[2] <= f.free[2] + 0.5 && f.box[3] <= f.free[3] + 0.5;
const sameVp = (a, b) => Math.abs(a.x - b.x) < 0.5 && Math.abs(a.y - b.y) < 0.5 && Math.abs(a.zoom - b.zoom) < 1e-4;
const r1 = (f) => JSON.stringify(f.box?.map(Math.round)) + ' in ' + JSON.stringify(f.free.map(Math.round));

const rgb = (s) => s.match(/[\d.]+/g).slice(0, 3).map(Number);
const lum = ([r, g, b]) => { const f = (c) => { c /= 255; return c <= 0.03928 ? c / 12.92 : ((c + 0.055) / 1.055) ** 2.4; }; return 0.2126 * f(r) + 0.7152 * f(g) + 0.0722 * f(b); };
const contrast = (a, b) => { const [x, y] = [lum(rgb(a)), lum(rgb(b))].sort((u, v) => v - u); return (x + 0.05) / (y + 0.05); };

export default async function dynamic(browser, srv, F, name) {
  const t = new T(`dynamic:${name}`);
  const errors = [];
  const views = F.model.views.filter((v) => v.kind === 'dynamic');
  const scene = (v) => JSON.parse(fs.readFileSync(path.join(srv.dir, F.index.scenes[v.scene].file), 'utf8'));
  const nameOf = (id) => F.model.elements.find((e) => e.id === id)?.name ?? id;

  // ---- 1. the bar is on dynamic views only
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    t.eq(await p.locator(bar).count(), 0, 'model canvas: no step bar');
    for (const v of F.model.views) {
      await open(p, srv.url, `#/v/${v.key}`);
      t.eq(await p.locator(bar).count(), v.kind === 'dynamic' ? 1 : 0, `${v.key} (${v.kind}): step bar ${v.kind === 'dynamic' ? 'shown' : 'not shown'}`);
    }
    await p.context().close();
  }
  if (!views.length) { t.note('no dynamic view: skipped'); t.eq(errors, [], 'no console errors'); return t; }

  const v = views.reduce((a, b) => (stepsOf(scene(b)).length > stepsOf(scene(a)).length ? b : a));
  const sc = scene(v);
  const steps = stepsOf(sc);
  const n = steps.length;
  const other = views.find((x) => x.key !== v.key);
  t.note(`${v.key}: ${n} steps (${steps.map((s) => s.map((e) => e.id).join(' + ')).join(', ')})`);

  // ---- 2. the default drawing is the one without stepping; every step marks its arrows, dims what is later, moves nothing
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    const before = await snapshot(p);
    const L0 = await look(p);
    t.eq(L0.step, '0', 'opens at step 0');
    t.eq(L0.count, `${n} steps`, 'step 0: the bar says how many steps there are');
    t.eq(L0.text, null, 'step 0: no step text');
    t.ok(Object.values(L0.edges).every(([s, o]) => s === null && o === 1), 'step 0: no arrow is marked or dimmed');
    t.ok(Object.values(L0.nodes).every((o) => o === 1), 'step 0: no box is dimmed');
    t.eq(L0.currentLabels, [], 'step 0: no label is marked');
    t.eq(await p.locator(`${btn('close')}`).count(), 0, 'step 0: no "show the whole diagram" button');
    const hash = await hashOf(p);
    for (let k = 1; k <= n; k++) {
      await p.locator(btn('next')).click();
      const L = await look(p);
      const want = expected(steps, k);
      t.eq(L.step, String(k), `next -> step ${k}`);
      t.eq(L.count, `Step ${k} of ${n}`, `step ${k}: counter`);
      t.eq(Object.entries(L.edges).map(([id, [s]]) => [id, s]).sort(), Object.entries(want.edges).sort(), `step ${k}: earlier, current and later arrows`);
      t.ok(Object.entries(L.edges).every(([id, [, o]]) => (want.edges[id] === 'later' ? o === 0.25 : o === 1)), `step ${k}: later arrows dimmed (0.25), the others not: ${JSON.stringify(L.edges)}`);
      t.eq(Object.entries(L.nodes).filter(([, o]) => o < 1).map(([id]) => id).sort(), want.later, `step ${k}: the boxes no step has reached yet are dimmed`);
      t.eq(L.currentLabels, steps[k - 1].map((e) => e.id).sort(), `step ${k}: the current arrow's label is marked`);
      const e = steps[k - 1][0];
      const text = e.label.lines[0].text.replace(`${e.order}: `, '');
      t.ok(L.text?.startsWith(`${nameOf(e.source)} → ${nameOf(e.target)}: ${text}`), `step ${k}: text "${L.text}"`);
      t.ok(L.live.startsWith(`Step ${k} of ${n}: ${nameOf(e.source)} to ${nameOf(e.target)}: ${text}`), `step ${k}: announced "${L.live}"`);
      const widths = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll('g.rolled-edge')].map((g) => [g.dataset.edge, parseFloat(g.querySelector('.react-flow__edge-path').style.strokeWidth)])));
      t.ok(steps[k - 1].every((c) => Object.entries(widths).every(([id, w]) => id === c.id || w < widths[c.id])), `step ${k}: the current arrow is the thickest`);
    }
    const after = await snapshot(p);
    t.eq(after.dom, before.dom, 'stepping moved no box');
    t.eq(after.vp, before.vp, 'at the default fit every step is already in view: the camera stays (section 11 zooms in)');
    t.eq(await hashOf(p), hash, 'stepping does not change the hash');
    // ---- 3. bounds: the last step, then back to the first
    t.eq(await p.locator(btn('next')).getAttribute('aria-disabled'), 'true', 'last step: Next is disabled');
    t.eq(await p.evaluate(() => document.activeElement?.dataset.testid), 'steps-next', 'last step: Next keeps the focus');
    await p.locator(btn('next')).click({ force: true }); // aria-disabled: Playwright would wait for it to be enabled
    t.eq(await stepOf(p), n, 'Next at the last step stays there');
    for (let k = n - 1; k >= 1; k--) {
      await p.locator(btn('prev')).click();
      t.eq(await stepOf(p), k, `previous -> step ${k}`);
    }
    t.eq(await p.locator(btn('prev')).getAttribute('aria-disabled'), 'true', 'first step: Previous is disabled');
    t.eq(await p.locator(btn('first')).getAttribute('aria-disabled'), 'true', 'first step: First is disabled');
    await p.locator(btn('prev')).click({ force: true });
    t.eq(await stepOf(p), 1, 'Previous at the first step stays there');
    await p.locator(btn('close')).click();
    const Lz = await look(p);
    t.eq(Lz.step, '0', 'Show the whole diagram -> step 0');
    t.eq(JSON.stringify([Lz.edges, Lz.nodes]), JSON.stringify([L0.edges, L0.nodes]), 'step 0 again: the drawing is the default one');
    t.eq(await p.evaluate(() => document.activeElement?.dataset.testid), 'steps-play', 'the focus moves to Play when the close button goes');

    // ---- 4. Play advances to the last step and stops; Pause stops it where it is
    await p.evaluate(() => { window.__viewer.stepMs = 40; });
    await p.locator(btn('play')).click();
    t.ok((await stepOf(p)) >= 1, 'Play from step 0 shows step 1 at once');
    await p.waitForFunction((n) => document.querySelector('[data-testid=steps]').dataset.step === String(n) && !document.querySelector('[data-testid=steps]').dataset.playing, n, { timeout: 5000 });
    t.eq(await stepOf(p), n, 'Play ends at the last step');
    t.eq(await p.locator(btn('play')).getAttribute('aria-label'), 'Play again from the first step', 'at the end Play starts again');
    if (n >= 3) {
      await p.evaluate(() => { window.__viewer.stepMs = 150; });
      await p.locator(btn('play')).click();
      t.eq(await stepOf(p), 1, 'Play at the last step starts from step 1');
      await p.waitForFunction(() => document.querySelector('[data-testid=steps]').dataset.step === '2', null, { timeout: 5000 });
      await p.locator(btn('play')).click(); // Pause
      const s = await stepOf(p);
      t.eq(await p.locator(bar).getAttribute('data-playing'), null, 'Pause: not playing');
      await p.waitForTimeout(600); // four step intervals: nothing may move
      t.eq(await stepOf(p), s, 'Pause: the step stays');
      t.ok((await look(p)).live.startsWith(`Paused at step ${s}`), 'Pause is announced');
      await p.evaluate(() => { window.__viewer.stepMs = 1e6; });
      await p.locator(btn('play')).click();
      t.eq(await stepOf(p), s, 'Play after Pause goes on from the same step');
      await p.locator(btn('next')).click();
      t.eq(await p.locator(bar).getAttribute('data-playing'), null, 'Next pauses');
    }
    await p.context().close();
  }

  // ---- 5. the keyboard: Tab reaches the bar, Enter/Space press its buttons, arrows/Home/End/Escape step inside it only
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    await p.evaluate(() => { window.__viewer.stepMs = 1e6; });
    let reached = false;
    for (let i = 0; i < 80 && !reached; i++) {
      await p.keyboard.press('Tab');
      reached = await p.evaluate(() => !!document.activeElement?.closest('[data-testid=steps]'));
    }
    t.ok(reached, 'Tab reaches the step bar');
    const labels = await p.locator(`${bar} button`).evaluateAll((bs) => bs.map((b) => b.getAttribute('aria-label')));
    t.eq(labels, ['First step', 'Previous step', 'Play the steps', 'Next step'], 'every button has a label');
    t.eq(await p.locator(bar).getAttribute('role'), 'group', 'the bar is a labelled group');
    await p.locator(btn('play')).focus();
    await p.keyboard.press('Enter');
    t.eq(await stepOf(p), 1, 'Enter on Play: step 1');
    t.eq(await p.locator(bar).getAttribute('data-playing'), 'true', 'Enter on Play: playing');
    await p.keyboard.press('Space');
    t.eq(await p.locator(bar).getAttribute('data-playing'), null, 'Space on Pause: paused');
    await p.keyboard.press('ArrowRight');
    t.eq(await stepOf(p), 2, 'Right arrow: next step');
    await p.keyboard.press('ArrowLeft');
    t.eq(await stepOf(p), 1, 'Left arrow: previous step');
    await p.keyboard.press('ArrowLeft');
    t.eq(await stepOf(p), 1, 'Left arrow at the first step: stays');
    await p.keyboard.press('End');
    t.eq(await stepOf(p), n, 'End: last step');
    await p.keyboard.press('ArrowRight');
    t.eq(await stepOf(p), n, 'Right arrow at the last step: stays');
    await p.keyboard.press('Home');
    t.eq(await stepOf(p), 1, 'Home: first step');
    const hash = await hashOf(p);
    await p.keyboard.press('Escape');
    t.eq(await stepOf(p), 0, 'Escape: the whole diagram');
    t.eq(await p.evaluate(() => document.activeElement?.dataset.testid), 'steps-play', 'Escape: the focus is on Play');
    t.eq(await hashOf(p), hash, 'Escape: the hash is unchanged');
    // outside the bar the keys keep their meaning: nothing steps
    await p.locator(btn('next')).click();
    await p.locator('[data-testid=canvas]').click({ position: { x: 5, y: 300 } });
    await p.keyboard.press('ArrowRight');
    await p.keyboard.press('Space');
    t.eq(await stepOf(p), 1, 'keys pressed on the canvas do not step');
    await p.context().close();
  }

  // ---- 6. a selection, another view or the model show the whole diagram again
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    await p.locator(btn('next')).click();
    await p.locator(btn('next')).click();
    const box = sc.nodes.find((x) => x.role === 'element');
    await mouseClick(p, box.id);
    t.eq(await stepOf(p), 0, 'selecting a box ends the stepping');
    await raf(p, 3);
    t.eq(await p.locator('g.rolled-edge').count(), sc.edges.length, 'after a selection every arrow is drawn');
    t.eq(await p.locator('g.rolled-edge[data-step]').count(), 0, 'after a selection no arrow is marked');
    await p.locator(btn('next')).click();
    t.eq(await stepOf(p), 1, 'stepping again with a selection');
    if (other) {
      await act(p, () => p.locator(`.views button[data-view="${other.key}"]`).click());
      t.eq(await stepOf(p), 0, `another dynamic view (${other.key}) opens at step 0`);
      t.eq(await p.locator(btn('count')).textContent(), `${stepsOf(scene(other)).length} steps`, `${other.key}: its own steps`);
    }
    await p.locator(btn('next')).click();
    await act(p, () => p.locator('.crumbs button').first().click());
    t.eq(await p.locator(bar).count(), 0, 'the model canvas has no step bar');
    await act(p, () => p.goBack());
    t.eq(await stepOf(p), 0, 'back to the dynamic view: step 0');
    await p.context().close();
  }

  // ---- 7. reduced motion: no fade between steps, Play still steps; without it, a short fade (the camera: section 12)
  for (const motion of ['reduce', 'no-preference']) {
    const p = await newPage(browser, errors, { reducedMotion: motion });
    await open(p, srv.url, `#/v/${v.key}`);
    const dur = await p.evaluate(() => getComputedStyle(document.querySelector('g.rolled-edge')).transitionDuration);
    t.eq(dur, motion === 'reduce' ? '0s' : '0.2s', `${motion}: arrow fade ${dur}`);
    await p.evaluate(() => { window.__viewer.stepMs = 40; });
    await p.locator(btn('play')).click();
    await p.waitForFunction((n) => document.querySelector('[data-testid=steps]').dataset.step === String(n), n, { timeout: 5000 });
    t.ok(true, `${motion}: Play reaches the last step`);
    await p.context().close();
  }

  // ---- 8. both themes: the bar's text and buttons read on it, the current label's mark reads on the canvas, axe
  for (const scheme of ['light', 'dark']) {
    const p = await newPage(browser, errors, { colorScheme: scheme });
    await open(p, srv.url, `#/v/${v.key}`);
    await p.locator(btn('next')).click();
    await raf(p, 3);
    t.eq(await p.evaluate(() => document.documentElement.dataset.theme), scheme, `${scheme}: theme`);
    const c = await p.evaluate(() => {
      const cs = (sel) => getComputedStyle(document.querySelector(sel));
      return { bg: cs('[data-testid=steps]').backgroundColor, text: cs('[data-testid=steps-count]').color, step: cs('[data-testid=steps-text]').color,
        icon: cs('[data-testid=steps-next]').color, edge: cs('[data-testid=steps-next]').borderTopColor,
        mark: cs('.edge-label[data-step=current]').outlineColor, canvas: cs('.react-flow').backgroundColor };
    });
    t.ok(contrast(c.text, c.bg) >= 4.5 && contrast(c.step, c.bg) >= 4.5, `${scheme}: text ${contrast(c.text, c.bg).toFixed(2)}:1 on the bar`);
    t.ok(contrast(c.icon, c.bg) >= 3 && contrast(c.edge, c.bg) >= 3, `${scheme}: button icon ${contrast(c.icon, c.bg).toFixed(2)}:1 and border ${contrast(c.edge, c.bg).toFixed(2)}:1`);
    t.ok(contrast(c.mark, c.canvas) >= 3, `${scheme}: current label mark ${contrast(c.mark, c.canvas).toFixed(2)}:1 on the canvas`);
    await p.addScriptTag({ path: AXE });
    const res = await p.evaluate(async () => (await window.axe.run({ include: [['[data-testid=steps]']] }, { resultTypes: ['violations'] })).violations.map((x) => `${x.id}[${x.impact}]`));
    t.eq(res, [], `${scheme}: axe on the step bar`);
    await p.context().close();
  }

  // ---- 9. embedded (?embed=1&data=server): the bar is there and steps; a frame too low for it draws the diagram alone
  {
    const e = await newPage(browser, errors, { viewport: { width: 800, height: 500 } });
    await e.goto(srv.url + `?embed=1&data=server#/v/${v.key}`);
    await e.waitForFunction(() => window.__viewer?.ready === true && Object.keys(window.__viewer.positions()).length > 0);
    t.ok(await e.locator(bar).isVisible(), 'embed: the step bar is shown');
    const len = await e.evaluate(() => history.length);
    await e.locator(btn('next')).click();
    await e.locator(btn('next')).click();
    t.eq(await stepOf(e), 2, 'embed: Next steps');
    t.eq(await e.evaluate(() => history.length), len, 'embed: no history entry');
    await e.setViewportSize({ width: 800, height: 200 });
    t.ok(!(await e.locator(bar).isVisible()), 'embed 200 px high: no room, no bar');
    await e.context().close();
  }

  // ---- 10. phone (390 px) and desktop: the bar fits, its buttons are big enough to tap, it is not under the header
  for (const [label, opts] of [['phone', { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true }], ['desktop', {}]]) {
    const p = await newPage(browser, errors, opts);
    await open(p, srv.url, `#/v/${v.key}`);
    if (label === 'phone') await p.locator(btn('next')).tap(); else await p.locator(btn('next')).click();
    t.eq(await stepOf(p), 1, `${label}: Next steps`);
    const r = await p.evaluate(() => {
      const b = document.querySelector('[data-testid=steps]').getBoundingClientRect();
      const c = document.querySelector('[data-testid=canvas]').getBoundingClientRect();
      const sizes = [...document.querySelectorAll('[data-testid=steps] button')].map((x) => { const q = x.getBoundingClientRect(); return [q.width, q.height]; });
      return { b: [b.left, b.top, b.right, b.bottom], c: [c.left, c.top, c.right, c.bottom], sizes, sw: document.documentElement.scrollWidth, w: innerWidth };
    });
    t.ok(r.b[0] >= r.c[0] && r.b[2] <= r.c[2] && r.b[1] >= r.c[1], `${label}: the bar is inside the canvas ${JSON.stringify(r.b)} in ${JSON.stringify(r.c)}`);
    t.ok(r.sw <= r.w, `${label}: no horizontal scroll`);
    const min = label === 'phone' ? 44 : 32;
    t.ok(r.sizes.every(([w, h]) => w >= min && h >= min), `${label}: buttons at least ${min} px: ${JSON.stringify(r.sizes)}`);
    await p.context().close();
  }

  // ---- 11. the camera follows the current step: it brings the step's arrows, labels and end boxes into the free part of the
  // canvas (not under the bar or the phone's sheet), keeps the zoom when the step fits, zooms out only as far as it must, never in
  const follows = async (p, label, { phone = false } = {}) => {
    let moved = 0, zoomedOut = 0;
    for (let k = 1; k <= n; k++) {
      const before = (await framing(p)).vp;
      if (phone) await p.locator(btn('next')).tap(); else await p.locator(btn('next')).click();
      await camDone(p);
      const f = await framing(p);
      t.ok(inside(f), `${label} step ${k}: the step is in the free part of the canvas ${r1(f)}`);
      t.ok(f.vp.zoom <= before.zoom + 1e-6, `${label} step ${k}: never zoomed in (${before.zoom.toFixed(3)} -> ${f.vp.zoom.toFixed(3)})`);
      if (f.cam.moved) moved++;
      if (f.vp.zoom < before.zoom - 1e-6) {
        zoomedOut++;
        const [w, h] = [f.box[2] - f.box[0], f.box[3] - f.box[1]];
        const [fw, fh] = [f.free[2] - f.free[0], f.free[3] - f.free[1]];
        t.ok(Math.max(w / (fw - 64), h / (fh - 64)) > 0.97, `${label} step ${k}: zoomed out only as far as the step needs (${Math.round(w)}x${Math.round(h)} in ${Math.round(fw)}x${Math.round(fh)} less the padding)`);
      }
    }
    return { moved, zoomedOut };
  };
  {
    // desktop: at the default fit every step is in view, nothing moves (section 2); zoomed in, the camera follows
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    const fit = (await snapshot(p)).vp;
    await p.locator(btn('next')).click();
    await camDone(p);
    t.ok(!(await framing(p)).cam.moved && sameVp((await framing(p)).vp, fit), 'desktop default fit: step 1 is in view, the camera stays');
    await p.locator(btn('close')).click();
    await settle(p);
    await zoomTo(p, Math.min(2, fit.zoom * 3));
    const hash = await hashOf(p);
    const r = await follows(p, 'desktop zoomed in');
    t.ok(r.moved > 0, `desktop zoomed in: the camera followed (${r.moved} of ${n} steps moved it)`);
    t.eq(await hashOf(p), hash, 'following the steps does not change the hash');
    // a step already in view does not move the camera
    const k = n;
    const shown = await framing(p);
    await p.locator(btn('prev')).click();
    await camDone(p);
    const back = await framing(p);
    if (!back.cam.moved) t.ok(sameVp(back.vp, shown.vp), `previous step ${k - 1} was already in view: the camera stayed`);
    else t.ok(inside(back), `previous step ${k - 1}: brought into view`);
    // manual pan between steps is left alone, the next step refocuses
    await p.evaluate(() => { const v = window.__viewer.viewport(); window.__viewer.setViewport({ ...v, x: v.x + 4000, y: v.y + 3000 }); });
    await raf(p, 3);
    const panned = (await framing(p)).vp;
    await p.waitForTimeout(400);
    t.ok(sameVp((await framing(p)).vp, panned), 'a manual pan while paused is left alone');
    await p.locator(btn('next')).click();
    await camDone(p);
    const ref = await framing(p);
    t.ok(ref.cam.moved && inside(ref), `the next step brings the step back into view ${r1(ref)}`);
    // back to step 0: the default whole-diagram fit, by the close button, Escape and a selection
    await act(p, () => p.locator(btn('close')).click());
    t.ok(sameVp((await snapshot(p)).vp, fit), 'Show the whole diagram: the default fit again');
    await p.locator(btn('next')).click();
    await camDone(p);
    await act(p, () => p.keyboard.press('Escape'));
    t.ok(sameVp((await snapshot(p)).vp, fit), 'Escape: the default fit again');
    await zoomTo(p, Math.min(2, fit.zoom * 3));
    await p.locator(btn('next')).click();
    await camDone(p);
    await act(p, () => mouseClick(p, steps[0][0].source)); // a box of the step: it is on screen
    t.eq(await stepOf(p), 0, 'selecting a box ends the stepping');
    t.ok(sameVp((await snapshot(p)).vp, fit), 'ending the stepping by a selection: the default fit again');
    await p.context().close();
  }
  {
    // a small desktop window zoomed in: a step too big for it is zoomed out to fit
    const p = await newPage(browser, errors, { viewport: { width: 800, height: 520 } });
    await open(p, srv.url, `#/v/${v.key}`);
    await zoomTo(p, 2);
    const r = await follows(p, 'small window at zoom 2');
    t.ok(r.zoomedOut > 0, `small window at zoom 2: a step too big was zoomed out to fit (${r.zoomedOut} of ${n})`);
    await p.context().close();
  }
  {
    // phone: the default fit runs under the bar, so the camera moves the step out from under it; with the sheet open, above it
    const opts = { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true };
    const p = await newPage(browser, errors, opts);
    await open(p, srv.url, `#/v/${v.key}`);
    const fit = (await snapshot(p)).vp;
    await follows(p, 'phone', { phone: true });
    await act(p, () => p.locator(btn('close')).tap());
    t.ok(sameVp((await snapshot(p)).vp, fit), 'phone: back to step 0, the default fit again');
    const box = sc.nodes.find((x) => x.role === 'element');
    const [x, y] = await hitPoint(p, box.id);
    await p.touchscreen.tap(x, y); // at step 0: a selection, the camera stays
    await p.waitForFunction(() => document.querySelector('.sheet-wrap')?.dataset.sheet === 'peek');
    await p.waitForTimeout(400); // the sheet slides up
    await follows(p, 'phone, sheet open', { phone: true });
    await p.context().close();
  }
  {
    // embedded, a frame too low for the bar: the whole canvas is free; no hash change, no history entry
    const e = await newPage(browser, errors, { viewport: { width: 800, height: 230 } });
    await e.goto(srv.url + `?embed=1&data=server#/v/${v.key}`);
    await settle(e);
    t.ok(!(await e.locator(bar).isVisible()), 'embed 230 px high: no bar');
    await zoomTo(e, 2);
    const len = await e.evaluate(() => history.length);
    const hash = await hashOf(e);
    for (let k = 1; k <= n; k++) {
      await e.locator(btn('next')).evaluate((b) => b.click()); // the bar is hidden: press it from the page, as a test would
      await camDone(e);
      const f = await framing(e);
      t.ok(inside(f), `embed, no bar, step ${k}: in view ${r1(f)}`);
    }
    t.eq(await e.evaluate(() => history.length), len, 'embed: the camera moves add no history entry');
    t.eq(await hashOf(e), hash, 'embed: the hash is unchanged');
    await e.context().close();
  }
  // ---- 12. motion: reduced motion jumps to the step at once, otherwise a short animated pan, well inside one Play interval
  for (const motion of ['reduce', 'no-preference']) {
    const p = await newPage(browser, errors, { reducedMotion: motion });
    await open(p, srv.url, `#/v/${v.key}`);
    if (motion === 'no-preference') await p.waitForFunction(() => window.__viewer.ready === true);
    await zoomTo(p, 2);
    const samples = await p.evaluate(() => new Promise((res) => {
      const out = [window.__viewer.viewport()];
      document.querySelector('[data-testid=steps-next]').click();
      const f = () => { out.push(window.__viewer.viewport()); if ((window.__viewer.stepCamera?.done ?? out.length > 30) && out.length > 3) res({ out, cam: window.__viewer.stepCamera ?? {} }); else requestAnimationFrame(f); };
      requestAnimationFrame(f);
    }));
    const { out, cam } = samples;
    t.ok(cam.moved, `${motion}: zoomed in, step 1 moves the camera`);
    if (motion === 'reduce') {
      t.eq(cam.duration, 0, 'reduce: no animation');
      t.ok(!!cam.to && sameVp(out[1], cam.to), `reduce: the next frame is already the final camera ${JSON.stringify(out[1])}`);
    } else {
      t.eq(cam.duration, 300, 'no-preference: a 300 ms pan');
      t.ok(cam.duration < 2000 / 2, 'the pan ends well inside one Play interval (2 s)');
      const between = !!cam.to && out.slice(1).some((s) => !sameVp(s, out[0]) && !sameVp(s, cam.to));
      t.ok(between, `no-preference: the camera passes through in-between positions (${out.length} frames sampled)`);
      t.ok(!!cam.to && sameVp(out.at(-1), cam.to), 'no-preference: it ends at the final camera');
    }
    await p.context().close();
  }

  t.eq(errors, [], 'no console errors');
  return t;
}
