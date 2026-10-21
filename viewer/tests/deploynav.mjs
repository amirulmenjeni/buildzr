// From a software system or container to the deployment instances that run it: zero, one or several, the existing
// navigation, the keyboard, a phone, an embedded frame and no network. Data sets without deployment environments only
// check that nothing new shows. Run: node tests/run.mjs --only deploynav --data <dir>
import { createRequire } from 'node:module';
import { newPage, open, act, hashOf, mouseClick, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const DEPLOYABLE = new Set(['SoftwareSystem', 'Container']);
const section = '[data-section=deployments]';
const parentOf = (e) => e.parent ?? '';

async function seriousAxe(p) {
  await p.addScriptTag({ path: AXE });
  return p.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((v) => `${v.id}[${v.impact}]: ${v.nodes[0].target.join(' ')}`));
}

export default async function deploynav(browser, srv, F, name) {
  const t = new T(`deploynav:${name}`);
  const errors = [];
  const requests = [];
  const byId = new Map(F.model.elements.map((e) => [e.id, e]));
  const envs = F.model.deployment.environments;
  const deployable = F.model.elements.filter((e) => DEPLOYABLE.has(e.type));
  const instancesOf = (id) => F.model.elements.filter((e) => e.instanceOf === id);
  const shownIn = (inst) => inst.views.some((k) => F.model.views.some((v) => v.key === k));

  const p = await newPage(browser, errors);
  p.on('request', (r) => requests.push(r.url()));
  const select = (id) => open(p, srv.url, `#/m/${parentOf(byId.get(id))}?sel=${id}`);

  // ---- 1. every deployable element: the section is there exactly when the model has environments, with the model's count
  for (const e of deployable) {
    await select(e.id);
    const n = instancesOf(e.id).length;
    if (envs.length === 0) {
      t.eq(await p.locator(`${section}, [data-action=show-deployment]`).count(), 0, `${e.id}: no deployment environments, nothing new in the inspector`);
      continue;
    }
    t.eq(await p.locator(`${section} h3 [data-count]`).getAttribute('data-count'), String(n), `${e.id}: ${n} deployments listed`);
    t.eq(await p.locator(`${section} li[data-instance]`).evaluateAll((li) => li.map((x) => x.dataset.instance)).then((a) => a.sort()),
      instancesOf(e.id).map((i) => i.id).sort(), `${e.id}: the instances are the model's`);
    t.eq(await p.locator(`${section} [data-empty=deployments]`).count(), n === 0 ? 1 : 0, `${e.id}: the "not deployed" note only without instances`);
  }
  // a person, a component and a deployment element have no such section
  for (const e of F.model.elements.filter((x) => !DEPLOYABLE.has(x.type) && x.type !== 'DeploymentNode' && x.type !== 'InfrastructureNode' && !x.instanceOf).slice(0, 3)) {
    await select(e.id);
    t.eq(await p.locator(section).count(), 0, `${e.id} (${e.type}): no deployments section`);
  }
  if (envs.length === 0) { t.eq(errors, [], 'no console errors'); await p.context().close(); return t; }

  // the fixture: zero, one and several; the expectations are written out, the loop above checks them against the model
  const zero = deployable.find((e) => instancesOf(e.id).length === 0);
  const one = deployable.find((e) => instancesOf(e.id).length === 1 && shownIn(instancesOf(e.id)[0]));
  const many = deployable.find((e) => instancesOf(e.id).filter(shownIn).length > 1);
  const hidden = deployable.find((e) => instancesOf(e.id).length > 0 && instancesOf(e.id).every((i) => !shownIn(i)));

  // ---- 2. zero: a plain note, no button, nothing that looks like a link
  if (zero) {
    await select(zero.id);
    t.eq(await p.locator(`${section} [data-empty=deployments]`).textContent(), 'Not deployed in any environment.', 'zero: the note says so');
    t.eq(await p.locator(`${section} button`).count(), 0, 'zero: no buttons in the section');
    t.eq(await p.locator('[data-action=show-deployment]').count(), 0, 'zero: no "Show deployment" action');
  } else t.note('no element that runs nowhere');

  // ---- 3. one: "Show deployment" opens the deployment view with the instance selected; Back returns; Instance of returns too
  if (one) {
    const inst = instancesOf(one.id)[0];
    const view = inst.views.find((k) => F.model.views.some((v) => v.key === k));
    await select(one.id);
    const before = await hashOf(p);
    t.eq(await p.locator('[data-action=show-deployment]').textContent(), 'Show deployment', 'one: the action is "Show deployment"');
    await act(p, () => p.locator('[data-action=show-deployment]').click());
    t.eq(await hashOf(p), `#/v/${view}?sel=${inst.id}`, 'one: the deployment view opens with the instance selected');
    t.eq(await p.locator(`[data-selected-id="${inst.id}"] [data-field=instance-of]`).textContent(), one.name, 'one: the inspector names what it is an instance of');
    t.eq(await p.evaluate(() => document.activeElement?.matches('.inspector h2')), true, 'one: focus moved to the inspector heading');
    t.ok((await p.locator('[data-testid=live]').textContent()).startsWith(`Showing ${inst.name} in `), 'one: the change is announced');
    await p.goBack();
    await p.waitForFunction((h) => location.hash === h, before);
    t.eq(await hashOf(p), before, 'one: Back returns to the container');
    t.eq(await p.locator(`[data-selected-id="${one.id}"]`).count(), 1, 'one: the container is selected again');
    await p.goForward();
    await p.waitForFunction((h) => location.hash.startsWith('#/v/'), null);
    t.eq(await p.locator(`[data-selected-id="${inst.id}"]`).count(), 1, 'one: Forward shows the instance again');
    await act(p, () => p.locator('[data-field=instance-of] button').click());
    t.eq(await p.locator(`[data-selected-id="${one.id}"]`).count(), 1, 'one: "Instance of" leads back to the container');
    t.eq(await p.locator(`${section} li[data-instance="${inst.id}"] button`).count(), 1, 'one: and the container lists the instance again');
  } else t.note('no element with exactly one shown instance');

  // ---- 4. several: grouped by environment, labelled by the nodes; the action goes to the list; a row opens its view
  if (many) {
    const list = instancesOf(many.id).filter(shownIn);
    await select(many.id);
    t.eq(await p.locator('[data-action=show-deployment]').textContent(), `Deployments (${list.length})`, 'several: the action counts them');
    await p.locator('[data-action=show-deployment]').click();
    t.eq(await p.evaluate(() => document.activeElement?.closest('[data-section=deployments]') !== null && document.activeElement.tagName), 'H3', 'several: the action moves focus to the list heading');
    const groups = await p.locator(`${section} [data-environment]`).evaluateAll((g) => g.map((x) => [x.dataset.environment, x.querySelector('h4').textContent, x.querySelectorAll('li').length]));
    const want = envs.map((e) => [e.key, e.name, instancesOf(many.id).filter((i) => i.environment === e.key).length]).filter((g) => g[2] > 0);
    t.eq(groups, want, 'several: one group per environment, in environment order');
    const labels = await p.locator(`${section} li[data-instance]`).evaluateAll((li) => li.map((x) => x.textContent.replace(/\s+/g, ' ').trim()));
    const expect = instancesOf(many.id).map((i) => {
      const chain = []; for (let q = i.parent; q; q = byId.get(q).parent) chain.unshift(byId.get(q).name);
      const copies = byId.get(i.parent)?.instances;
      return chain.join(' › ') + (copies && copies !== '1' ? ` ×${copies}` : '');
    });
    t.eq(labels.length, expect.length, 'several: a row per instance');
    t.eq(labels, expect, 'several: the label is the path of nodes, and the copies when more than one');
    const separators = await p.locator(`${section} li[data-instance] button [aria-hidden=true]`).count();
    t.ok(separators >= 1, 'several: the › separators are hidden from assistive technology');

    // the last row (another environment, or another node): opens a view that draws it
    const last = list.at(-1);
    const lastView = last.views.find((k) => F.model.views.some((v) => v.key === k));
    await act(p, () => p.locator(`${section} li[data-instance="${last.id}"] button`).click());
    t.eq(await hashOf(p), `#/v/${lastView}?sel=${last.id}`, 'several: a row opens the view of its instance');
    // the same view again: a second instance of it is selected in place, the history gets no new entry
    await act(p, () => p.locator('[data-field=instance-of] button').click());
    const sameView = list.find((i) => i.id !== last.id && i.views.includes(lastView));
    if (sameView) {
      await act(p, () => p.locator(`${section} li[data-instance="${last.id}"] button`).click());
      const len = await p.evaluate(() => history.length);
      await act(p, () => p.locator('[data-field=instance-of] button').click());
      await act(p, () => p.locator(`${section} li[data-instance="${sameView.id}"] button`).click());
      t.ok((await hashOf(p)).endsWith(`?sel=${sameView.id}`), 'several: each instance is selectable');
      t.ok((await p.evaluate(() => history.length)) <= len + 1, 'several: one entry for the trip to the view');
    }
    // keyboard: Tab onto a row and Enter
    await select(many.id);
    await p.locator(`${section} li[data-instance="${list[0].id}"] button`).focus();
    await act(p, () => p.keyboard.press('Enter'));
    t.eq((await hashOf(p)).endsWith(`?sel=${list[0].id}`), true, 'several: Enter on a focused row opens it');
    t.eq(await p.locator('.react-flow__node[data-selected=true], [data-id="' + list[0].id + '"][data-selected="true"]').count() > 0, true, 'several: and selects it on the canvas');
  } else t.note('no element with several shown instances');

  // ---- 5. an instance no deployment view draws: listed, but not a link, and no action
  if (hidden) {
    await select(hidden.id);
    t.eq(await p.locator(`${section} li[data-instance] button`).count(), 0, 'hidden: no button for an instance no view draws');
    t.ok((await p.locator(`${section} li[data-instance]`).first().textContent()).includes('(in no deployment view)'), 'hidden: the row says why');
    t.eq(await p.locator('[data-action=show-deployment]').count(), 0, 'hidden: no "Show deployment" action');
  } else t.note('no element whose instances no view draws');

  // ---- 6. existing navigation is intact: Show in model, the views list, a link to a container, search
  if (one) {
    await select(one.id);
    t.eq(await p.locator('[data-action=show-in-model]').count(), 0, 'in the model canvas the container has no "Show in model"');
    t.eq(await p.locator('[data-section=views] li').count(), one.views.length, 'the container still lists its views');
    await open(p, srv.url, `#/m/${parentOf(one)}?sel=${one.id}`);
    t.eq(await hashOf(p), `#/m/${parentOf(one)}?sel=${one.id}`, 'a link to the container still opens it');
    const inst = instancesOf(one.id)[0];
    await open(p, srv.url, `#/m/${inst.id}`);
    t.eq((await hashOf(p)).endsWith(`?sel=${inst.id}`), true, '#/m/<instance id> still opens its deployment view');
    await act(p, () => p.locator('[data-action=show-in-model]').click());
    t.eq(await p.locator(`[data-selected-id="${one.id}"] ${section}`).count(), 1, '"Show in model" from the instance lands on the container, with its deployments');
  }

  // ---- 7. accessibility: a labelled region with a heading, no axe violations, a visible focus ring on the rows
  if (many) {
    await select(many.id);
    t.eq(await p.locator(`${section}`).getAttribute('aria-labelledby'), 'deployments-h', 'the section is labelled by its heading');
    t.eq(await seriousAxe(p), [], 'axe: no violations with the deployments listed');
    await p.keyboard.press('Shift'); // keyboard modality: focus() from a script then shows the focus ring
    await p.locator(`${section} li button`).first().focus();
    const ring = await p.locator(`${section} li button`).first().evaluate((b) => getComputedStyle(b).outlineStyle);
    t.ok(ring !== 'none', 'a focused row has an outline');
  }
  t.ok(requests.every((u) => new URL(u).origin === new URL(srv.url).origin), 'offline: every request goes to the viewer\'s own origin');
  await p.context().close();

  // ---- 8. a phone: the action is in reach of the sheet, 44 px targets, nothing overflows, the sheet shows the instance
  const target = one ?? many;
  if (target) {
    const ph = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true });
    await open(ph, srv.url, `#/m/${parentOf(target)}?sel=${target.id}`);
    t.eq(await ph.locator('[data-sheet]').getAttribute('data-sheet'), 'peek', 'phone: the sheet is open');
    const btn = ph.locator('[data-action=show-deployment]');
    const box = await btn.boundingBox();
    const sheetBox = await ph.locator('.sheet-wrap').boundingBox();
    t.ok(box.height >= 44 && box.width >= 44, `phone: the action is at least 44 px (${box.width}x${box.height})`);
    t.ok(box.y + box.height <= sheetBox.y + sheetBox.height + 1, 'phone: the action is visible in the peeking sheet');
    t.eq(await ph.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, 'phone: no horizontal overflow');
    if (target === many) {
      await btn.tap();
      await ph.locator(`${section} li button`).first().evaluate((b) => b.scrollIntoView());
      const rb = await ph.locator(`${section} li button`).first().boundingBox();
      t.ok(rb.height >= 44, `phone: a row is at least 44 px high (${rb.height})`);
      t.eq(await seriousAxe(ph), [], 'phone: axe has no violations');
      await act(ph, () => ph.locator(`${section} li button`).first().tap());
    } else {
      await act(ph, () => btn.tap());
    }
    t.ok((await hashOf(ph)).startsWith('#/v/'), 'phone: a tap opens the deployment view');
    t.eq(await ph.locator('.react-flow__node').count() > 0, true, 'phone: the view is drawn');
    t.eq(await ph.locator('[data-sheet]').getAttribute('data-sheet'), 'peek', 'phone: the sheet shows the instance');
    t.eq(await ph.locator('[data-selected-id] [data-field=instance-of]').count(), 1, 'phone: and its "Instance of"');
    t.eq(await ph.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth), 0, 'phone: still no horizontal overflow');
    await ph.context().close();
  }

  // ---- 9. embedded (?embed=1&data=server): the same navigation, and the parent's history is never stepped
  if (one) {
    const e = await newPage(browser, errors, { viewport: { width: 900, height: 600 } });
    await e.goto(srv.url + `?embed=1&data=server#/m/${parentOf(one)}`);
    await e.waitForFunction(() => window.__viewer?.ready === true && Object.keys(window.__viewer.positions()).length > 0);
    t.eq(await e.locator('.inspector [data-action=show-deployment]').count(), 0, 'embed: the inspector is closed until a reader selects something');
    await mouseClick(e, one.id);
    const len = await e.evaluate(() => history.length);
    const inst = instancesOf(one.id)[0];
    await act(e, () => e.locator('[data-action=show-deployment]').click());
    t.ok((await hashOf(e)).endsWith(`?sel=${inst.id}`), 'embed: the instance is opened');
    t.eq(await e.evaluate(() => history.length), len, 'embed: no history entry was added');
    t.eq(await e.locator(`[data-selected-id="${inst.id}"]`).count(), 1, 'embed: the inspector shows the instance');
    await e.context().close();
  }

  t.eq(errors, [], 'no console errors');
  return t;
}
