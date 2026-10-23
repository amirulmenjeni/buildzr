// Zoom-in expand (setting `zoomExpand`): off = never expands; on = a collapsed frame expands at 0.9 x its fit zoom when the
// viewport centre is inside it, like a click, with its scene prefetched before. Run: node tests/run.mjs --only expand --data <dir>
import { newPage, open, snapshot, hashOf, raf, fitOf, T } from './lib.mjs';

const KEY = 'buildzr-ui:settings';
const EXPAND_AT = 0.9, PREFETCH_AT = 0.6, COLLAPSE_AT = 0.5; // zoomfx.ts EXPAND / CHILD_FADE.gone
const pathOf = (h) => decodeURIComponent(h.replace(/^#\/m\/?/, '').split('?')[0]);

/** Zoom to `z` with the flow point (fx, fy) at the centre of the canvas, instantly. */
async function zoomAt(p, z, [fx, fy]) {
  await p.evaluate(([z, fx, fy]) => {
    const el = document.querySelector('.react-flow');
    window.__viewer.setViewport({ zoom: z, x: el.clientWidth / 2 - fx * z, y: el.clientHeight / 2 - fy * z });
  }, [z, fx, fy]);
  await raf(p, 3);
  await p.waitForTimeout(30);
}
const setVp = async (p, vp) => { await p.evaluate((v) => window.__viewer.setViewport(v), vp); await raf(p, 3); await p.waitForTimeout(30); };
const state = (p) => p.evaluate(() => ({ hash: location.hash, hist: history.length }));
const rectOf = async (p, id) => { const r = (await p.evaluate(() => window.__viewer.positions()))[id]; return r; };
const centreOf = (r) => [r.x + r.w / 2, r.y + r.h / 2];

function compare(a, b) {
  let compared = 0, storeDiff = 0, domDiff = 0, maxDom = 0;
  for (const id of Object.keys(a.store)) {
    if (!(id in b.store)) continue;
    compared++;
    const x = a.store[id], y = b.store[id];
    if (x.x !== y.x || x.y !== y.y || x.w !== y.w || x.h !== y.h) storeDiff++;
    const m = Math.max(...a.dom[id].map((v, i) => Math.abs(v - b.dom[id][i])));
    maxDom = Math.max(maxDom, m);
    if (m > 0.01) domDiff++;
  }
  return { compared, storeDiff, domDiff, maxDom };
}

/**
 * Zoom in on `centre` in `n` geometric steps from `from` to `to`. One row per step: the ratio to `fit` (the camera's fit zoom of
 * the frame at stake), the path and the history entries the step added. The step on which `target` becomes the path is checked
 * for "nothing outside the subtree moves": restore the previous viewport, compare with the snapshot taken before the step.
 * `onStep(i)` runs before each step (the callers log scene requests against it).
 */
async function sweepIn(p, t, { target, centre, from, to, n, fit, label, stepBase = 0, onStep = () => {} }) {
  await zoomAt(p, from, centre);
  const rows = [];
  let prevSnap = await snapshot(p);
  for (let i = 1; i <= n; i++) {
    onStep(stepBase + i);
    const z = from * (to / from) ** (i / n);
    const before = await state(p);
    await zoomAt(p, z, centre);
    const after = await state(p);
    rows.push({ i, z, ratio: z / fit, path: pathOf(after.hash), dHist: after.hist - before.hist, hash: after.hash });
    if (pathOf(before.hash) !== target && pathOf(after.hash) === target) {
      await p.waitForFunction((id) => !!document.querySelector(`.react-flow__node[data-id="${id}"] [data-expanded=true]`), target);
      await raf(p, 3);
      const here = (await snapshot(p)).vp;
      await p.evaluate(() => { window.__viewer.autoCollapse = false; }); // restoring the old viewport is a zoom-out
      await setVp(p, prevSnap.vp);
      const B = await snapshot(p);
      const cmp = compare(prevSnap, B);
      t.eq(cmp.storeDiff, 0, `${label}: store positions changed by the expansion of ${target}`);
      t.eq(cmp.domDiff, 0, `${label}: DOM rects changed by the expansion of ${target} (max ${cmp.maxDom.toFixed(4)} px)`);
      t.ok(cmp.compared >= 2, `${label}: compared ${cmp.compared} nodes`);
      t.note(`${label}: expanded ${target} at ratio ${(z / fit).toFixed(3)} (step ${i}); ${cmp.compared} nodes compared, max DOM delta ${cmp.maxDom.toFixed(4)} px`);
      await setVp(p, here);
      await p.evaluate(() => { window.__viewer.autoCollapse = true; });
    }
    prevSnap = await snapshot(p);
  }
  return rows;
}

export default async function expand(browser, srv, F, name) {
  const t = new T(`expand:${name}`);
  const errors = [];
  const E1 = F.expandable.find((id) => !F.parentOf(id));
  const E2 = F.expandable.find((id) => F.parentOf(id) === E1);
  if (!E1) { t.note('nothing expandable: skipped'); return t; }
  const sceneFile = (id) => F.index.scenes['e/' + id].file;
  const on = (p) => p.addInitScript(([k]) => localStorage.setItem(k, JSON.stringify({ zoomExpand: true })), [KEY]);

  // the camera's fit zoom of a frame, read on a fresh page each time (a hash-only navigation can be read before its camera move ends)
  const fitFresh = async (id) => { const q = await newPage(browser, errors, { reducedMotion: 'no-preference' }); const z = await fitOf(q, srv, '#/m/' + id); await q.context().close(); return z; };
  const z1 = await fitFresh(E1);
  const z2 = E2 ? await fitFresh(E2) : null;

  // ------------------------------------------------------------ 1. flag OFF: zooming in never expands anything
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    t.eq(await p.evaluate(() => window.__viewer.settings.zoomExpand), false, 'flag is off by default');
    const reqs = []; p.on('request', (r) => reqs.push(r.url()));
    const h0 = await state(p);
    const rows = await sweepIn(p, t, { target: E1, centre: centreOf(await rectOf(p, E1)), from: 0.35 * z1, to: 3 * z1, n: 28, fit: z1, label: 'off' });
    for (const r of rows) t.eq(r.path, '', `off: step ${r.i} (ratio ${r.ratio.toFixed(2)}) must not expand`);
    const h1 = await state(p);
    t.eq(h1, h0, 'off: hash and history unchanged by 28 zoom-in steps');
    t.eq(await p.locator('[data-expanded=true]').count(), 0, 'off: no expanded frame');
    t.eq(reqs.filter((u) => u.endsWith(sceneFile(E1))).length, 0, 'off: no prefetch of the scene');
    await p.context().close();
  }

  // ------------------------------------------------------------ 2. flag ON through the gear: expand, expand again, Back x2
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    await p.locator('button.gear').click();
    await p.locator('[role=dialog] input[data-setting=zoomExpand]').click();
    await p.keyboard.press('Escape');
    t.eq(await p.evaluate(() => window.__viewer.settings.zoomExpand), true, 'on: switched on through the gear');
    const h0 = await state(p);
    const seen = []; // scene requests with the step they were seen at
    let step = 0;
    p.on('request', (r) => { for (const id of [E1, E2]) if (id && r.url().endsWith(sceneFile(id))) seen.push({ id, step }); });
    // -- landscape -> E1
    const N = 30;
    const rows = await sweepIn(p, t, { target: E1, centre: centreOf(await rectOf(p, E1)), from: 0.35 * z1, to: 1.4 * z1, n: N, fit: z1, label: 'on', onStep: (i) => { step = i; } });
    const first = rows.find((r) => r.path === E1);
    t.ok(!!first, `on: ${E1} expanded during the sweep`);
    if (first) {
      t.ok(first.ratio >= EXPAND_AT - 1e-9, `on: expanded only at ratio >= ${EXPAND_AT} (was ${first.ratio.toFixed(3)})`);
      const prevRow = rows[first.i - 2];
      t.ok(!prevRow || prevRow.ratio < EXPAND_AT, 'on: expanded at the first step at or above the threshold');
      t.eq(first.dHist, 1, 'on: the expansion added exactly one history entry');
      t.eq(decodeURIComponent(first.hash), `#/m/${E1}?sel=${E1}`, 'on: hash like a click on the frame');
      t.eq(rows.filter((r) => r.dHist !== 0).length, 1, 'on: exactly one history entry over the whole sweep');
      const pf = seen.filter((s) => s.id === E1);
      t.ok(pf.length >= 1, `on: the scene of ${E1} was requested`);
      if (pf.length) {
        const at = rows[Math.max(0, pf[0].step - 1)];
        t.ok(at.ratio < EXPAND_AT && at.ratio >= PREFETCH_AT * 0.9, `on: scene requested at step ${pf[0].step}, ratio ${at.ratio.toFixed(3)}: before the expand threshold, from the prefetch ratio (${PREFETCH_AT})`);
        t.ok(pf[0].step < first.i, 'on: the request came before the expansion step');
      }
      t.eq(await p.locator(`[role=treeitem][data-id="${E1}"]`).getAttribute('aria-selected'), 'true', 'on: tree row selected');
      t.eq(await p.locator(`[role=treeitem][data-id="${E1}"]`).getAttribute('aria-expanded'), 'true', 'on: tree row expanded');
      t.ok(((await p.locator('.crumbs [aria-current=page]').textContent()) ?? '').includes(F.byId.get(E1).name), 'on: breadcrumb shows the expanded element');
      t.ok(((await p.locator('[data-testid=live]').textContent()) ?? '').startsWith('Expanded ' + F.byId.get(E1).name), 'on: announced like a click');
    }
    // -- E1 -> E2
    if (E2) {
      const histBefore = (await state(p)).hist;
      const c2 = centreOf(await rectOf(p, E2));
      const from = (await snapshot(p)).vp.zoom;
      const n2 = 30;
      // pan to E2 at the same zoom first (not a zoom-in: nothing happens), then zoom in on it
      step = 100;
      await zoomAt(p, from, c2);
      t.eq(pathOf(await hashOf(p)), E1, 'on: panning alone does not expand E2');
      const out = await sweepIn(p, t, { target: E2, centre: c2, from, to: 1.4 * z2, n: n2, fit: z2, label: 'on', stepBase: 100, onStep: (i) => { step = i; } });
      const e2 = out.find((r) => r.path === E2);
      t.ok(!!e2, `on: ${E2} expanded while zooming toward it`);
      if (e2) {
        t.ok(e2.ratio >= EXPAND_AT - 1e-9 && (out[e2.i - 2]?.ratio ?? 0) < EXPAND_AT, `on: ${E2} expanded at the threshold (ratio ${e2.ratio.toFixed(3)})`);
        t.eq(e2.dHist, 1, `on: expanding ${E2} added one history entry`);
        const pf = seen.filter((s) => s.id === E2);
        // the centre of the first sweep ends inside E2 at ratio ~0.7, so its scene may be requested already then (>= 0.6): that is the prefetch
        const rAt = !pf.length ? NaN : pf[0].step >= 101 ? out[pf[0].step - 101].ratio : pf[0].step === 100 ? from / z2 : null;
        t.ok(pf.length > 0 && pf[0].step < 100 + e2.i && (rAt === null || (rAt < EXPAND_AT && rAt >= PREFETCH_AT * 0.9)), `on: the scene of ${E2} was requested (step ${pf[0]?.step}, ratio ${rAt === null ? 'during the first sweep' : rAt.toFixed(3)}) before the threshold`);
      }
      t.eq((await state(p)).hist - histBefore, 1, 'on: one history entry for the second expansion');
      // Back x2
      await p.goBack(); await p.waitForFunction((e) => location.hash.startsWith('#/m/' + e + '?') || location.hash === '#/m/' + e, E1);
      t.eq(pathOf(await hashOf(p)), E1, 'on: Back returns to the first level');
      await p.waitForFunction(() => window.__viewer.ready === true);
      await p.goBack();
      await p.waitForFunction(() => location.hash === '#/m' || location.hash === '');
      await p.waitForFunction(() => window.__viewer.ready === true);
      await p.waitForTimeout(400);
      t.eq(await hashOf(p), h0.hash, 'on: Back x2 returns to the landscape');
      t.eq(await p.locator('[data-expanded=true]').count(), 0, 'on: nothing re-expands after Back');
    } else {
      await p.goBack();
      await p.waitForFunction(() => location.hash === '#/m' || location.hash === '');
      await p.waitForFunction(() => window.__viewer.ready === true);
      await p.waitForTimeout(400);
      t.eq(await hashOf(p), h0.hash, 'on: Back returns to the landscape');
    }
    await p.context().close();
  }

  // ------------------------------------------------------------ 3. hysteresis: 20 wiggles of +-3% around each threshold
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await on(p);
    await open(p, srv.url, '#/m');
    const c = centreOf(await rectOf(p, E1));
    await zoomAt(p, 0.5 * z1, c);
    await zoomAt(p, 0.8 * z1, c);
    const s0 = await state(p);
    let n = 0, last = pathOf(s0.hash);
    for (let i = 0; i < 20; i++) {
      await zoomAt(p, z1 * EXPAND_AT * (i % 2 ? 0.97 : 1.03), c);
      const h = pathOf(await hashOf(p));
      if (h !== last) { n++; last = h; }
    }
    const s1 = await state(p);
    t.ok(n <= 1, `hysteresis: 20 wiggles of +-3% around the expand threshold changed the path ${n} times (max 1)`);
    t.ok(s1.hist - s0.hist <= 1, `hysteresis: ${s1.hist - s0.hist} history entries (max 1)`);
    t.eq(last, E1, 'hysteresis: it ended expanded');
    // around the collapse threshold (E1 is expanded now)
    await zoomAt(p, z1 * COLLAPSE_AT * 1.03, c);
    const s2 = await state(p);
    let m = 0; last = pathOf(s2.hash);
    for (let i = 0; i < 20; i++) {
      await zoomAt(p, z1 * COLLAPSE_AT * (i % 2 ? 1.03 : 0.97), c);
      const h = pathOf(await hashOf(p));
      if (h !== last) { m++; last = h; }
    }
    const s3 = await state(p);
    t.ok(m <= 1, `hysteresis: 20 wiggles of +-3% around the collapse threshold changed the path ${m} times (max 1)`);
    t.ok(s3.hist - s2.hist <= 1, `hysteresis: ${s3.hist - s2.hist} history entries (max 1)`);
    t.eq(last, '', 'hysteresis: it ended collapsed (the up-wiggles did not expand it again)');
    t.note(`hysteresis: ${n} change(s) at the expand threshold, ${m} at the collapse threshold`);
    // zoom out afterwards: collapse as before, all the way
    await zoomAt(p, z1 * 0.9, c); // expands again (zooming in)
    t.eq(pathOf(await hashOf(p)), E1, 'zoom in again expands again');
    for (let i = 1; i <= 24; i++) await zoomAt(p, z1 * 0.9 * (0.1 / 0.9) ** (i / 24), c);
    t.eq(pathOf(await hashOf(p)), '', 'zooming out afterwards collapses as before');
    await p.context().close();
  }

  // ------------------------------------------------------------ 4. reduced motion: no intermediate opacity at the expand or the collapse
  {
    const p = await newPage(browser, errors, { reducedMotion: 'reduce' });
    await on(p);
    await open(p, srv.url, '#/m');
    const c = centreOf(await rectOf(p, E1));
    const grab = () => p.evaluate(() => {
      const o = {};
      for (const n of document.querySelectorAll('.react-flow__node')) {
        const fx = n.querySelector('.fx');
        const names = [...n.querySelectorAll('[data-tier="0"]')];
        o[n.dataset.id] = [parseFloat(getComputedStyle(n.firstElementChild).opacity), fx ? parseFloat(getComputedStyle(fx).opacity) : 1, ...names.map((x) => parseFloat(getComputedStyle(x).opacity) * parseFloat(getComputedStyle(x.parentElement).opacity))];
      }
      return o;
    });
    let samples = 0, moving = 0;
    const check = async (label) => {
      await raf(p, 1);
      const a = await grab();
      await p.waitForTimeout(450);
      const b = await grab();
      for (const id of Object.keys(a)) if (id in b) { samples += a[id].length; if (JSON.stringify(a[id]) !== JSON.stringify(b[id])) { moving++; console.log(`  FAIL [expand:${name}] ${label}: ${id} opacity ${JSON.stringify(a[id])} then ${JSON.stringify(b[id])}`); t.ok(false, `${label}: opacity of ${id} still changing`); } }
    };
    await zoomAt(p, 0.5 * z1, c);
    const z = [0.7, 0.85, 0.89];
    for (const r of z) await zoomAt(p, r * z1, c);
    await zoomAt(p, 0.95 * z1, c);
    t.eq(pathOf(await hashOf(p)), E1, 'reduced motion: expanded');
    await check('right after the expand');
    await zoomAt(p, 0.3 * z1, c);
    t.eq(pathOf(await hashOf(p)), '', 'reduced motion: collapsed');
    await check('right after the collapse');
    // every sampled value while stepping through the whole range is 0 or 1 or a node state constant: compare with the settled values at each step
    t.note(`reduced motion: ${samples} opacity samples right after the expand and the collapse, ${moving} still moving after 450 ms`);
    await p.context().close();
  }

  t.eq(errors, [], 'no console errors in expand tests');
  console.log(`  expand ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
