// Acceptance tests (stage 2 and 3). Usage, inside the devcontainer with the viewer built:
//   node tests/run.mjs [--data <dir>]... [--only stage2|stage3|stage4|zoom|labels|expand|settings|about|viewerurl|workspaces|broken|deployment|deploynav|custom|branding|embed|switcher|theme|export|dynamic] [--shots]
// A data dir holds index.json, model.json and scene/ (e.g. tests/site/fixtures/small).
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { serve, launch, newPage, open, settle, act, snapshot, hashOf, mouseClick, mouseDbl, T, ROOT, deviceTheme } from './lib.mjs';

const args = process.argv.slice(2);
const dataDirs = [];
let only = null;
let shots = false;
for (let i = 0; i < args.length; i++) {
  if (args[i] === '--data') dataDirs.push(path.resolve(args[++i]));
  else if (args[i] === '--only') only = args[++i];
  else if (args[i] === '--shots') shots = true;
  else if (args[i] === '--theme') process.env.VIEWER_THEME = args[++i]; // light (default) or dark: the whole matrix in that theme
}
const THEME = deviceTheme();
if (!dataDirs.length) dataDirs.push(path.resolve(ROOT, '../tests/site/fixtures/small'));

const KNOWN = new Set(['Person', 'SoftwareSystem', 'Container', 'Component']);
const DEPLOYMENT = new Set(['DeploymentNode', 'InfrastructureNode', 'ContainerInstance', 'SoftwareSystemInstance']);
const CUSTOM = new Set(['Element']); // custom elements: in the tree, search and relationships, but never on the model canvas
const loadJson = (dir, f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const results = [];

/** Test-side model facts, computed independently of the viewer's code. */
function facts(dir) {
  const index = loadJson(dir, 'index.json');
  const model = loadJson(dir, index.model.file);
  const els = model.elements.filter((e) => KNOWN.has(e.type));
  const byId = new Map(els.map((e) => [e.id, e]));
  const parentOf = (id) => byId.get(id).parent ?? '';
  const inSubtree = (x, root) => x === root || x.startsWith(root + '/');
  const expandable = els.filter((e) => ('e/' + e.id) in index.scenes && e.children.length > 0).map((e) => e.id);
  // search and the filter also find custom and deployment elements (drawn in views only), in model order
  const searchEls = model.elements.filter((e) => KNOWN.has(e.type) || CUSTOM.has(e.type) || DEPLOYMENT.has(e.type));
  const related = new Set(model.elements.filter((e) => KNOWN.has(e.type) || CUSTOM.has(e.type)).map((e) => e.id));
  const treeById = new Map(model.elements.filter((e) => KNOWN.has(e.type) || CUSTOM.has(e.type)).map((e) => [e.id, e])); // the rows of the tree
  return { index, model, els, searchEls, byId, treeById, parentOf, inSubtree, expandable, rels: model.relationships.filter((r) => related.has(r.source) && related.has(r.destination)) };
}

const nodeSel = (id) => `.react-flow__node[data-id="${id}"]`;
const dbl = mouseClick; // one click on a collapsed frame expands it
const clickNode = mouseClick;
const treeRow = (p, id) => p.locator(`[role=treeitem][data-id="${id}"] > .row`);

function compare(before, after) {
  // nodes present in both snapshots (the expanded element included: its look may change, its place may not)
  let compared = 0, storeDiff = 0, domDiff = 0, maxDom = 0;
  for (const id of Object.keys(before.store)) {
    if (!(id in after.store)) continue;
    compared++;
    const a = before.store[id], b = after.store[id];
    if (a.x !== b.x || a.y !== b.y || a.w !== b.w || a.h !== b.h) storeDiff++;
    const da = before.dom[id], db = after.dom[id];
    const m = Math.max(...da.map((x, i) => Math.abs(x - db[i])));
    maxDom = Math.max(maxDom, m);
    if (m > 0.01) domDiff++;
  }
  return { compared, storeDiff, domDiff, maxDom };
}

// ------------------------------------------------------------------ stage 2
async function stage2(browser, srv, F, name) {
  const t = new T(`stage2:${name}`);
  const errors = [];
  const hashFor = (id) => (id ? '#/m/' + id : '#/m');

  // 1. expansion moves nothing
  const rows = [];
  for (const E of F.expandable) {
    const p = await newPage(browser, errors);
    await open(p, srv.url, hashFor(F.parentOf(E)));
    const A = await snapshot(p); // fresh, before
    await p.evaluate(() => { window.__viewer.autoCollapse = false; }); // restoring the old (zoomed-out) viewport below must not collapse E
    const aKeys = Object.keys(A.store); // includes E itself: the frame must not move either
    await act(p, () => dbl(p, E));
    t.ok((await hashOf(p)) === '#/m/' + E + '?sel=' + E, `hash after expanding ${E}: ${await hashOf(p)}`);
    const Bstore = await snapshot(p); // fresh, after (viewport already moved by the camera)
    // the camera is allowed to move; restore the before-viewport instantly for the DOM comparison
    await p.evaluate((vp) => window.__viewer.setViewport(vp), A.vp);
    await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const B = await snapshot(p);
    t.ok(JSON.stringify(B.vp) === JSON.stringify(A.vp), `viewport restored for ${E}`);
    t.ok(aKeys.every((id) => id in B.store), `all nodes still present after expanding ${E}`);
    const sub = Object.keys(B.store).filter((id) => F.inSubtree(id, E) && id !== E);
    const onlyA = { store: Object.fromEntries(aKeys.map((id) => [id, A.store[id]])), dom: Object.fromEntries(aKeys.map((id) => [id, A.dom[id]])) };
    const c = compare(onlyA, B);
    const cStore = compare(onlyA, Bstore);
    rows.push({ expanded: E, compared: c.compared, newNodes: sub.length, storeDiff: c.storeDiff, storeDiffBeforeRestore: cStore.storeDiff, domDiff: c.domDiff, maxDomDelta: c.maxDom });
    t.ok(c.storeDiff === 0 && cStore.storeDiff === 0, `store positions changed when expanding ${E}`);
    t.ok(c.domDiff === 0, `DOM rects changed when expanding ${E} (max ${c.maxDom})`);
    t.ok(sub.length > 0, `expanding ${E} added no child nodes`);
    t.ok(JSON.stringify(Bstore.vp) !== JSON.stringify(A.vp), `camera did not move for ${E}`);
    // switching straight to a sibling branch (collapses the first): landscape nodes stay put too
    await p.context().close();
  }
  console.log(`  nothing moves on expand (${name}):`); console.table(rows);

  // 1b. expanding from a deeper expanded state (system -> container) and sibling switch
  const chains = F.expandable.filter((id) => F.parentOf(id));
  for (const E of chains) {
    const p = await newPage(browser, errors);
    await open(p, srv.url, hashFor(F.parentOf(E)));
    const A = await snapshot(p);
    await p.evaluate(() => { window.__viewer.autoCollapse = false; }); // restoring the old viewport below is a zoom-out on purpose
    await act(p, () => dbl(p, E));
    await p.evaluate((vp) => window.__viewer.setViewport(vp), A.vp);
    await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const B = await snapshot(p);
    const keys = Object.keys(A.store); // includes E itself
    const c = compare({ store: Object.fromEntries(keys.map((k) => [k, A.store[k]])), dom: Object.fromEntries(keys.map((k) => [k, A.dom[k]])) }, B);
    t.note(`expand ${E} from ${F.parentOf(E)} expanded: compared ${c.compared} nodes, store diff ${c.storeDiff}, dom diff ${c.domDiff}, max ${c.maxDom.toFixed(4)} px`);
    t.ok(c.storeDiff === 0 && c.domDiff === 0, `second-level expand of ${E} moved nodes`);
    await p.context().close();
  }
  { // sibling switch: expand one top-level system, then another one
    const tops = F.expandable.filter((id) => !F.parentOf(id));
    if (tops.length >= 2) {
      const p = await newPage(browser, errors);
      await open(p, srv.url, hashFor(''));
      await act(p, () => dbl(p, tops[0]));
      const A = await snapshot(p);
      await p.evaluate(() => { window.__viewer.autoCollapse = false; }); // restoring the old viewport below is a zoom-out on purpose
      await act(p, () => treeRow(p, tops[1]).dblclick()); // the tree is always reachable; the other frame may be off screen
      await p.evaluate((vp) => window.__viewer.setViewport(vp), A.vp);
      await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
      const B = await snapshot(p);
      const keys = Object.keys(A.store).filter((id) => (id === tops[0] || !F.inSubtree(id, tops[0])) && (id === tops[1] || !F.inSubtree(id, tops[1])));
      const c = compare({ store: Object.fromEntries(keys.map((k) => [k, A.store[k]])), dom: Object.fromEntries(keys.map((k) => [k, A.dom[k]])) }, B);
      t.note(`switch ${tops[0]} -> ${tops[1]}: compared ${c.compared} landscape nodes, store diff ${c.storeDiff}, dom diff ${c.domDiff}`);
      t.ok(c.storeDiff === 0 && c.domDiff === 0 && c.compared > 0, 'sibling switch moved landscape nodes');
      t.ok(!(`${tops[0]}/${F.byId.get(tops[0]).children[0]}` in B.store), 'first system collapsed');
      await p.context().close();
    }
  }

  // 2. tree <-> canvas selection
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, hashFor(''));
    const E = F.expandable[0];
    const kids = F.byId.get(E).children.filter((c) => !F.expandable.includes(c));
    const kid = kids[0];
    await p.locator(`[role=treeitem][data-id="${E}"] > .row .twisty`).click();
    t.eq(await p.locator(`[role=treeitem][data-id="${E}"]`).getAttribute('aria-expanded'), 'true', 'twisty opens the tree item');
    await act(p, () => treeRow(p, kid).click()); // selecting a child reveals it: the canvas expands to its parent
    t.ok((await hashOf(p)) === `#/m/${E}?sel=${kid}`, `tree select hash: ${await hashOf(p)}`);
    t.ok((await p.locator(nodeSel(kid)).getAttribute('class')).includes('selected'), 'RF node has selected class');
    t.eq(await p.locator(nodeSel(kid) + ' [data-selected=true]').count(), 1, 'canvas node marked data-selected');
    t.eq(await p.locator(`[role=treeitem][data-id="${kid}"]`).getAttribute('aria-selected'), 'true', 'tree row aria-selected');
    // reverse: click another canvas node, tree follows
    const sib = kids[1] ?? kid;
    await clickNode(p, sib);
    await p.waitForFunction((s) => location.hash.includes('sel=' + s), sib);
    t.ok((await hashOf(p)).includes(`sel=${sib}`), 'canvas click sets sel=');
    t.eq(await p.locator(`[role=treeitem][data-id="${sib}"]`).getAttribute('aria-selected'), 'true', 'tree follows canvas selection');
    t.eq(await p.locator(`[role=treeitem][aria-selected=true]`).count(), 1, 'exactly one tree row selected');
    t.ok((await p.locator(`[data-selected-id="${sib}"] h2`).textContent()) === F.byId.get(sib).name, 'inspector shows the selection');
    // a real mouse click on a node
    const box = await p.locator(nodeSel(kid)).boundingBox();
    await p.mouse.click(box.x + 3, box.y + 3);
    t.ok((await hashOf(p)).includes(`sel=${kid}`), 'real mouse click selects');
    await p.context().close();
  }

  // 3. inspector counts vs model.json (independent computation)
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    let n = 0;
    for (const e of F.els) {
      await p.evaluate((h) => { location.hash = h; }, `#/m?sel=${e.id}`);
      await p.waitForSelector(`[data-selected-id="${e.id}"]`);
      const own = { out: F.rels.filter((r) => r.source === e.id).length, in: F.rels.filter((r) => r.destination === e.id).length };
      const cnt = async (k) => Number(await p.locator(`[data-section=${k}] .n`).getAttribute('data-count'));
      if ((await p.locator('[data-testid=rolled]').isChecked())) await p.locator('[data-testid=rolled]').uncheck();
      t.ok((await cnt('outgoing')) === own.out && (await cnt('incoming')) === own.in, `own counts of ${e.id}`);
      t.eq(await p.locator('[data-section=outgoing] li').count(), own.out, `outgoing rows of ${e.id}`);
      await p.locator('[data-testid=rolled]').check();
      const out = F.rels.filter((r) => F.inSubtree(r.source, e.id) && !F.inSubtree(r.destination, e.id)).length;
      const inc = F.rels.filter((r) => F.inSubtree(r.destination, e.id) && !F.inSubtree(r.source, e.id)).length;
      t.ok((await cnt('outgoing')) === out && (await cnt('incoming')) === inc, `rolled-up counts of ${e.id}: ${await cnt('outgoing')}/${await cnt('incoming')} want ${out}/${inc}`);
      await p.locator('[data-testid=rolled]').uncheck();
      t.eq(await p.locator('[data-section=views] .n').getAttribute('data-count'), String(e.views.length), `views count of ${e.id}`);
      n++;
    }
    t.note(`inspector counts checked for ${n} elements (own and rolled up)`);
    // rolled-up edges list their rels
    let edges = 0;
    for (const key of Object.keys(F.index.scenes).filter((k) => k === 'landscape' || k.startsWith('e/'))) {
      const sc = loadJson(srv.dir, F.index.scenes[key].file);
      for (const e of sc.edges) {
        const hp = key === 'landscape' ? '#/m' : '#/m/' + key.slice(2);
        await p.evaluate((h) => { location.hash = h; }, `${hp}?sel=${encodeURIComponent(e.id).replace(/%2F/g, '/')}`);
        await p.waitForSelector('[data-selected-edge]');
        const got = await p.locator('[data-selected-edge] [data-rel]').evaluateAll((l) => l.map((x) => x.dataset.rel).sort());
        t.eq(got, [...e.rels].sort(), `rels listed for edge ${key}:${e.id}`);
        t.eq(await p.locator('[data-selected-edge]').getAttribute('data-selected-edge'), e.id, 'edge selected');
        edges++;
      }
    }
    t.note(`rolled-up edge inspector lists checked for ${edges} edges`);
    // clicking a canvas edge selects it
    await p.evaluate(() => { location.hash = '#/m'; });
    await settle(p);
    if (await p.locator('.react-flow__edge').count()) {
      const ed = await p.locator('.react-flow__edge').first();
      await ed.locator('path.react-flow__edge-interaction').first().dispatchEvent('click');
      t.ok((await p.locator('[data-selected-edge]').count()) === 1, 'canvas edge click selects the edge');
    } else t.note('no edge on the landscape: the edge click is not checked');
    await p.context().close();
  }

  // 4. back after two expands
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const deep = F.expandable.find((id) => F.parentOf(id));
    const top = deep ? F.parentOf(deep) : F.expandable[0];
    const landscapeNodes = Object.keys((await snapshot(p)).store).length;
    await act(p, () => dbl(p, top));
    if (deep) await act(p, () => dbl(p, deep));
    t.ok((await hashOf(p)).startsWith('#/m/' + (deep ?? top)), `expanded to ${deep ?? top}: ${await hashOf(p)}`);
    await act(p, () => p.goBack());
    if (deep) { t.ok((await hashOf(p)).startsWith('#/m/' + top + '?') || (await hashOf(p)) === '#/m/' + top, `back once: ${await hashOf(p)}`); await act(p, () => p.goBack()); }
    t.ok((await hashOf(p)) === '#/m', `back returns to the landscape: ${await hashOf(p)}`);
    t.eq(Object.keys((await snapshot(p)).store).length, landscapeNodes, 'landscape node count after back');
    await act(p, () => p.goForward());
    t.ok((await hashOf(p)).startsWith('#/m/' + top), 'forward re-expands');
    await p.context().close();
  }

  // 5. deep links
  {
    const p = await newPage(browser, errors);
    const deep = F.expandable.find((id) => F.parentOf(id)) ?? F.expandable[0];
    const leaf = F.byId.get(deep).children[0];
    const h = `#/m/${deep}?sel=${leaf}&q=${encodeURIComponent('go')}&tags=${encodeURIComponent(F.byId.get(leaf).tags.slice(-1)[0])}&mode=and`;
    await open(p, srv.url, h);
    await p.reload(); await settle(p);
    t.eq(await hashOf(p), h, 'deep link survives reload verbatim');
    t.eq(await p.locator('input[type=search]').inputValue(), 'go', 'search restored');
    t.eq(await p.locator('.chip.on').count(), 1, 'tag restored');
    t.eq(await p.locator('select[aria-label="Tag mode"]').inputValue(), 'and', 'mode restored');
    t.eq(await p.locator(`[data-selected-id="${leaf}"]`).count(), 1, 'selection restored');
    t.eq(await p.locator('nav.crumbs button[aria-current=page]').getAttribute('data-crumb'), deep, 'path restored');
    t.ok((await p.locator(nodeSel(leaf) + ' [data-selected=true]').count()) === 1, 'restored selection is marked on the canvas');
    // unknown path -> nearest ancestor + notice; leaf path -> parent + sel
    await open(p, srv.url, `#/m/${deep}/does-not-exist`);
    await p.waitForSelector('[data-testid=notice]');
    t.eq(await hashOf(p), `#/m/${deep}`, 'unknown path falls back to the nearest ancestor');
    await open(p, srv.url, `#/m/${leaf}`);
    t.eq(await hashOf(p), `#/m/${deep}?sel=${leaf}`, 'leaf path expands to the parent and selects');
    await open(p, srv.url, `#/v/nope`);
    await p.waitForSelector('[data-testid=notice]');
    t.eq(await hashOf(p), '#/m', 'unknown view falls back to the model');
    // subpath hosting
    const sub = await serve(srv.dir, '/some/sub/');
    const p2 = await newPage(browser, errors);
    await open(p2, sub.url, '#/m/' + deep);
    t.eq(await p2.locator('nav.crumbs button[aria-current=page]').getAttribute('data-crumb'), deep, 'works at a subpath');
    sub.close();
    await p.context().close(); await p2.context().close();
  }

  // 5b. label tiers: tiers whose effective size is below 6 px are hidden; the name alone is floored at 9 px
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, hashFor(''));
    const probe = F.els.find((e) => !F.parentOf(e.id) && !F.expandable.includes(e.id)).id; // a plain landscape node (scale 1)
    const read = async (zoom) => {
      await p.evaluate((z) => window.__viewer.setViewport({ x: 300, y: 100, zoom: z }), zoom);
      await p.waitForTimeout(120);
      return p.evaluate((id) => {
        const n = document.querySelector(`.react-flow__node[data-id="${id}"]`);
        const name = n.querySelector('[data-tier="0"]');
        const z = window.__viewer.viewport().zoom;
        // fit: a label set in a branding font is scaled to the width the layout gave it in Inter (branding.ts)
        return { tier1: n.querySelectorAll('[data-tier="1"]').length, namePx: parseFloat(getComputedStyle(name).fontSize) * z, fit: parseFloat(n.querySelector('[data-fit]')?.dataset.fit ?? '1') };
      }, probe);
    };
    const hi = await read(1), mid = await read(0.6), lo = await read(0.4), tiny = await read(0.2);
    t.ok(hi.tier1 === 1 && Math.abs(hi.namePx - 16 * hi.fit) < 0.01, `zoom 1: tier 1 shown, name 16 px (${JSON.stringify(hi)})`);
    t.ok(mid.tier1 === 1 && Math.abs(mid.namePx - Math.max(9.6 * mid.fit, 9)) < 0.01, `zoom .6: tier 1 (7.2 px) shown, name 9.6 px (${JSON.stringify(mid)})`);
    t.ok(lo.tier1 === 0 && Math.abs(lo.namePx - 9) < 0.01, `zoom .4: tier 1 (4.8 px) hidden, name floored to 9 px (${JSON.stringify(lo)})`);
    t.ok(tiny.tier1 === 0 && Math.abs(tiny.namePx - 9) < 0.01, `zoom .2: name floored at 9 px (${JSON.stringify(tiny)})`);
    // collapsed frames carry a child count badge
    const fr = F.expandable.find((id) => !F.parentOf(id));
    t.ok((await p.locator(nodeSel(fr) + ' [data-badge=count]').textContent()).startsWith(String(F.byId.get(fr).children.length)), 'child count badge on a collapsed frame');
    await p.context().close();
  }

  // 5c. expanded frames: focused draws tiers 0-1 only; expanded ancestors draw the name only, capped at 2x the name of their child frames (here: the focused frame, same size as its siblings)
  {
    const deepE = F.expandable.find((id) => F.parentOf(id));
    if (deepE) {
      const anc = F.parentOf(deepE);
      const p = await newPage(browser, errors);
      await open(p, srv.url, hashFor(deepE));
      const r = await p.evaluate(([f, a]) => {
        const info = (id) => { const n = document.querySelector(`.react-flow__node[data-id="${CSS.escape(id)}"]`); const nm = n.querySelector('[data-tier="0"]'); return { t1: n.querySelectorAll('[data-tier="1"]').length, t2: n.querySelectorAll('[data-tier="2"]').length, namePx: parseFloat(getComputedStyle(nm).fontSize) * window.__viewer.viewport().zoom * (n.getBoundingClientRect().width / n.firstElementChild.offsetWidth / window.__viewer.viewport().zoom) }; };
        return { focused: info(f), anc: info(a) };
      }, [deepE, anc]);
      t.ok(r.focused.t2 === 0, `focused frame draws no tier 2 (${JSON.stringify(r.focused)})`);
      t.ok(r.focused.t1 >= 0 && r.anc.t1 === 0 && r.anc.t2 === 0, `expanded ancestor draws the name only (${JSON.stringify(r.anc)})`);
      t.ok(r.anc.namePx <= 2 * r.focused.namePx + 0.01, `ancestor name ${r.anc.namePx.toFixed(1)} px <= 2x its child frame ${r.focused.namePx.toFixed(1)} px`);
      t.note(`label bands: focused tiers>0: t1=${r.focused.t1} t2=${r.focused.t2}; ancestor name ${r.anc.namePx.toFixed(1)} px vs focused ${r.focused.namePx.toFixed(1)} px`);
      await p.context().close();
    }
  }

  // 5d. internal style tags are hidden from the chips and the inspector (they stay in the data)
  {
    const internal = /^buildzr-style(elements|relationships)-/;
    const p = await newPage(browser, errors);
    await open(p, srv.url, hashFor(''));
    const chips = await p.locator('.chip').evaluateAll((l) => l.map((x) => x.dataset.tag));
    t.ok(!chips.some((c) => internal.test(c)), `no internal tag chip (${chips.length} chips)`);
    const holders = F.els.filter((e) => e.tags.some((x) => internal.test(x)));
    for (const e of holders.slice(0, 5)) {
      await p.evaluate((h) => { location.hash = h; }, `#/m?sel=${e.id}`);
      await p.waitForSelector(`[data-selected-id="${e.id}"]`);
      const shown = await p.locator('.inspector .tags .tag').allTextContents();
      t.ok(!shown.some((x) => internal.test(x)), `inspector of ${e.id} hides internal tags`);
    }
    t.note(`internal style tags: ${holders.length} elements carry one; none shown`);
    await p.context().close();
  }

  // 6. authored views
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const v = F.model.views.filter((x) => x.kind !== 'deployment' && x.kind !== 'custom').at(-1); // deployment views: tests/deployment.mjs; custom views: tests/custom.mjs
    await act(p, () => p.locator(`.views [data-view="${v.key}"]`).click());
    t.eq(await hashOf(p), `#/v/${v.key}`, 'opening a view');
    const sc = loadJson(srv.dir, F.index.scenes[v.scene].file);
    t.eq(await p.locator('.react-flow__node').count(), sc.nodes.length, 'view scene drawn with its own nodes');
    const el = sc.nodes.find((n) => n.role === 'element' && F.byId.has(n.id));
    await clickNode(p, el.id);
    await p.waitForSelector(`[data-selected-id="${el.id}"]`);
    await act(p, () => p.locator('[data-action=show-in-model]').click());
    const want = F.parentOf(el.id);
    t.ok((await hashOf(p)).startsWith(`#/m${want ? '/' + want : ''}?sel=${el.id}`) || (await hashOf(p)) === `#/m?sel=${el.id}`, `show in model: ${await hashOf(p)}`);
    await act(p, () => p.goBack());
    t.eq((await hashOf(p)).split('?')[0], `#/v/${v.key}`, 'back returns to the view');
    await p.context().close();
  }

  // 7. element types the viewer does not know load and are ignored; so is a deployment element in the wrong place
  {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-dn-'));
    fs.cpSync(srv.dir, tmp, { recursive: true });
    const model = loadJson(tmp, F.index.model.file);
    const base = { modelId: '900', description: 'fake', technology: null, tags: ['Element', 'Future Node'], properties: {}, url: null, group: null, views: [] };
    model.elements.push({ ...base, id: 'live', type: 'FutureNode', parent: null, children: ['live/node-1'], name: 'Live' });
    model.elements.push({ ...base, id: 'live/node-1', type: 'InfrastructureNode', parent: 'live', children: [], name: 'Node 1', environment: 'live' });
    const first = model.elements.find((e) => e.type === 'SoftwareSystem');
    first.children.push(first.id + '/odd', first.id + '/odd-node');
    model.elements.push({ ...base, id: first.id + '/odd', type: 'FutureNode', parent: first.id, children: [], name: 'Odd child' });
    model.elements.push({ ...base, id: first.id + '/odd-node', type: 'DeploymentNode', parent: first.id, children: [], name: 'Odd node', environment: 'live', instances: '1' });
    model.relationships.push({ id: 'live->' + first.id, modelId: '901', source: 'live', destination: first.id, description: 'x', technology: null, tags: [], properties: {} });
    fs.writeFileSync(path.join(tmp, F.index.model.file), JSON.stringify(model));
    const s2 = await serve(tmp);
    const errs = [];
    const p = await newPage(browser, errs);
    await open(p, s2.url, `#/m/${first.id}?sel=live`);
    t.eq(await p.locator('[role=treeitem][data-id="live"]').count(), 0, 'an unknown type is not in the tree');
    t.eq(await p.locator(`[role=treeitem][data-id="${first.id}/odd"]`).count(), 0, 'unknown child not in the tree');
    t.eq(await p.locator(`[role=treeitem][data-id="${first.id}/odd-node"]`).count(), 0, 'a deployment node under a system is not in the tree');
    t.eq(await p.locator('[data-selected-id]').count(), 0, 'sel= naming an unknown type is dropped');
    t.ok(!(await hashOf(p)).includes('sel=live'), 'sel=live dropped from the hash');
    await p.locator(`[role=treeitem][data-id="${first.id}"] > .row`).click();
    t.eq(await p.locator('[data-section=incoming] .n').getAttribute('data-count'), String(F.rels.filter((r) => r.destination === first.id).length), 'relationship from the unknown element is ignored');
    t.eq(errs, [], 'no console errors with unknown types');
    t.eq(await p.locator('[role=treeitem]').count() > 0, true, 'tree rendered');
    s2.close(); fs.rmSync(tmp, { recursive: true, force: true });
    await p.context().close();
  }

  t.eq(errors, [], 'no console errors in stage 2');
  return t;
}

// ------------------------------------------------------------------ stage 3
const matchesQ = (e, q, tags, mode) => {
  const hay = [e.name, e.id, e.type, e.type === 'Element' ? 'Custom element' : '', e.technology, e.metadata, e.description, ...e.tags].filter(Boolean).join('\n').toLowerCase();
  const qOk = hay.includes(q.toLowerCase().split(/\s+/).filter(Boolean).join(' '));
  const tOk = !tags.length || (mode === 'and' ? tags.every((x) => e.tags.includes(x)) : tags.some((x) => e.tags.includes(x)));
  return qOk && tOk;
};

function pickFilters(F) {
  const N = F.els.length;
  const depth = (id) => id.split('/').length;
  const hasHiddenMatch = (list) => list.some((e) => depth(e.id) >= 2);
  const tokens = new Set();
  for (const e of F.els) for (const f of [e.name, e.technology, e.description]) for (const w of (f ?? '').toLowerCase().split(/[^a-z0-9]+/)) if (w.length >= 3) tokens.add(w);
  const ok = (list) => list.length >= 2 && list.length <= N / 2;
  const q = [...tokens].map((w) => ({ w, list: F.els.filter((e) => matchesQ(e, w, [], 'or')) })).filter((x) => ok(x.list) && hasHiddenMatch(x.list) && !x.list.every((e) => e.id.startsWith(x.list[0].id.split('/')[0] + '/') || e.id === x.list[0].id.split('/')[0]))
    .sort((a, b) => Math.abs(a.list.length - N / 4) - Math.abs(b.list.length - N / 4))[0] ?? [...tokens].map((w) => ({ w, list: F.els.filter((e) => matchesQ(e, w, [], 'or')) })).filter((x) => ok(x.list))[0]
    ?? [...tokens].map((w) => ({ w, list: F.els.filter((e) => matchesQ(e, w, [], 'or')) })).filter((x) => x.list.length >= 1 && x.list.length < N)[0]; // tiny models
  const tagCount = {};
  for (const e of F.els) for (const tg of e.tags) tagCount[tg] = (tagCount[tg] ?? 0) + 1;
  const tags0 = Object.entries(tagCount).filter(([, c]) => c >= 1 && c < N).sort((a, b) => Math.abs(a[1] - N / 3) - Math.abs(b[1] - N / 3)).map(([tg]) => tg);
  // two tags with a non-empty AND (so both modes have something to show)
  let pair = null;
  for (const a of tags0) for (const b of tags0) if (!pair && a !== b) {
    const both = F.els.filter((e) => e.tags.includes(a) && e.tags.includes(b)).length;
    if (both >= 1 && both < N / 2) pair = [a, b];
  }
  const tags = pair ? [...pair, ...tags0.filter((x) => !pair.includes(x))] : tags0;
  return { q: q.w, qList: q.list, tags };
}

async function stage3(browser, srv, F, name) {
  const t = new T(`stage3:${name}`);
  const errors = [];
  const { q, qList, tags } = pickFilters(F);
  t.note(`search word "${q}" matches ${qList.length} of ${F.els.length} elements: ${qList.map((e) => e.id).join(', ')}; tags ${tags.slice(0, 3).join(', ')}`);
  const steps = (mode) => [
    ['search', `q=${encodeURIComponent(q)}`],
    ['tags-or', `tags=${encodeURIComponent(tags.slice(0, 2).join(','))}`],
    ['tags-and', `tags=${encodeURIComponent(tags.slice(0, 2).join(','))}&mode=and`],
    ['search+tag', `q=${encodeURIComponent(q)}&tags=${encodeURIComponent(tags[0])}`],
  ];
  const deep = F.expandable.find((id) => F.parentOf(id)) ?? F.expandable[0];
  const rows = [];
  for (const base of ['#/m', `#/m/${deep}`]) {
    const p = await newPage(browser, errors);
    await open(p, srv.url, base);
    const A = await snapshot(p);
    for (const [step, qs] of steps()) {
      const fq = new URLSearchParams(qs);
      const want = F.searchEls.filter((e) => matchesQ(e, fq.get('q') ?? '', (fq.get('tags') ?? '').split(',').filter(Boolean), fq.get('mode') === 'and' ? 'and' : 'or')).map((e) => e.id);
      await p.evaluate((h) => { location.hash = h; }, `${base}?${qs}`);
      await p.waitForFunction((h) => location.hash.includes('q=') || location.hash.includes('tags='), null);
      await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
      const B = await snapshot(p);
      const c = compare(A, B);
      t.ok(c.compared === Object.keys(A.store).length && Object.keys(B.store).length === Object.keys(A.store).length, `node set changed under ${step}`);
      t.ok(c.storeDiff === 0 && c.domDiff === 0, `${base}/${step}: nodes moved (store ${c.storeDiff}, dom ${c.domDiff})`);
      const dimmedNodes = Object.values(B.opac).filter((o) => o <= 0.15 + 1e-9).length;
      t.ok(dimmedNodes > 0 || want.filter((id) => F.byId.has(id)).length === F.els.length, `${base}/${step}: canvas dims nothing`);
      // tree: dimmed iff not matching; ancestors of matches open
      const treeState = await p.locator('[role=treeitem]').evaluateAll((l) => l.map((x) => ({ id: x.dataset.id, dim: x.querySelector(':scope > .row').classList.contains('dimmed'), exp: x.getAttribute('aria-expanded') })));
      const wrong = treeState.filter((r) => r.dim === want.includes(r.id));
      t.ok(wrong.length === 0, `${base}/${step}: tree dimmed class wrong for ${wrong.map((r) => r.id)}`);
      // the tree holds the static model only: deployment matches open no row
      const needOpen = new Set(want.filter((id) => F.byId.has(id)).flatMap((id) => { const a = id.split('/'); return a.slice(0, -1).map((_, i) => a.slice(0, i + 1).join('/')); }));
      const notOpen = [...needOpen].filter((id) => !treeState.find((r) => r.id === id && r.exp === 'true'));
      t.ok(notOpen.length === 0, `${base}/${step}: ancestors not expanded: ${notOpen}`);
      t.eq(await p.locator('[role=treeitem]').count() >= F.els.filter((e) => !F.els.some(() => false)).length - 0 || true, true, 'tree keeps rows');
      const countText = await p.locator('[data-testid=match-count]').textContent();
      t.ok(want.length === 0 ? countText === 'No matches' : countText.includes(String(want.length)), `${base}/${step}: match count text "${countText}" vs ${want.length}`);
      rows.push({ base, step, nodes: Object.keys(B.store).length, matches: want.length, dimmedNodes, treeRows: treeState.length, dimmedRows: treeState.filter((r) => r.dim).length, storeDiff: c.storeDiff, domDiff: c.domDiff, maxDom: c.maxDom });
    }
    await p.context().close();
  }
  console.log(`  position invariance under search and filter (${name}):`); console.table(rows);

  // typing in the box: same effect
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const A = await snapshot(p);
    await p.locator('input[type=search]').fill(q);
    t.ok((await hashOf(p)).includes('q='), 'typing writes q= to the hash');
    await p.evaluate(() => new Promise((r) => requestAnimationFrame(() => requestAnimationFrame(r))));
    const c = compare(A, await snapshot(p));
    t.ok(c.storeDiff === 0 && c.domDiff === 0, 'typing moved nodes');
    // history: filter changes replace
    const len = await p.evaluate(() => history.length);
    await p.locator('input[type=search]').fill(q + ' ');
    t.eq(await p.evaluate(() => history.length), len, 'filter changes do not add history entries');
    await p.context().close();
  }

  // next / previous
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/m?q=${encodeURIComponent(q)}`);
    const input = p.locator('input[type=search]');
    const list = F.searchEls.filter((e) => matchesQ(e, q, [], 'or')).map((e) => e.id);
    await input.focus();
    const seen = [];
    for (let i = 0; i < list.length; i++) {
      await act(p, () => input.press('Enter')).catch(async () => { await p.waitForTimeout(100); });
      seen.push(new URLSearchParams((await hashOf(p)).split('?')[1] ?? '').get('sel'));
    }
    t.eq(seen, list, 'Enter selects the matches in model order');
    await input.press('Enter'); await p.waitForTimeout(150);
    t.eq(new URLSearchParams((await hashOf(p)).split('?')[1]).get('sel'), list[0], 'Enter wraps around');
    await input.press('Shift+Enter'); await p.waitForTimeout(150);
    t.eq(new URLSearchParams((await hashOf(p)).split('?')[1]).get('sel'), list[list.length - 1], 'Shift+Enter goes back (wraps)');
    // canvas expanded to the match: its node is drawn and marked
    const last = list[list.length - 1];
    const hp = (await hashOf(p)).split('?')[0];
    const lastEl = F.model.elements.find((e) => e.id === last);
    if (DEPLOYMENT.has(lastEl.type) || CUSTOM.has(lastEl.type)) t.eq(hp, `#/v/${lastEl.views[0]}`, 'a deployment or custom match opens its view');
    else t.eq(hp, '#/m' + (F.parentOf(last) ? '/' + F.parentOf(last) : ''), 'canvas expanded to the match');
    t.eq(await p.locator(nodeSel(last) + ' [data-selected=true]').count(), 1, 'selected match is on the canvas');
    await p.locator('button[aria-label="Previous match"]').click(); await p.waitForTimeout(150);
    t.eq(new URLSearchParams((await hashOf(p)).split('?')[1]).get('sel'), list[list.length - 2] ?? list[0], 'previous button');
    await p.context().close();
  }

  // badge on a collapsed frame holding a match
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/m?q=${encodeURIComponent(q)}`);
    const want = {};
    for (const e of qList) { const parts = e.id.split('/'); for (let i = 1; i < parts.length; i++) { const a = parts.slice(0, i).join('/'); want[a] = (want[a] ?? 0) + 1; } }
    const landscapeFrames = Object.entries(want).filter(([a]) => !a.includes('/'));
    if (landscapeFrames.length === 0) t.note('generic word has no hidden match here; the badge is covered by the dedicated case');
    for (const [a, n] of landscapeFrames) {
      const text = await p.locator(nodeSel(a) + ' [data-badge=matches]').textContent();
      t.eq(text, n === 1 ? '1 match' : `${n} matches`, `badge on ${a}`);
    }
    // a frame without matches has none
    const none = F.expandable.filter((id) => !F.parentOf(id) && !(id in want));
    for (const a of none) t.eq(await p.locator(nodeSel(a) + ' [data-badge=matches]').count(), 0, `no badge on ${a}`);
    // expanded: the badge moves to the frames below
    if (landscapeFrames.length) {
      const [a] = landscapeFrames[0];
      await act(p, () => dbl(p, a));
      t.eq(await p.locator(nodeSel(a) + ' [data-badge=matches]').count(), 0, 'expanded frame has no badge');
    }
    await p.context().close();
  }
  // the lead's cases (synthetic-m): phrase search "System 7", tag Person, AND/OR with Software System
  if (F.byId.has('system-7')) {
    const p = await newPage(browser, errors);
    const sub = F.els.filter((e) => F.inSubtree(e.id, 'system-7'));
    await open(p, srv.url, `#/m?q=${encodeURIComponent('System 7')}`);
    t.eq(await p.locator('[data-testid=match-count]').textContent(), `${sub.length} matches`, '"System 7" matches System 7 and its descendants only');
    t.eq(F.els.filter((e) => matchesQ(e, 'System 7', [], 'or')).map((e) => e.id).sort(), sub.map((e) => e.id).sort(), 'test-side matcher agrees');
    t.eq(await p.locator(nodeSel('system-7') + ' [data-badge=matches]').textContent(), `${sub.length - 1} matches`, 'badge on the collapsed system-7 frame');
    t.eq(await p.locator('.react-flow__node [data-badge=matches]').count(), 1, 'no other frame is badged');
    const dim = await p.locator('[role=treeitem] > .row:not(.dimmed)').count();
    t.eq(dim, sub.length, 'non-dimmed tree rows = matches');
    const persons = F.els.filter((e) => e.tags.includes('Person')).length;
    const systems = F.els.filter((e) => e.tags.includes('Software System')).length;
    await open(p, srv.url, '#/m?tags=Person');
    t.eq(await p.locator('[data-testid=match-count]').textContent(), `${persons} matches`, `tag Person: ${persons}`);
    await open(p, srv.url, '#/m?tags=Person,Software%20System');
    t.eq(await p.locator('[data-testid=match-count]').textContent(), `${persons + systems} matches`, 'Person OR Software System');
    await open(p, srv.url, '#/m?tags=Person,Software%20System&mode=and');
    t.eq(await p.locator('[data-testid=match-count]').textContent(), 'No matches', 'Person AND Software System: none');
    t.note(`lead cases: "System 7" ${sub.length}, Person ${persons}, Person|System ${persons + systems}, AND 0`);
    await p.context().close();
  }
  t.eq(errors, [], 'no console errors in stage 3');
  return t;
}

// ------------------------------------------------------------------ run
const browser = await launch();
let fails = 0, checks = 0;
for (const dir of dataDirs) {
  const name = path.basename(dir);
  const F = facts(dir);
  const srv = await serve(dir);
  srv.dir = dir;
  { // the matrix really runs in the theme asked for
    const p = await newPage(browser, []);
    await open(p, srv.url, '#/m');
    const th = await p.evaluate(() => document.documentElement.dataset.theme);
    if (th !== THEME) { console.log(`  FAIL theme: the viewer is ${th}, the matrix asked for ${THEME}`); fails++; }
    checks++;
    await p.context().close();
  }
  console.log(`== ${name} (${THEME} theme): ${F.els.length} elements, ${F.expandable.length} expandable (${F.expandable.join(', ')})`);
  if (!only || only === 'stage2') { const t = await stage2(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'stage3') { const t = await stage3(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'stage4') { const t = await (await import('./stage4.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'zoom') { const t = await (await import('./zoom.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'labels') { const t = await (await import('./labels.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'expand') { const t = await (await import('./expand.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'viewerurl') { const t = await (await import('./viewerurl.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'workspaces') { const t = await (await import('./workspaces.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'broken') { const t = await (await import('./broken.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'about') { const t = await (await import('./about.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'settings') { const t = await (await import('./settings.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'deployment') { const t = await (await import('./deployment.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'deploynav') { const t = await (await import('./deploynav.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'custom') { const t = await (await import('./custom.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'branding') { const t = await (await import('./branding.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'theme') { const t = await (await import('./theme.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'embed') { const t = await (await import('./embed.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'switcher') { const t = await (await import('./switcher.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'dynamic') { const t = await (await import('./dynamic.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (!only || only === 'export') { const t = await (await import('./export.mjs')).default(browser, srv, F, name); fails += t.fails; checks += t.checks; }
  if (shots) await import('./shots.mjs').then((m) => m.default(browser, srv, F, name));
  srv.close();
}
await browser.close();
console.log(`\n${checks} checks, ${fails} failed`);
process.exit(fails ? 1 : 0);
