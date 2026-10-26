// Unit tests without a browser: the steps of a dynamic view and what a step looks like (steps.ts). Run: npm run test:unit
import { T } from './lib.mjs';
import { compareOrder, stepLook, stepsOf, stepText } from '../src/steps.ts';

const t = new T('steps');
const edge = (id, order, text) => {
  const [source, target] = id.split('#')[0].split('->');
  return { id, source, target, points: [], count: 1, rels: [`${source}->${target}`], style: { stroke: '#000', arrow: 'end' }, order,
    ...(text === undefined ? {} : { label: { lines: [{ text, tier: 0 }], x: 0, y: 0, w: 1, h: 1 } }) };
};
const scene = (edges) => ({ schema: 'buildzr.scene/2', key: 'v/x', level: { kind: 'view', scope: null }, title: 'x', modelHash: 'x', bounds: [0, 0, 1, 1], ports: [], nodes: [], edges });
const ids = (steps) => steps.map((s) => `${s.order}:${s.edges.join('+')}`);

// order: numbers as numbers, nested orders by their parts
t.eq(['10', '2', '1', '1.10', '1.2', '1.1'].sort(compareOrder), ['1', '1.1', '1.2', '1.10', '2', '10'], 'orders sort as numbers, part by part');

// edges come sorted by id in a scene: the steps follow the order, not the id
const sc = scene([edge('a->b#10', '10', '10: ten'), edge('a->b#2', '2', '2: two'), edge('b->c#1', '1', '1: one'), edge('c->d#1', '1', '1: one too'), edge('x->y', undefined), edge('y->z', '', 'none')]);
const steps = stepsOf(sc, 'dynamic');
t.eq(ids(steps), ['1:b->c#1+c->d#1', '2:a->b#2', '10:a->b#10'], 'steps in order; one order shared by two edges is one step; edges without an order are not steps');
t.eq(stepsOf(sc, 'container'), [], 'only dynamic views have steps');
t.eq(stepsOf(undefined, 'dynamic'), [], 'no scene yet: no steps');

// what a step looks like
t.eq(stepLook(sc, steps, 0), null, 'step 0: the whole diagram as drawn');
t.eq(stepLook(sc, steps, 4), null, 'past the last step: the whole diagram');
const l1 = stepLook(sc, steps, 1);
t.eq([...l1.edges].sort(), [['a->b#10', 'later'], ['a->b#2', 'later'], ['b->c#1', 'current'], ['c->d#1', 'current']], 'step 1: both edges of the step are current');
t.eq([...l1.later].sort(), ['a'], 'step 1: a, which only later steps reach, is dimmed');
t.ok(!l1.edges.has('x->y'), 'an edge without an order keeps its look');
const l3 = stepLook(sc, steps, 3);
t.eq([...l3.edges].sort(), [['a->b#10', 'current'], ['a->b#2', 'earlier'], ['b->c#1', 'earlier'], ['c->d#1', 'earlier']], 'last step: the others are earlier');
t.eq([...l3.later], [], 'last step: nothing is dimmed');

// the text of a step
const desc = (r) => (r === 'x->y' ? 'from the model' : null);
t.eq(stepText(sc, 'a->b#2', desc), 'two', 'the label without the "2: " in front');
t.eq(stepText(scene([edge('p->q#3', '3', 'Calls')]), 'p->q#3', desc), 'Calls', 'a label without the number stays as it is');
t.eq(stepText(scene([edge('x->y#1', '1')]), 'x->y#1', desc), 'from the model', 'no label: the relationship description');
t.eq(stepText(sc, 'nope', desc), '', 'an unknown edge has no text');

console.log(`steps: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
