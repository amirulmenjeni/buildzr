// Label rules while zooming out: (2) the 9 px name floor holds only while the name fits its box and fades when it does not;
// (3) the name of every node never gets bigger on screen, the steps where a frame collapses included.
// Run: node tests/run.mjs --only labels --data <dir>
import { newPage, open, hashOf, zoomTo, fitOf, T } from './lib.mjs';

const FLOOR = 9;
const INNER = 0.8; // NAME_FIT.inner (zoomfx.ts): the share of its box's width a floored name may use
const FULL = 1, GONE = 1.25; // NAME_FIT.full / gone, as ratios of the text width to the inner width

/** The name of every drawn node, now: on-screen font size, opacity of the label (name x label wrapper), text width, box width. */
const names = (p) => p.evaluate(() => {
  const out = {};
  for (const n of document.querySelectorAll('.react-flow__node')) {
    const name = n.querySelector('[data-tier="0"]');
    const box = n.firstElementChild;
    if (!name || !box) continue;
    const range = document.createRange();
    range.selectNodeContents(name);
    const tr = range.getBoundingClientRect(), br = box.getBoundingClientRect();
    // the label only: its own opacity and its wrapper's (not the node's context opacity, nor the .fx children fade)
    const op = parseFloat(getComputedStyle(name).opacity) * parseFloat(getComputedStyle(name.parentElement).opacity);
    out[n.dataset.id] = { px: name.getBoundingClientRect().height / 1.25, op, textW: tr.width, boxW: br.width, left: tr.left - br.left,
      expanded: n.querySelector('[data-role=frame-label]') !== null, boundary: !!n.querySelector('.c4b') || box.classList.contains('c4b') };
  }
  return out;
});

export default async function labels(browser, srv, F, name) {
  const t = new T(`labels:${name}`);
  const errors = [];
  const E2 = F.expandable.find((id) => F.parentOf(id) && F.expandable.includes(F.parentOf(id)));
  const deep = E2 ?? F.expandable[0];
  if (!deep) { t.note('nothing expandable: skipped'); return t; }

  for (const reduced of ['no-preference', 'reduce']) {
    const p = await newPage(browser, errors, { reducedMotion: reduced });
    const zDeep = await fitOf(p, srv, '#/m/' + deep);
    const zL = await fitOf(p, srv, '#/m');
    await open(p, srv.url, '#/m/' + deep);
    const zEnd = zL * 0.03;
    const N = 60;
    let prev = await names(p);
    let sawFade = 0, sawFloored = 0, floorFits = 0, collapses = 0, lastHash = await hashOf(p), maxRatio = 0;
    const lastOp = {};
    for (let i = 1; i <= N; i++) {
      await zoomTo(p, zDeep * (zEnd / zDeep) ** (i / N));
      const now = await names(p);
      const h = await hashOf(p);
      if (h !== lastHash) { collapses++; lastHash = h; }
      for (const [id, l] of Object.entries(now)) {
        // (3) no name grows on screen, collapse steps included
        if (id in prev) t.ok(l.px <= prev[id].px * 1.005 + 0.01, // 0.5%: the line box snaps to 1/64 local px, which at small local font sizes is about 0.15% of the measured size
           `name of ${id} grew ${prev[id].px.toFixed(3)} -> ${l.px.toFixed(3)} px at step ${i} (${h})`);
        if (l.expanded) continue; // expanded frames have their own size-based fade (zoom.mjs)
        // (2) floor, but fade when it does not fit
        const inner = INNER * l.boxW - (l.boundary ? l.left : 0);
        const ratio = l.textW / inner;
        if (l.px >= FLOOR - 0.05) sawFloored += l.px < FLOOR + 0.05 ? 1 : 0;
        if (ratio <= FULL + 0.005) {
          floorFits++;
          t.ok(reduced === 'reduce' ? l.op >= 0.95 : l.op >= 0.95, `${id}: text ${l.textW.toFixed(1)} fits ${inner.toFixed(1)} px but opacity ${l.op.toFixed(2)} (step ${i})`);
          t.ok(l.px >= FLOOR - 0.05, `${id}: fits but is only ${l.px.toFixed(2)} px (floor ${FLOOR}) at step ${i}`);
        } else {
          if (reduced === 'no-preference') {
            const want = Math.max(0, Math.min(1, (GONE - ratio) / (GONE - FULL)));
            t.ok(Math.abs(l.op - want) <= 0.08, `${id}: ratio ${ratio.toFixed(3)} opacity ${l.op.toFixed(3)}, want ${want.toFixed(3)} (step ${i}; tolerance covers canvas-vs-DOM text width, about 1%)`);
            if (l.op > 0.02 && l.op < 0.98) sawFade++;
            if (id in lastOp) t.ok(l.op <= lastOp[id] + 0.011, `${id}: opacity went up ${lastOp[id].toFixed(3)} -> ${l.op.toFixed(3)} while zooming out (step ${i})`);
            if (ratio >= 1.4) t.ok(l.op <= 0.05, `${id}: ratio ${ratio.toFixed(2)} but opacity ${l.op.toFixed(3)}`);
          } else {
            t.ok(l.op === 0 || l.op === 1, `${id}: reduced motion opacity ${l.op} is not 0 or 1`);
          }
        }
        // never wider than the box while it can be seen
        if (l.op > 0.05) t.ok(l.textW <= l.boxW + 0.5, `${id}: text ${l.textW.toFixed(1)} px wider than its box ${l.boxW.toFixed(1)} px at opacity ${l.op.toFixed(2)} (step ${i})`);
        lastOp[id] = l.op;
        maxRatio = Math.max(maxRatio, ratio);
      }
      prev = now;
    }
    t.note(`${reduced}: ${N} steps ${zDeep.toFixed(3)} -> ${zEnd.toFixed(4)}, ${collapses} collapse step(s); fits-checks ${floorFits}, samples at the floor ${sawFloored}, mid-fade samples ${sawFade}, max text/inner ${maxRatio.toFixed(2)}`);
    if (reduced === 'no-preference') t.ok(sawFade > 0, 'saw labels mid-fade');
    t.ok(sawFloored > 0, 'saw labels at the floor');
    t.ok(maxRatio > GONE, 'the sweep reached labels that no longer fit');
    await p.context().close();
  }
  t.eq(errors, [], 'no console errors in label tests');
  console.log(`  labels ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
