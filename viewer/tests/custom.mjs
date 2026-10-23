// Custom elements and custom views: drawn from their scenes with the same canvas, in the tree, search, inspector and links;
// standard views and the model canvas stay as they are. Data sets without a custom element skip this.
// Run: node tests/run.mjs --only custom --data tests/site/fixtures/custom
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { act, hashOf, mouseClick, newPage, open, serve, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const node = (id) => `.react-flow__node[data-id="${id}"]`;
const row = (p, id) => p.locator(`[role=treeitem][data-id="${id}"] > .row`);
const loadJson = (dir, f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const lum = (c) => { const v = [1, 3, 5].map((i) => parseInt(c.slice(i, i + 2), 16) / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
const contrast = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };

async function axeRun(p, label, t) {
  await p.addScriptTag({ path: AXE });
  const bad = await p.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ['violations'] });
    return r.violations.filter((v) => v.impact === 'serious' || v.impact === 'critical').map((v) => `${v.id}: ${v.help} (${v.nodes[0].target.join(' ')})`);
  });
  t.eq(bad, [], `axe ${label}: no serious or critical violations`);
}

export default async function custom(browser, srv, F, name) {
  const t = new T(`custom:${name}`);
  const errors = [];
  const customs = F.model.elements.filter((e) => e.type === 'Element');
  const cviews = F.model.views.filter((v) => v.kind === 'custom');
  if (!customs.length || !cviews.length) { t.note('no custom element or custom view: skipped'); return t; }
  const byId = new Map(F.model.elements.map((e) => [e.id, e]));
  const scene = (v) => loadJson(srv.dir, F.index.scenes[v.scene].file);
  const viewOf = (k) => F.model.views.find((v) => v.key === k);
  const inView = (e) => e.views.some((k) => viewOf(k));
  const nodes = (p) => p.evaluate(() => [...document.querySelectorAll('.react-flow__node')].map((n) => n.dataset.id));
  const viewScenes = F.model.views.map((v) => ({ v, sc: scene(v) }));
  const withMeta = customs.find((e) => e.metadata && e.views.some((k) => viewOf(k).kind === 'custom'));
  const noMeta = customs.find((e) => !e.metadata && e.views.some((k) => viewOf(k).kind === 'custom'));
  const orphan = customs.find((e) => e.views.length === 0);
  const device = withMeta;
  const devView = viewOf(device.views.find((k) => viewOf(k).kind === 'custom'));
  const c4 = F.model.elements.filter((e) => ['Person', 'SoftwareSystem', 'Container', 'Component'].includes(e.type));

  // 1. every custom view draws every node and edge of its scene under the model ids; the views list names its kind
  for (const v of cviews) {
    const sc = scene(v);
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    t.eq((await nodes(p)).sort(), sc.nodes.map((n) => n.id).sort(), `${v.key}: every scene node is drawn under its model id`);
    t.eq(await p.locator('.react-flow__edge').count(), sc.edges.length, `${v.key}: every scene edge is drawn`);
    t.eq(await p.locator(`.views button[data-view="${v.key}"] .kind`).textContent(), 'custom', `${v.key}: listed as a custom view`);
    t.eq(await p.locator('.crumbs [data-crumb-view]').textContent(), `View: ${v.title}`, `${v.key}: the breadcrumb names the view`);
    t.ok(sc.nodes.every((n) => byId.get(n.id)?.type === 'Element'), `${v.key}: the scene holds custom elements only`);
    // labels: the metadata in brackets under the name, no type text for an element without metadata
    await p.evaluate(() => window.__viewer.setViewport({ x: 0, y: 0, zoom: 1 }));
    await p.waitForTimeout(50);
    for (const n of sc.nodes) {
      const e = byId.get(n.id);
      const text = (await p.locator(node(n.id)).textContent()) ?? '';
      t.ok(text.includes(e.name), `${v.key}/${n.id}: shows its name`);
      if (e.metadata) t.ok(text.includes(`[${e.metadata}]`), `${v.key}/${n.id}: shows [${e.metadata}]`);
      else t.ok(!/\[[^\]]*\]/.test(text), `${v.key}/${n.id}: no bracket line without metadata (${text})`);
    }
    t.ok(!(await p.locator('.canvas').textContent()).includes('[Element]'), `${v.key}: no "[Element]" type text`);
    await p.context().close();
  }

  // 2. the model canvas stays the C4 model: custom elements are not drawn there, in any state
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const land = loadJson(srv.dir, F.index.scenes.landscape.file).nodes.map((n) => n.id).sort();
    t.eq((await nodes(p)).sort(), land, 'the landscape draws its C4 nodes only');
    t.ok(!land.some((id) => byId.get(id).type === 'Element'), 'the landscape scene has no custom element');
    for (const e of F.expandable) {
      await open(p, srv.url, `#/m/${e}`);
      t.ok(!(await nodes(p)).some((id) => byId.get(id)?.type === 'Element'), `${e}: expanded, still no custom element on the model canvas`);
    }
    await p.context().close();
  }

  // 3. the tree: custom elements follow the C4 roots, one level, no twisty, labelled "Custom element"
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const rows = await p.locator('[role=treeitem][aria-level="1"]').evaluateAll((l) => l.map((x) => ({ id: x.dataset.id, kind: x.querySelector('.kind').textContent, exp: x.getAttribute('aria-expanded') })));
    const c4roots = c4.filter((e) => !e.parent).map((e) => e.id);
    t.eq(rows.map((r) => r.id), [...c4roots, ...customs.map((e) => e.id)], 'tree roots: the C4 elements, then the custom elements in model order');
    t.ok(rows.filter((r) => byId.get(r.id).type === 'Element').every((r) => r.kind === 'Custom element' && r.exp === null), 'custom rows: "Custom element", never expandable');
    t.eq(await p.locator('[role=treeitem]').evaluateAll((l) => l.filter((x) => x.dataset.id.startsWith('deploy/')).length), 0, 'no deployment row');
    // keyboard: End reaches the last custom element; Enter on it opens a view that draws it (or selects it when no view does)
    await p.locator('[role=treeitem][tabindex="0"]').focus();
    await p.keyboard.press('End');
    await p.waitForTimeout(80);
    t.eq(await p.evaluate(() => document.activeElement.dataset.id), customs.at(-1).id, 'End reaches the last custom element');
    await p.keyboard.press('ArrowUp');
    await p.waitForTimeout(80);
    t.eq(await p.evaluate(() => document.activeElement.dataset.id), customs.at(-2).id, 'ArrowUp walks back through the custom elements');
    await p.context().close();
  }

  // 4. tree navigation: a click opens the first view that draws the element, or stays in the view that does
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, '#/m');
    const first = device.views.find((k) => viewOf(k));
    await act(p, () => row(p, device.id).click());
    t.eq(await hashOf(p), `#/v/${first}?sel=${device.id}`, 'a click on a custom row opens its first view and selects it');
    t.eq(await p.locator(`${node(device.id)} [data-selected="true"]`).count(), 1, 'the element is selected on the canvas');
    await open(p, srv.url, `#/v/${devView.key}?sel=${device.id}`);
    const other = customs.find((e) => e.id !== device.id && e.views.includes(devView.key));
    await row(p, other.id).click();
    await p.waitForTimeout(80);
    t.eq(await hashOf(p), `#/v/${devView.key}?sel=${other.id}`, 'a click on a row of the same view stays in that view');
    // the element the view does not draw: a click in the tree leaves the view
    const away = customs.find((e) => !e.views.includes(devView.key) && e.views.length > 0);
    if (away) {
      await act(p, () => row(p, away.id).click());
      t.ok((await hashOf(p)).startsWith(`#/v/${away.views[0]}`), `${away.id} is not in ${devView.key}: its own view opens`);
    }
    if (orphan) {
      await open(p, srv.url, '#/m');
      await row(p, orphan.id).click();
      await p.waitForTimeout(80);
      t.eq(await hashOf(p), `#/m?sel=${orphan.id}`, 'an element in no view is selected where you are');
      t.eq(await p.locator(`[data-selected-id="${orphan.id}"] [data-section=views] .n`).getAttribute('data-count'), '0', 'the inspector counts no views');
      t.eq(await p.locator('[data-action=show-in-model]').count(), 0, 'no "Show in model" for a custom element');
    }
    await p.context().close();
  }

  // 5. the inspector: type and metadata, relationships across the C4 boundary both ways, views
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${devView.key}`);
    await mouseClick(p, device.id);
    await p.waitForSelector(`[data-selected-id="${device.id}"]`);
    t.eq(await hashOf(p), `#/v/${devView.key}?sel=${device.id}`, 'a click on a custom node selects it');
    t.eq(await p.locator('[data-field=type]').textContent(), `Custom element · ${device.metadata}`, 'the inspector names the type and the metadata');
    t.eq(await p.locator('.inspector h2').textContent(), device.name, 'the inspector names the element');
    t.eq(await p.locator('[data-action=show-in-model]').count(), 0, 'no "Show in model" for a custom element');
    t.eq(await p.locator('[data-action=open]').count(), 0, 'no "Open" for a custom element');
    const out = F.model.relationships.filter((r) => r.source === device.id), inc = F.model.relationships.filter((r) => r.destination === device.id);
    t.eq(await p.locator('[data-section=outgoing] li').evaluateAll((l) => l.map((x) => x.dataset.rel)), out.map((r) => r.id), 'outgoing relationships');
    t.eq(await p.locator('[data-section=incoming] li').evaluateAll((l) => l.map((x) => x.dataset.rel)), inc.map((r) => r.id), 'incoming relationships');
    t.eq(await p.locator('[data-section=views] li button').evaluateAll((l) => l.map((x) => x.dataset.view)), device.views, 'the views it is in');
    // incoming from a C4 element: the link leaves the custom view for the model, with the C4 element selected
    const fromC4 = inc.find((r) => c4.some((e) => e.id === r.source));
    if (fromC4) {
      await act(p, () => p.locator(`[data-section=incoming] li[data-rel="${fromC4.id}"] button.link`).click());
      const h = await hashOf(p);
      t.ok(h.startsWith('#/m') && h.endsWith(`sel=${fromC4.source}`), `a link to a C4 element opens it in the model (${h})`);
      t.eq(await p.locator(`[data-selected-id="${fromC4.source}"]`).count(), 1, 'the inspector shows the C4 element');
      // and back: its outgoing relationship to the custom element opens a view that draws it
      await act(p, () => p.locator(`[data-section=outgoing] li[data-rel="${fromC4.id}"] button.link`).click());
      t.eq(await hashOf(p), `#/v/${device.views[0]}?sel=${device.id}`, 'a link to a custom element opens its first view');
      t.eq(await p.locator(`${node(device.id)} [data-selected="true"]`).count(), 1, 'the custom node is selected');
    } else t.note('no relationship from a C4 element to a custom element: skipped');
    // an edge of the custom view lists its relationships
    const sc = scene(devView);
    await open(p, srv.url, `#/v/${devView.key}`);
    const e = sc.edges[0];
    await p.locator(`.react-flow__edge[data-id="${devView.scene}::${e.id}"] path.react-flow__edge-interaction`).first().dispatchEvent('click');
    await p.waitForTimeout(50);
    t.eq(await p.locator('[data-selected-edge] [data-rel]').evaluateAll((li) => li.map((x) => x.dataset.rel)), e.rels, 'an edge between custom elements lists its relationships');
    await p.context().close();
  }

  // 6. standard views that list a custom element draw it beside the C4 elements, and draw those as before
  {
    const std = viewScenes.filter(({ v, sc }) => v.kind !== 'custom' && sc.nodes.some((n) => byId.get(n.id)?.type === 'Element'));
    t.ok(std.length > 0, 'a standard view lists a custom element');
    for (const { v, sc } of std) {
      const p = await newPage(browser, errors);
      await open(p, srv.url, `#/v/${v.key}`);
      t.eq((await nodes(p)).sort(), sc.nodes.map((n) => (n.role === 'boundary' ? `${sc.key}|${n.id}` : n.id)).sort(), `${v.key}: C4 and custom nodes are all drawn`);
      const members = F.model.elements.filter((e) => e.views.includes(v.key)).map((e) => e.id).sort();
      t.eq(sc.nodes.map((n) => n.id).sort(), members, `${v.key}: the scene draws the elements the model says the view has`);
      const c = sc.nodes.find((n) => byId.get(n.id)?.type === 'Element');
      await mouseClick(p, c.id);
      await p.waitForSelector(`[data-selected-id="${c.id}"]`);
      t.eq(await hashOf(p), `#/v/${v.key}?sel=${c.id}`, `${v.key}: selecting a custom node stays in the view`);
      const boundary = sc.nodes.find((n) => n.role === 'boundary');
      if (boundary) t.ok(!(c.x >= boundary.x && c.y >= boundary.y && c.x + c.w <= boundary.x + boundary.w && c.y + c.h <= boundary.y + boundary.h), `${v.key}: the custom element is outside the ${boundary.id} boundary`);
      await p.context().close();
    }
  }

  // 7. links: #/m/<custom id> opens its first view; an element in no view says so; sel= restores the selection
  {
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/m/${device.id}`);
    t.eq(await hashOf(p), `#/v/${device.views[0]}?sel=${device.id}`, '#/m/<custom id> opens its first view');
    await open(p, srv.url, `#/v/${devView.key}?sel=${device.id}`);
    t.eq(await p.locator(`${node(device.id)} [data-selected="true"]`).count(), 1, 'a link selects the custom node');
    if (orphan) {
      await p.goto(srv.url + `#/m/${orphan.id}`);
      await p.waitForSelector('[data-testid=notice]');
      t.eq(await p.locator('[data-testid=notice]').textContent(), `${orphan.id} is in no view; showing the landscape ×`, 'an element in no view: a notice');
      t.eq(await hashOf(p), '#/m', 'and the landscape');
    }
    await p.context().close();
  }

  // 8. search and filter find custom elements (name, metadata, "Custom element") and dim the rest of a custom view
  {
    const p = await newPage(browser, errors);
    const word = device.metadata.toLowerCase();
    const want = F.searchEls.filter((e) => [e.name, e.id, e.type, e.metadata, e.technology, e.description, ...e.tags].filter(Boolean).join('\n').toLowerCase().includes(word));
    await open(p, srv.url, `#/v/${devView.key}?q=${encodeURIComponent(word)}`);
    const op = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map((n) => [n.dataset.id, parseFloat(getComputedStyle(n.firstElementChild).opacity)])));
    const drawn = scene(devView).nodes.map((n) => n.id);
    t.ok(drawn.filter((id) => want.some((e) => e.id === id)).every((id) => op[id] === 1), `search "${word}": the matches are drawn at full opacity`);
    t.ok(drawn.filter((id) => !want.some((e) => e.id === id)).every((id) => op[id] < 0.5), `search "${word}": the other nodes are dimmed`);
    t.ok((await p.locator('[data-testid=match-count]').textContent()).includes(String(want.length)), `search "${word}": ${want.length} matches counted`);
    const tree = await p.locator('[role=treeitem]').evaluateAll((l) => l.map((x) => [x.dataset.id, x.querySelector(':scope > .row').classList.contains('dimmed')]));
    t.eq(tree.filter(([, d]) => !d).map(([id]) => id), want.map((e) => e.id), `search "${word}": the tree dims every other row`);
    await open(p, srv.url, `#/m?q=${encodeURIComponent('custom element')}`);
    t.ok((await p.locator('[data-testid=match-count]').textContent()).includes(String(customs.length)), 'search "custom element" finds every custom element');
    await open(p, srv.url, `#/m?tags=${encodeURIComponent(device.tags.at(-1))}`);
    const tagged = F.searchEls.filter((e) => e.tags.includes(device.tags.at(-1))).length;
    t.ok((await p.locator('[data-testid=match-count]').textContent()).includes(String(tagged)), `the tag ${device.tags.at(-1)} finds ${tagged} elements`);
    // Enter walks the matches: a custom match opens its view
    await open(p, srv.url, `#/m?q=${encodeURIComponent(word)}`);
    const input = p.locator('input[type=search]');
    await input.focus();
    const customMatches = want.filter((e) => e.type === 'Element' && inView(e));
    for (let i = 0; i < want.length; i++) await input.press('Enter');
    await p.waitForTimeout(150);
    t.eq(new URLSearchParams((await hashOf(p)).split('?')[1]).get('sel'), want.at(-1).id, 'Enter walks the matches in model order');
    if (customMatches.length) t.ok((await hashOf(p)).startsWith('#/v/'), 'a custom match opens a view');
    await p.context().close();
  }

  // 9. phone: the view fits, a tap opens the inspector sheet, nothing scrolls sideways
  {
    const ph = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await open(ph, srv.url, `#/v/${devView.key}`);
    const sc = scene(devView);
    t.eq((await nodes(ph)).sort(), sc.nodes.map((n) => n.id).sort(), 'phone: the view is drawn');
    await mouseClick(ph, device.id);
    await ph.waitForTimeout(120);
    t.eq(await ph.locator('[data-sheet]').getAttribute('data-sheet'), 'peek', 'phone: a tap opens the inspector sheet');
    t.eq(await ph.locator(`[data-selected-id="${device.id}"] [data-field=type]`).textContent(), `Custom element · ${device.metadata}`, 'phone: the sheet shows the element');
    t.ok(await ph.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth), 'phone: no horizontal scroll');
    await ph.locator('button[aria-label="Open model navigation"]').click();
    await ph.waitForTimeout(250);
    const tall = await ph.locator(`[role=treeitem][data-id="${device.id}"] > .row`).evaluate((r) => r.getBoundingClientRect().height);
    t.ok(tall >= 44, `phone: the custom tree row is a tap target (${tall} px)`);
    await ph.locator('[role=tab]', { hasText: 'Views' }).click();
    t.eq(await ph.locator(`.views button[data-view="${devView.key}"] .kind`).textContent(), 'custom', 'phone: the views list names the custom view');
    await axeRun(ph, 'phone/custom view', t);
    await ph.context().close();
  }

  // 10. embed and offline: the same view in an embedded frame, with no request outside the page's own origin
  {
    const p = await newPage(browser, errors);
    const foreign = [];
    p.on('request', (r) => { if (!r.url().startsWith(srv.url) && !r.url().startsWith('data:') && !r.url().startsWith('blob:')) foreign.push(r.url()); });
    await open(p, srv.url + '?embed=1&data=server', `#/v/${devView.key}`);
    t.eq((await nodes(p)).sort(), scene(devView).nodes.map((n) => n.id).sort(), 'embed: the custom view is drawn');
    t.eq(await p.locator('[data-selected-id]').count(), 0, 'embed: the inspector shows nothing until a click');
    await mouseClick(p, device.id);
    await p.waitForSelector(`[data-selected-id="${device.id}"]`);
    await open(p, srv.url, `#/v/${devView.key}`);
    await axeRun(p, 'desktop/custom view', t);
    t.eq(foreign, [], 'no request outside the origin of the viewer');
    await p.context().close();
  }

  // 11. text contrast of every custom node, in the dark theme too (the canvas keeps the scene's fills)
  for (const scheme of ['light', 'dark']) {
    const p = await newPage(browser, errors, { colorScheme: scheme });
    await open(p, srv.url, `#/v/${devView.key}`);
    t.eq(await p.evaluate(() => document.documentElement.dataset.theme), scheme, `${scheme}: the theme is applied`);
    const low = scene(devView).nodes.filter((n) => contrast(n.style.color, n.style.fill) < 4.5).map((n) => n.id);
    t.eq(low, [], `${scheme}: custom node text reads against its fill (4.5:1)`);
    const painted = await p.evaluate((ids) => ids.map((id) => getComputedStyle(document.querySelector(`.react-flow__node[data-id="${id}"] .fx div[style*="color"]`) ?? document.body).color), scene(devView).nodes.map((n) => n.id));
    t.ok(painted.every((c) => c.startsWith('rgb')), `${scheme}: the labels are painted`);
    await p.context().close();
  }

  // 12. data from before this feature, or a shape the viewer does not understand, loads without errors
  {
    const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-custom-'));
    fs.cpSync(srv.dir, tmp, { recursive: true });
    const model = loadJson(tmp, F.index.model.file);
    for (const e of model.elements) delete e.metadata; // an older build wrote no metadata
    const std = viewScenes.find(({ v, sc }) => v.kind !== 'custom' && sc.nodes.some((n) => byId.get(n.id)?.type === 'Element'));
    if (std) { // ... and drew no custom element in a standard view
      const file = path.join(tmp, F.index.scenes[std.v.scene].file);
      const sc = loadJson(tmp, F.index.scenes[std.v.scene].file);
      const gone = new Set(sc.nodes.filter((n) => byId.get(n.id)?.type === 'Element').map((n) => n.id));
      sc.nodes = sc.nodes.filter((n) => !gone.has(n.id));
      sc.edges = sc.edges.filter((e) => !gone.has(e.source) && !gone.has(e.target));
      fs.writeFileSync(file, JSON.stringify(sc));
    }
    // a custom element under a system, and a system under a custom element, are not understood
    const sys = model.elements.find((e) => e.type === 'SoftwareSystem');
    const base = { modelId: '900', description: null, technology: null, tags: ['Element'], properties: {}, url: null, group: null, views: [], children: [] };
    model.elements.push({ ...base, id: `${sys.id}/odd-custom`, type: 'Element', parent: sys.id, name: 'Odd custom' });
    sys.children.push(`${sys.id}/odd-custom`);
    model.relationships.push({ id: `${sys.id}/odd-custom->${sys.id}`, modelId: '901', source: `${sys.id}/odd-custom`, destination: sys.id, description: 'x', technology: null, tags: [], properties: {} });
    fs.writeFileSync(path.join(tmp, F.index.model.file), JSON.stringify(model));
    const s2 = await serve(tmp);
    const errs = [];
    const p = await newPage(browser, errs);
    await open(p, s2.url, `#/m/${sys.id}`);
    t.eq(await p.locator(`[role=treeitem][data-id="${sys.id}/odd-custom"]`).count(), 0, 'a custom element under a system is not in the tree');
    t.eq(await p.locator('[role=treeitem][aria-level="1"]').count(), c4.filter((e) => !e.parent).length + customs.length, 'the other rows are as before');
    await row(p, sys.id).click();
    t.eq(await p.locator('[data-section=incoming] .n').getAttribute('data-count'), String(F.rels.filter((r) => r.destination === sys.id).length), 'a relationship from the dropped element is ignored');
    await open(p, s2.url, `#/v/${devView.key}?sel=${device.id}`);
    t.eq(await p.locator(`[data-selected-id="${device.id}"] [data-field=type]`).textContent(), 'Custom element', 'without metadata the inspector names the type only');
    if (std) {
      await open(p, s2.url, `#/v/${std.v.key}?sel=${device.id}`);
      t.eq(await p.locator(`[data-selected-id="${device.id}"]`).count(), 1, 'a view that does not draw the selected custom element still shows it in the inspector');
    }
    t.eq(errs, [], 'no console errors with older or odd data');
    await p.context().close();
    s2.close();
    fs.rmSync(tmp, { recursive: true, force: true });
  }

  t.eq(errors, [], 'no console errors');
  return t;
}
