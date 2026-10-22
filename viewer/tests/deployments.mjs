// Unit tests without a browser: the instances that run a software system or container (model.ts). Run: npm run test:unit
import { T } from './lib.mjs';
import { indexModel, deploymentsOf } from '../src/model.ts';

const t = new T('deployments');
const el = (id, type, extra = {}) => ({
  id, modelId: id, type, parent: type === 'DeploymentNode' && id.split('/').length === 3 ? null : id.includes('/') ? id.slice(0, id.lastIndexOf('/')) : null, children: [], name: id.split('/').pop(),
  description: null, technology: null, tags: [], properties: {}, url: null, group: null, views: [], ...extra,
});
const model = (elements, views = []) => ({
  schema: 'buildzr.model/2', modelHash: 'x', workspace: { name: 'w' }, elements, relationships: [], views,
  deployment: { environments: [] },
});
const index = { schema: 'buildzr.index/2', modelHash: 'x', model: { file: 'm', hash: 'x' }, scenes: {} };
const ENV = [{ key: 'prod', name: 'Production' }, { key: 'dev', name: 'Dev' }];
const view = (key) => ({ key, kind: 'deployment', title: key, scope: null, scene: 'v/' + key });

const m = indexModel(model([
  el('s', 'SoftwareSystem'), el('s/a', 'Container'), el('s/b', 'Container'), el('s/c', 'Container'),
  el('deploy/prod/n', 'DeploymentNode', { environment: 'prod', instances: '2' }),
  el('deploy/prod/n/a', 'ContainerInstance', { environment: 'prod', instanceOf: 's/a', views: ['prod'] }),
  el('deploy/prod/m', 'DeploymentNode', { environment: 'prod', instances: '1' }),
  el('deploy/prod/m/a', 'ContainerInstance', { environment: 'prod', instanceOf: 's/a', views: ['prod'] }),
  el('deploy/dev/l', 'DeploymentNode', { environment: 'dev', instances: '1' }),
  el('deploy/dev/l/a', 'ContainerInstance', { environment: 'dev', instanceOf: 's/a' }),
  el('deploy/dev/l/b', 'ContainerInstance', { environment: 'dev', instanceOf: 's/b', views: ['gone'] }),
  el('deploy/dev/l/s', 'SoftwareSystemInstance', { environment: 'dev', instanceOf: 's', views: ['prod'] }),
  // an instance of an unknown element is dropped by the index, like any element the viewer cannot place
  el('deploy/dev/l/x', 'ContainerInstance', { environment: 'dev', instanceOf: 's/missing', views: ['prod'] }),
], [view('prod')]), index);

t.eq([...m.instancesOf.keys()].sort(), ['s', 's/a', 's/b'], 'instancesOf has the elements that run somewhere');
t.eq(m.instancesOf.get('s/a'), ['deploy/prod/n/a', 'deploy/prod/m/a', 'deploy/dev/l/a'], 'instances in model order');
t.eq(m.instancesOf.get('s/c'), undefined, 'a container that runs nowhere has none');

const a = deploymentsOf(m, 's/a', ENV);
t.eq(a.map((g) => [g.environment, g.name, g.rows.map((r) => r.id)]),
  [['prod', 'Production', ['deploy/prod/n/a', 'deploy/prod/m/a']], ['dev', 'Dev', ['deploy/dev/l/a']]], 'grouped by environment, in environment order');
t.eq(a[0].rows.map((r) => [r.nodes, r.copies, r.shown]), [[['n'], '2', true], [['m'], null, true]], 'node path, copies of the node (not for 1), shown');
t.eq(a[1].rows[0].shown, false, 'an instance in no view is not shown');
t.eq(deploymentsOf(m, 's/b', ENV)[0].rows[0].shown, false, 'a view key the model does not list does not count');
t.eq(deploymentsOf(m, 's', ENV).map((g) => g.rows.map((r) => r.id)), [['deploy/dev/l/s']], 'a software system has its own instances');
t.eq(deploymentsOf(m, 's/c', ENV), [], 'zero instances: no group');
t.eq(deploymentsOf(m, 's/a', []).map((g) => g.name), ['prod', 'dev'], 'an environment the list does not name falls back to its key');

// older data: no instanceOf anywhere
const old = indexModel(model([el('s', 'SoftwareSystem'), el('s/a', 'Container')]), index);
t.eq([old.instancesOf.size, deploymentsOf(old, 's/a', [])], [0, []], 'a model without deployment data');

console.log(`deployments: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
