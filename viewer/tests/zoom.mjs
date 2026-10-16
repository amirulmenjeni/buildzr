// Zoom behaviour: zooming out collapses expanded frames (deepest first), labels shrink and fade, children fade before the collapse.
// Run: node tests/run.mjs --only zoom --data <dir>   (needs a data dir with an element that is expandable and whose parent is too, or at least one expandable)
import { newPage, open, settle, snapshot, hashOf, raf, zoomTo, fitOf, T } from './lib.mjs';

const pathOf = (h) => decodeURIComponent(h.replace(/^#\/m\/?/, '').split('?')[0]);
const selOf = (h) => { const m = /[?&]sel=([^&]*)/.exec(h); return m ? decodeURIComponent(m[1]) : null; };

/** Everything the tests look at, at this instant. */
const probe = (p, subtreeOf) => p.evaluate((sub) => {
  const labels = {};
  for (const el of document.querySelectorAll('[data-role=frame-label]')) {
    const id = el.closest('.react-flow__node').dataset.id;
    const name = el.querySelector('[data-tier="0"]');
    labels[id] = { px: name.getBoundingClientRect().height / 1.25, op: parseFloat(getComputedStyle(el).opacity) };
  }
  const kids = {};
  if (sub) for (const n of document.querySelectorAll('.react-flow__node')) {
    const id = n.dataset.id;
    if (id !== sub && (id.startsWith(sub + '/') || id.startsWith('e/' + sub + '|'))) kids[id] = parseFloat(getComputedStyle(n.querySelector('.fx')).opacity);
  }
  const rows = {};
  for (const r of document.querySelectorAll('[role=treeitem]')) rows[r.dataset.id] = [r.getAttribute('aria-expanded'), r.getAttribute('aria-selected')];
  return { hash: location.hash, labels, kids, rows, hist: history.length };
}, subtreeOf);

export default async function zoom(browser, srv, F, name) {
  const t = new T(`zoom:${name}`);
  const errors = [];
  // the deepest chain available: a container-level frame whose parent is a system-level frame, else one expandable
  const E2 = F.expandable.find((id) => F.expandable.includes(F.parentOf(id)) && F.parentOf(id));
  const E1 = E2 ? F.parentOf(E2) : F.expandable[0];
  const deep = E2 ?? E1;
  const chainIds = E2 ? [E2, E1] : [E1];
  if (!deep) { t.note('nothing expandable: skipped'); return t; }
  const rowsOf = (r) => JSON.stringify(Object.entries(r).sort());

  const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
  const fit = {};
  for (const id of chainIds) fit[id] = await fitOf(p, srv, '#/m/' + id);
  const zL = await fitOf(p, srv, '#/m');
  const zEnd = Math.min(zL, 0.45 * fit[E1]) * 0.98;
  t.note(`fit zoom: ${chainIds.map((id) => `${id} ${fit[id].toFixed(4)}`).join(', ')}, landscape ${zL.toFixed(4)}; stepping to ${zEnd.toFixed(4)}`);

  // ---------------------------------------------------------------- 1. step down from the deepest frame's fit zoom
  await open(p, srv.url, '#/m/' + deep);
  const N = 36;
  const zs = Array.from({ length: N + 1 }, (_, i) => fit[deep] * (zEnd / fit[deep]) ** (i / N));
  let prev = await probe(p, deep);
  let prevZoom = zs[0];
  const paths = [pathOf(prev.hash)];
  const changes = [];
  let sawMidChild = 0, sawMidLabel = 0, maxLabelsSeen = 0, collapseAt = {};
  let cur = deep;
  for (let i = 1; i <= N; i++) {
    const A = await snapshot(p); // expanded state, at the previous zoom
    await zoomTo(p, zs[i]);
    const now = await probe(p, cur);
    const path = pathOf(now.hash);
    // (b) no frame label ever gets bigger on screen while zooming out, the step where a frame collapses included
    // (a frame's name is capped at 2x its child frames' names, which does not depend on what is expanded or focused).
    for (const [id, l] of Object.entries(now.labels)) {
      if (id in prev.labels) t.ok(l.px <= prev.labels[id].px + 0.01, `label of ${id} grew: ${prev.labels[id].px.toFixed(3)} -> ${l.px.toFixed(3)} px at step ${i}`);
      // (c) < 6 px is invisible, >= 12 px is opaque
      if (l.px < 6) t.ok(l.op <= 0.05, `label of ${id} is ${l.px.toFixed(2)} px but opacity ${l.op}`);
      if (l.px >= 12) t.ok(l.op >= 0.95, `label of ${id} is ${l.px.toFixed(2)} px but opacity ${l.op}`);
      if (l.px >= 6 && l.px < 12) { sawMidLabel++; t.ok(l.op > 0 && l.op < 1 || Math.abs(l.op - (l.px - 6) / 6) < 0.02, `label ramp ${l.px.toFixed(2)} px -> ${l.op}`); }
    }
    maxLabelsSeen = Math.max(maxLabelsSeen, Object.keys(now.labels).length);
    // (d) children of the frame that is about to collapse fade along the ramp (zoom relative to that frame's fit zoom)
    if (path === cur) {
      const ratio = zs[i] / fit[cur];
      const want = Math.min(1, Math.max(0, (ratio - 0.5) / 0.3));
      for (const [id, o] of Object.entries(now.kids)) t.ok(Math.abs(o - want) <= 0.011, `child ${id} opacity ${o} at ratio ${ratio.toFixed(3)}, want ${want.toFixed(3)}`);
      if (ratio > 0.5 && ratio < 0.8 && Object.values(now.kids).some((o) => o > 0 && o < 1)) sawMidChild++;
    }
    if (path !== paths[paths.length - 1]) {
      // a collapse happened at this step
      const gone = cur;
      paths.push(path);
      changes.push({ step: i, ratio: zs[i] / fit[gone], from: gone, to: path, hash: now.hash, hist: now.hist - prev.hist });
      t.eq(path, F.parentOf(gone), `collapse of ${gone} lands on its parent`);
      t.eq(selOf(now.hash), gone, `selection after collapsing ${gone}`);
      t.eq(now.rows[gone]?.[1], 'true', `tree row ${gone} is selected`);
      t.eq(Object.entries(now.rows).filter(([, r]) => r[1] === 'true').length, 1, 'one selected tree row');
      t.ok(zs[i] / fit[gone] < 0.5 && zs[i - 1] / fit[gone] >= 0.5, `collapse of ${gone} only below 0.5 x its fit (step ${i}, ratio ${(zs[i] / fit[gone]).toFixed(3)})`);
      collapseAt[gone] = zs[i];
      // (e) nothing outside the collapsed subtree moved: same store positions, and the same DOM rects at the same viewport
      await zoomTo(p, zs[i - 1]);
      const B = await snapshot(p);
      await zoomTo(p, zs[i]);
      const inSub = (id) => id.startsWith(gone + '/') || id.startsWith('e/' + gone + '|');
      let cmp = 0, bad = 0, maxd = 0;
      for (const id of Object.keys(A.store)) {
        if (!(id in B.store)) { t.ok(inSub(id), `${id} vanished but is outside the collapsed ${gone}`); continue; }
        cmp++;
        const a = A.store[id], b = B.store[id];
        if (a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h) bad++;
        const d = Math.max(...A.dom[id].map((v, k) => Math.abs(v - B.dom[id][k])));
        maxd = Math.max(maxd, d);
        if (d > 0.01) bad++;
      }
      t.eq(bad, 0, `nodes outside collapsed ${gone} moved`);
      t.ok(cmp >= 1, `compared ${cmp} nodes`);
      t.note(`collapse ${gone} -> '${path}' at step ${i}: compared ${cmp} nodes, max DOM delta ${maxd.toFixed(4)} px`);
      cur = path;
    }
    prev = await probe(p, cur);
    prevZoom = zs[i];
    if (!cur) break;
  }
  t.eq(paths, E2 ? [E2, E1, ''] : [E1, ''], '(a) expanded path shrinks one level at a time down to the landscape');
  t.ok(changes.every((c) => c.hist === 1), `each collapse adds exactly one history entry: ${JSON.stringify(changes.map((c) => c.hist))}`);
  t.ok(sawMidChild > 0, '(d) saw children at an opacity strictly between 0 and 1 before the collapse');
  t.note(`mid-ramp child samples ${sawMidChild}; mid-ramp label samples ${sawMidLabel}; collapse ratios ${changes.map((c) => c.ratio.toFixed(3)).join(', ')}; landscape fit zoom ${zL.toFixed(4)} reached before the last collapse: ${(collapseAt[E1] ?? 0) >= zL ? 'no' : 'yes'}`);

  // ---------------------------------------------------------------- 2. zooming back in never expands anything
  {
    const endPath = pathOf(await hashOf(p));
    const upTo = fit[deep] * 1.5;
    const z0 = (await snapshot(p)).vp.zoom;
    const h0 = await hashOf(p), hist0 = (await probe(p, null)).hist;
    for (let i = 1; i <= 24; i++) {
      await zoomTo(p, z0 * (upTo / z0) ** (i / 24));
      t.eq(pathOf(await hashOf(p)), endPath, `zoom-in step ${i} must not change the path`);
    }
    t.eq(await hashOf(p), h0, 'hash unchanged by zooming in');
    t.eq((await probe(p, null)).hist, hist0, 'no history entry added by zooming in');
    t.eq(await p.locator('.react-flow__node[data-expanded=true]').count(), 0, 'no expanded frame after zooming in');
  }

  // ---------------------------------------------------------------- 3. hysteresis: wiggle +-3% around the threshold
  {
    await open(p, srv.url, '#/m/' + deep);
    const zt = 0.5 * fit[deep];
    await zoomTo(p, zt * 1.03); // just inside: still expanded
    const start = await probe(p, null);
    t.eq(pathOf(start.hash), deep, 'above the threshold it stays expanded');
    let n = 0, last = pathOf(start.hash);
    for (let i = 0; i < 20; i++) {
      await zoomTo(p, zt * (i % 2 ? 1.03 : 0.97));
      const h = pathOf(await hashOf(p));
      if (h !== last) { n++; last = h; }
    }
    const end = await probe(p, null);
    t.ok(n <= 1, `wiggling +-3% around the threshold changed the path ${n} times (max 1)`);
    t.ok(end.hist - start.hist <= 1, `wiggle added ${end.hist - start.hist} history entries (max 1)`);
    t.note(`wiggle: ${n} state change(s), ${end.hist - start.hist} history entr${end.hist - start.hist === 1 ? 'y' : 'ies'}`);
  }

  // ---------------------------------------------------------------- 3b. the auto collapse is the same state change as Back
  {
    const stateOf = async () => { const s = await probe(p, null); return { hash: s.hash, rows: rowsOf(s.rows), sel: s.rows }; };
    await open(p, srv.url, '#/m/' + deep);
    // Back-equivalent: Escape on the canvas collapses the deepest frame
    await p.evaluate(() => document.querySelector('.canvas').dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true })));
    await raf(p);
    const viaBack = await stateOf();
    await open(p, srv.url, '#/m/' + deep);
    await zoomTo(p, 0.45 * fit[deep]);
    const viaZoom = await stateOf();
    t.eq(viaZoom.hash, viaBack.hash, 'hash after zoom-out collapse equals the hash after Back');
    t.eq(viaZoom.rows, viaBack.rows, 'tree aria-expanded/aria-selected after zoom-out collapse equal those after Back');
  }
  await p.context().close();

  // ---------------------------------------------------------------- 4. reduced motion: no intermediate opacity anywhere, state still correct
  {
    const r = await newPage(browser, errors, { reducedMotion: 'reduce' });
    await open(r, srv.url, '#/m/' + deep);
    let mid = 0, samples = 0, cur2 = deep;
    for (let i = 1; i <= N; i++) {
      await zoomTo(r, zs[i]);
      const s = await probe(r, cur2);
      const ops = [...Object.values(s.kids), ...Object.values(s.labels).map((l) => l.op)];
      samples += ops.length;
      mid += ops.filter((o) => o > 0 && o < 1).length;
      cur2 = pathOf(s.hash) || cur2;
    }
    t.eq(mid, 0, `reduced motion: ${mid} of ${samples} child/label opacity samples were strictly between 0 and 1`);
    t.eq(pathOf(await hashOf(r)), '', 'reduced motion: the state still ends on the landscape');
    await r.context().close();
  }

  // ---------------------------------------------------------------- 4b. real wheel events (what a mouse or trackpad does)
  {
    const w = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await open(w, srv.url, '#/m/' + deep);
    const box = await w.locator('.react-flow').boundingBox();
    await w.mouse.move(box.x + box.width / 2, box.y + box.height / 2);
    let n = 0;
    while (pathOf(await hashOf(w)) !== '' && n < 150) { await w.mouse.wheel(0, 120); await raf(w, 2); await w.waitForTimeout(20); n++; }
    t.eq(pathOf(await hashOf(w)), '', `real wheel zoom-out collapses everything (${n} wheel events)`);
    await w.context().close();
  }

  // ---------------------------------------------------------------- 5. phone layout: the same logic (pinch drives the same viewport)
  {
    const ph = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, reducedMotion: 'no-preference' });
    const f = await fitOf(ph, srv, '#/m/' + deep);
    await open(ph, srv.url, '#/m/' + deep);
    for (let i = 1; i <= 20; i++) await zoomTo(ph, f * 0.9 ** i * 0.8);
    const end = pathOf(await hashOf(ph));
    t.ok(end !== deep, `phone: zooming out collapses ${deep} (path now '${end}')`);
    await ph.context().close();
  }

  t.eq(errors, [], 'no console errors in zoom tests');
  console.log(`  zoom ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
