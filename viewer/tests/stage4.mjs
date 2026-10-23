// Stage 4: keyboard-only path, axe-core, reduced motion, phone layout.
import path from 'node:path';
import { createRequire } from 'node:module';
import { newPage, open, settle, snapshot, hashOf, T, ROOT } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const nodeSel = (id) => `.react-flow__node[data-id="${id}"]`;
const active = (p) => p.evaluate(() => { const a = document.activeElement; return { id: a?.dataset?.id ?? null, role: a?.getAttribute('role') ?? null, tag: a?.tagName }; });
const frames = (p) => p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));

async function axeRun(p, label, t) {
  await p.addScriptTag({ path: AXE });
  const res = await p.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ['violations'] });
    return r.violations.map((v) => ({ id: v.id, impact: v.impact, n: v.nodes.length, help: v.help, sample: v.nodes[0].target.join(' ') + ' :: ' + v.nodes[0].failureSummary?.split('\n')[1] }));
  });
  const bad = res.filter((v) => v.impact === 'serious' || v.impact === 'critical');
  t.note(`axe ${label}: ${res.length} violations (${bad.length} serious/critical)${res.length ? ' ' + res.map((v) => `${v.id}[${v.impact}]x${v.n}`).join(', ') : ''}`);
  for (const v of bad) t.ok(false, `axe ${label}: ${v.id} (${v.impact}) ${v.help} -- ${v.sample}`);
  return res;
}

export default async function stage4(browser, srv, F, name) {
  const t = new T(`stage4:${name}`);
  const errors = [];

  // ---- 1. keyboard only: reach, open and inspect a component through the tree alone
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const comp = F.els.find((e) => e.type === 'Component') ?? F.els.find((e) => e.parent) ?? F.els[F.els.length - 1];
    const chain = [];
    for (let id = comp.id; id; id = F.byId.get(id).parent) chain.unshift(id);
    // Tab from the top of the page until the tree takes focus (a single tab stop: roving tabindex)
    t.eq(await p.locator('[role=treeitem][tabindex="0"]').count(), 1, 'exactly one tree item is in the tab order');
    await p.evaluate(() => document.body.focus());
    let tabs = 0;
    while ((await active(p)).role !== 'treeitem' && tabs < 60) { await p.keyboard.press('Tab'); tabs++; }
    t.eq((await active(p)).role, 'treeitem', `Tab reaches the tree (after ${tabs} tabs)`);
    // Home / End
    await p.keyboard.press('End');
    await frames(p);
    const last = (await active(p)).id;
    await p.keyboard.press('Home');
    await frames(p);
    t.eq((await active(p)).id, F.els.find((e) => !e.parent).id, 'Home goes to the first item');
    await p.keyboard.press('End');
    await frames(p);
    t.eq((await active(p)).id, last, 'End goes to the last visible item');
    await p.keyboard.press('Home');
    await frames(p);
    // walk down to the component, opening parents with ArrowRight
    for (const id of chain) {
      let guard = 0;
      while ((await active(p)).id !== id && guard++ < 80) { await p.keyboard.press('ArrowDown'); await frames(p); }
      t.eq((await active(p)).id, id, `reached ${id} with ArrowDown`);
      if (id !== comp.id) {
        const li = p.locator(`[role=treeitem][data-id="${id}"]`);
        if ((await li.getAttribute('aria-expanded')) === 'false') await p.keyboard.press('ArrowRight');
        t.eq(await li.getAttribute('aria-expanded'), 'true', `ArrowRight opened ${id}`);
      }
    }
    // levels and expansion state
    const lv = await p.locator('[role=treeitem]').evaluateAll((l) => l.map((x) => [x.dataset.id, x.getAttribute('aria-level'), x.getAttribute('aria-expanded')]));
    for (const [id, level, exp] of lv) {
      t.eq(level, String(id.split('/').length), `aria-level of ${id}`);
      t.eq(exp === null, F.treeById.get(id).children.length === 0, `aria-expanded only on parents (${id})`);
    }
    // ArrowLeft: leaf -> parent; ArrowLeft on an open parent collapses it
    await p.keyboard.press('ArrowLeft');
    await frames(p);
    t.eq((await active(p)).id, comp.parent, 'ArrowLeft on a leaf goes to its parent');
    await p.keyboard.press('ArrowLeft');
    await frames(p);
    t.eq(await p.locator(`[role=treeitem][data-id="${comp.parent}"]`).getAttribute('aria-expanded'), 'false', 'ArrowLeft collapses an open parent');
    await p.keyboard.press('ArrowRight');
    await p.keyboard.press('ArrowRight'); // first child
    // type-ahead: type the component's name
    await p.keyboard.press('Home');
    await frames(p);
    await p.keyboard.type(comp.name.slice(0, 3).toLowerCase(), { delay: 20 });
    const ta = (await active(p)).id;
    t.ok(ta !== null && F.byId.get(ta).name.toLowerCase().startsWith(comp.name.slice(0, 3).toLowerCase()), `type-ahead "${comp.name.slice(0, 3)}" jumps to ${ta}`);
    // go to the component and open it
    let guard = 0;
    while ((await active(p)).id !== comp.id && guard++ < 80) { await p.keyboard.press('ArrowDown'); await frames(p); }
    await p.keyboard.press('Enter');
    await p.waitForSelector(`[data-selected-id="${comp.id}"]`);
    t.ok((await hashOf(p)).includes(`sel=${comp.id}`), `Enter selects the component: ${await hashOf(p)}`);
    t.eq(await p.locator(`[data-selected-id="${comp.id}"] h2`).textContent(), comp.name, 'inspector shows the component');
    t.eq(await p.locator('[role=complementary]').count(), 1, 'inspector is a complementary landmark');
    t.ok((await p.locator('[data-testid=live]').textContent()).length >= 0, 'live region present');
    // Escape on the canvas collapses (focus a canvas node, then Escape)
    await p.locator(nodeSel(comp.id)).focus();
    t.eq((await active(p)).tag, 'DIV', 'canvas node is keyboard-focusable');
    const before = await hashOf(p);
    await p.keyboard.press('Escape');
    await frames(p);
    t.ok((await hashOf(p)) !== before, `Escape collapses the canvas path: ${before} -> ${await hashOf(p)}`);
    // Enter on a focused canvas frame expands it
    const sys = F.expandable.find((id) => !F.parentOf(id));
    await open(p, srv.url, '#/m');
    await p.locator(nodeSel(sys)).focus();
    await p.keyboard.press('Enter');
    await p.waitForFunction((s) => location.hash.startsWith('#/m/' + s), sys);
    t.ok(true, 'Enter on a focused frame expands it');
    await p.context().close();
  }

  // ---- 2. axe
  for (const [dev, vp] of [['desktop', { width: 1600, height: 1000 }], ['phone', { width: 390, height: 844 }]]) {
    const sys = F.expandable.find((id) => !F.parentOf(id));
    const kid = F.byId.get(sys).children[0];
    const states = [['landscape', '#/m'], ['expanded', `#/m/${sys}?sel=${kid}`]];
    for (const [st, hash] of states) {
      const p = await newPage(browser, errors, { viewport: vp });
      await open(p, srv.url, hash);
      if (dev === 'phone') { await p.locator('button[aria-label="Open model navigation"]').click(); await p.waitForTimeout(300); await axeRun(p, `${dev}/${st}/drawer`, t); await p.keyboard.press('Escape'); await p.waitForTimeout(300); }
      await axeRun(p, `${dev}/${st}`, t);
      await p.context().close();
    }
  }

  // ---- 3. reduced motion: the viewport reaches its final value in the first frame; with motion it animates
  {
    const sys = F.expandable.find((id) => !F.parentOf(id));
    for (const rm of ['reduce', 'no-preference']) {
      const p = await newPage(browser, errors, { reducedMotion: rm });
      await open(p, srv.url, '#/m');
      const fin = await p.evaluate(async (s) => {
        const vp0 = window.__viewer.viewport();
        document.querySelector(`.react-flow__node[data-id="${s}"]`).click();
        // wait for the scene to load (the camera request is served when it is composed), then sample frame by frame
        const frames = [];
        const t0 = performance.now();
        await new Promise((res) => { const tick = () => { const v = window.__viewer.viewport(); frames.push([performance.now() - t0, v.zoom]); if (performance.now() - t0 > 900) res(); else requestAnimationFrame(tick); }; tick(); });
        return { vp0: vp0.zoom, frames };
      }, sys);
      const zs = fin.frames.map((f) => f[1]);
      const final = zs[zs.length - 1];
      const firstChange = fin.frames.findIndex((f) => Math.abs(f[1] - fin.vp0) > 1e-6);
      const reached = fin.frames.findIndex((f) => Math.abs(f[1] - final) < 1e-6);
      const intermediate = zs.filter((z) => Math.abs(z - fin.vp0) > 1e-6 && Math.abs(z - final) > 1e-6).length;
      t.note(`reducedMotion=${rm}: zoom ${fin.vp0.toFixed(3)} -> ${final.toFixed(3)}; first change at frame ${firstChange}, final reached at frame ${reached}, intermediate frames ${intermediate}`);
      if (rm === 'reduce') { t.ok(intermediate === 0 && firstChange === reached && firstChange >= 0, 'reduced motion: the viewport jumps to its final value in one frame'); }
      else t.ok(intermediate > 5, `with motion the camera animates (${intermediate} intermediate frames)`);
      await p.context().close();
    }
  }

  // ---- 4. phone: no horizontal scroll, sheet on tap, tap targets >= 44 px
  {
    const vp = { width: 390, height: 844 };
    const sys = F.expandable.find((id) => !F.parentOf(id));
    const kid = F.byId.get(sys).children[0];
    const small = [];
    const checkTargets = async (p, label) => {
      const bad = await p.evaluate(() => {
        const out = [];
        const vis = (el) => { const r = el.getBoundingClientRect(); const cs = getComputedStyle(el); return r.width > 0 && r.height > 0 && cs.visibility !== 'hidden' && !el.closest('[inert]') && !el.closest('[aria-hidden=true]') && r.right > 0 && r.left < innerWidth && r.bottom > 0 && r.top < innerHeight; };
        for (const el of document.querySelectorAll('button, a[href], input, select, [role=tab], [role=treeitem] > .row')) {
          if (!vis(el)) continue;
          if (el.closest('.react-flow__node')) continue; // canvas nodes are zoomed by the camera
          const r = el.getBoundingClientRect();
          if (r.width < 44 - 0.5 || r.height < 44 - 0.5) out.push(`${el.tagName.toLowerCase()}${el.className ? '.' + String(el.className).split(' ')[0] : ''}[${(el.getAttribute('aria-label') || el.textContent || '').trim().slice(0, 24)}] ${r.width.toFixed(0)}x${r.height.toFixed(0)}`);
        }
        return out;
      });
      for (const b of bad) small.push(`${label}: ${b}`);
      return bad;
    };
    for (const [st, hash] of [['landscape', '#/m'], ['system', `#/m/${sys}`], ['container', `#/m/${F.expandable.find((id) => F.parentOf(id)) ?? sys}`]]) {
      const p = await newPage(browser, errors, { viewport: vp, hasTouch: true, isMobile: true });
      await open(p, srv.url, hash);
      const sw = await p.evaluate(() => [document.documentElement.scrollWidth, document.body.scrollWidth, innerWidth]);
      t.ok(sw[0] <= sw[2] && sw[1] <= sw[2], `phone ${st}: no horizontal scroll (scrollWidth ${sw[0]}/${sw[1]} <= ${sw[2]})`);
      await checkTargets(p, `${st}`);
      await p.context().close();
    }
    const p = await newPage(browser, errors, { viewport: vp, hasTouch: true, isMobile: true });
    await open(p, srv.url, `#/m/${sys}`);
    t.eq(await p.locator('.left').getAttribute('data-open'), null, 'drawer closed by default');
    await p.locator('button[aria-label="Open model navigation"]').tap();
    await p.waitForTimeout(300);
    t.eq(await p.locator('.left').getAttribute('data-open'), 'true', 'menu button opens the drawer');
    await checkTargets(p, 'drawer/model');
    t.eq(await p.locator('[role=tab]').count(), 2, 'drawer has the Model and Views tabs');
    await p.locator('[role=tab]', { hasText: 'Views' }).tap();
    t.ok(await p.locator('.views button').first().isVisible(), 'Views tab shows the views');
    await checkTargets(p, 'drawer/views');
    await p.locator('[role=tab]', { hasText: 'Model' }).tap();
    await p.locator(`[role=treeitem][data-id="${kid}"] > .row`).tap();
    await p.waitForTimeout(300);
    t.eq(await p.locator('.left').getAttribute('data-open'), null, 'choosing a tree item closes the drawer');
    t.eq(await p.locator('.sheet-wrap').getAttribute('data-sheet'), 'peek', 'the inspector sheet opens at peek');
    await checkTargets(p, 'sheet');
    await p.locator('button[aria-label="Grow inspector"]').tap(); await p.waitForTimeout(300);
    t.eq(await p.locator('.sheet-wrap').getAttribute('data-sheet'), 'half', 'sheet grows to half');
    await p.locator('button[aria-label="Grow inspector"]').tap(); await p.waitForTimeout(300);
    t.eq(await p.locator('.sheet-wrap').getAttribute('data-sheet'), 'full', 'sheet grows to full');
    await checkTargets(p, 'sheet/full');
    await p.locator('button[aria-label="Close inspector"]').tap(); await p.waitForTimeout(300);
    t.eq(await p.locator('.sheet-wrap').getAttribute('data-sheet'), 'closed', 'sheet closes');
    // tap on a canvas node selects it (no expand) and opens the sheet
    await open(p, srv.url, '#/m');
    const top = F.expandable.find((id) => !F.parentOf(id));
    const box = await p.locator(nodeSel(top)).boundingBox();
    await p.touchscreen.tap(box.x + 6, box.y + box.height / 2);
    await p.waitForTimeout(300);
    t.ok((await hashOf(p)).startsWith('#/m?sel=' + top), `phone tap selects without expanding: ${await hashOf(p)}`);
    t.eq(await p.locator('.sheet-wrap').getAttribute('data-sheet'), 'peek', 'tap opens the peek sheet');
    await p.locator('[data-action=open]').tap();
    await p.waitForFunction((s) => location.hash.startsWith('#/m/' + s), top);
    t.ok(true, '"Open" in the sheet expands');
    // tap inside an expanded frame zooms to that child
    await p.waitForTimeout(300);
    const z0 = await p.evaluate(() => window.__viewer.viewport().zoom);
    const kidBox = await p.locator(nodeSel(kid)).boundingBox();
    await p.touchscreen.tap(kidBox.x + kidBox.width / 2, kidBox.y + kidBox.height / 2);
    await p.waitForFunction((z) => window.__viewer.viewport().zoom > z * 1.05, z0, { timeout: 5000 }).catch(() => {});
    const z1 = await p.evaluate(() => window.__viewer.viewport().zoom);
    t.ok(z1 > z0 * 1.05, `a tap inside an expanded frame zooms to the child (${z0.toFixed(2)} -> ${z1.toFixed(2)})`);
    await p.context().close();
    if (small.length) { t.note(`tap targets under 44 px: ${small.length}`); for (const s of small) t.ok(false, `tap target ${s}`); }
    else t.note('all measured tap targets >= 44 px');
  }
  t.eq(errors, [], 'no console errors in stage 4');
  return t;
}
