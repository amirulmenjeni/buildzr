// Deployment views: drawn from their scene with the same canvas, selectable, linkable, filtered like any view.
// Data sets without a deployment view skip this. Run: node tests/run.mjs --only deployment --data <dir>
import fs from 'node:fs';
import path from 'node:path';
import { newPage, open, act, hashOf, T } from './lib.mjs';

const DEPLOYMENT = new Set(['DeploymentNode', 'InfrastructureNode', 'ContainerInstance', 'SoftwareSystemInstance']);
const node = (id) => `.react-flow__node[data-id="${id}"]`;

/** Click a box; a deployment node full of children is clicked in its label strip (bottom-left), where nothing covers it. */
async function clickBox(p, id) {
  const pt = await p.evaluate((id) => {
    const el = document.querySelector(`.react-flow__node[data-id="${CSS.escape(id)}"]`);
    const r = el.getBoundingClientRect();
    const pts = [];
    for (const fy of [0.5, 0.985, 0.97, 0.95, 0.9, 0.15, 0.03]) for (const fx of [0.5, 0.02, 0.05, 0.1, 0.2, 0.95]) pts.push([r.x + r.width * fx, r.y + r.height * fy]);
    return pts.find(([x, y]) => { const top = document.elementFromPoint(x, y); return top && top.closest('.react-flow__node') === el; }) ?? null;
  }, id);
  if (!pt) throw new Error(`no free point on node ${id}`);
  await p.mouse.click(pt[0], pt[1]);
}

export default async function deployment(browser, srv, F, name) {
  const t = new T(`deployment:${name}`);
  const errors = [];
  const views = F.model.views.filter((v) => v.kind === 'deployment');
  if (!views.length) { t.note('no deployment view: skipped'); return t; }
  const byId = new Map(F.model.elements.map((e) => [e.id, e]));
  const scene = (v) => JSON.parse(fs.readFileSync(path.join(srv.dir, F.index.scenes[v.scene].file), 'utf8'));

  // 1. every deployment view draws every node of its scene, under its model id; the views list names its kind
  for (const v of views) {
    const sc = scene(v);
    const p = await newPage(browser, errors);
    await open(p, srv.url, `#/v/${v.key}`);
    const drawn = await p.evaluate(() => [...document.querySelectorAll('.react-flow__node')].map((n) => n.dataset.id));
    t.eq(drawn.sort(), sc.nodes.map((n) => n.id).sort(), `${v.key}: every scene node is drawn under its model id`);
    t.eq(await p.locator('.react-flow__edge').count(), sc.edges.length, `${v.key}: every scene edge is drawn`);
    t.eq(await p.locator(`.views button[data-view="${v.key}"] .kind`).textContent(), 'deployment', `${v.key}: listed as a deployment view`);
    t.eq(await p.locator('[role=treeitem]').evaluateAll((rows) => rows.filter((r) => r.dataset.id.startsWith('deploy/')).length), 0,
      `${v.key}: the model tree has no deployment rows`);
    for (const n of sc.nodes.filter((x) => x.instances)) {
      t.eq(await p.locator(`${node(n.id)} [data-badge=instances]`).textContent(), `×${n.instances}`, `${n.id}: instance badge`);
    }
    const deep = Math.max(0, ...sc.nodes.map((n) => { let d = 0; for (let q = n.parent; q; q = sc.nodes.find((x) => x.id === q)?.parent) d++; return d; }));
    t.ok(deep >= 1 || sc.nodes.length <= 1, `${v.key}: nodes nest (depth ${deep})`);
    await p.context().close();
  }

  const v = views.find((x) => scene(x).nodes.some((n) => n.role === 'boundary' && byId.get(n.id)?.type === 'DeploymentNode')) ?? views[0];
  const sc = scene(v);
  const boundary = sc.nodes.find((n) => n.role === 'boundary' && byId.get(n.id)?.type === 'DeploymentNode');
  const inst = sc.nodes.find((n) => byId.get(n.id)?.instanceOf);
  const p = await newPage(browser, errors);
  await open(p, srv.url, `#/v/${v.key}`);

  // 2. a click on a deployment node selects it: hash, inspector with its environment and instance count
  if (boundary) {
    await clickBox(p, boundary.id);
    await p.waitForTimeout(50);
    t.eq(await hashOf(p), `#/v/${v.key}?sel=${boundary.id}`, 'clicking a deployment node selects it');
    t.eq(await p.locator(`[data-selected-id="${boundary.id}"]`).count(), 1, 'the inspector shows the node');
    const env = F.model.deployment.environments.find((e) => e.key === byId.get(boundary.id).environment);
    t.eq(await p.locator('[data-field=environment]').textContent(), env.name, 'the inspector names the environment');
    t.eq(await p.locator('[data-field=instances]').textContent(), byId.get(boundary.id).instances, 'the inspector shows the instance count');
    t.eq(await p.locator('[data-action=show-in-model]').count(), 0, 'a deployment node has no "Show in model"');
  }

  // 3. an instance: "Instance of" and "Show in model" go to its container or system
  if (inst) {
    const of = byId.get(inst.id).instanceOf;
    await clickBox(p, inst.id);
    await p.waitForTimeout(50);
    t.eq(await p.locator(`[data-selected-id="${inst.id}"] [data-field=instance-of]`).textContent(), byId.get(of).name, 'the inspector names what it is an instance of');
    await act(p, () => p.locator('[data-action=show-in-model]').click());
    const h = await hashOf(p);
    t.ok(h.startsWith('#/m') && h.endsWith(`sel=${of}`), `"Show in model" selects ${of} in the model (${h})`);
    t.eq(await p.locator(`[data-selected-id="${of}"]`).count(), 1, 'the inspector shows the container');
  }

  // 4. links: #/v/<key>?sel=<id> restores the selection; #/m/<deployment id> opens its deployment view
  const target = inst ?? boundary ?? sc.nodes[0];
  await open(p, srv.url, `#/v/${v.key}?sel=${target.id}`);
  t.eq(await p.locator(`${node(target.id)} [data-selected="true"]`).count() + await p.locator(`[data-id="${target.id}"][data-selected="true"]`).count() > 0, true, 'a link selects the deployment element on the canvas');
  const first = byId.get(target.id).views[0];
  await open(p, srv.url, `#/m/${target.id}`);
  t.eq(await hashOf(p), `#/v/${first}?sel=${target.id}`, '#/m/<deployment id> opens its first deployment view');

  // 5. search and filter dim and highlight in the deployment view; next match selects inside it
  const q = byId.get(target.id).name;
  await open(p, srv.url, `#/v/${v.key}?q=${encodeURIComponent(q)}`);
  const op = await p.evaluate(() => Object.fromEntries([...document.querySelectorAll('.react-flow__node')].map((n) => [n.dataset.id, parseFloat(getComputedStyle(n.firstElementChild).opacity)])));
  const hits = F.model.elements.filter((e) => DEPLOYMENT.has(e.type) && e.views.includes(v.key) && e.name.toLowerCase().includes(q.toLowerCase())).map((e) => e.id);
  t.ok(hits.length > 0 && hits.every((id) => op[id] === 1), `search "${q}": matches drawn at full opacity`);
  const dim = sc.nodes.filter((n) => !hits.includes(n.id) && !hits.some((h) => h.startsWith(n.id + '/')));
  t.ok(dim.every((n) => op[n.id] < 0.5), `search "${q}": the other nodes are dimmed (${dim.length})`);
  t.ok(hits.every((id) => sc.nodes.filter((n) => id.startsWith(n.id + '/')).every((n) => op[n.id] === 1)), 'the nodes around a match stay lit');

  // 6. an edge click lists the relationships it stands for
  const e = sc.edges[0];
  if (e) {
    await open(p, srv.url, `#/v/${v.key}`);
    await p.locator(`.react-flow__edge[data-id="${v.scene}::${e.id}"] path.react-flow__edge-interaction`).first().dispatchEvent("click");
    await p.waitForTimeout(50);
    t.eq(await p.locator('[data-selected-edge] [data-rel]').evaluateAll((li) => li.map((x) => x.dataset.rel)), e.rels, 'an edge lists its relationships');
  }
  await p.context().close();

  // 7. phone: the view fits, a tap opens the inspector sheet
  const ph = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
  await open(ph, srv.url, `#/v/${v.key}`);
  t.eq(await ph.locator('.react-flow__node').count(), sc.nodes.length, 'phone: the view is drawn');
  const sel = inst ?? boundary;
  if (sel) {
    await clickBox(ph, sel.id);
    await ph.waitForTimeout(100);
    t.eq(await ph.locator('[data-sheet]').getAttribute('data-sheet'), 'peek', 'phone: a tap opens the inspector sheet');
    t.eq(await ph.locator(`[data-selected-id="${sel.id}"]`).count(), 1, 'phone: the sheet shows the element');
  }
  await ph.context().close();

  t.eq(errors, [], 'no console errors');
  return t;
}
