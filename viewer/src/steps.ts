// The steps of a dynamic view: its scene's edges grouped by `order`, in order. Pure functions, no state.
import type { Scene } from './types';

/** One step: the scene edges that share an order (one, or several for a parallel sequence). */
export interface Step { order: string; edges: string[] }

/** Where an edge or node stands at the current step: before it, on it, or after it. */
export type StepState = 'earlier' | 'current' | 'later';

const collator = new Intl.Collator('en', { numeric: true });
/** "2" < "10", "1.2" < "1.10": orders are strings in Structurizr. */
export const compareOrder = (a: string, b: string): number => collator.compare(a, b);

/** The steps of a dynamic view's scene, in order. Edges without an order are not steps (they stay as drawn). */
export function stepsOf(scene: Scene | undefined, kind: string | undefined): Step[] {
  if (!scene || kind !== 'dynamic') return [];
  const by = new Map<string, string[]>();
  for (const e of scene.edges) {
    if (e.order === undefined || e.order === null || e.order === '') continue;
    const list = by.get(e.order);
    if (list) list.push(e.id); else by.set(e.order, [e.id]);
  }
  return [...by.keys()].sort(compareOrder).map((order) => ({ order, edges: by.get(order)! }));
}

export interface StepLook {
  edges: Map<string, StepState>;
  /** Nodes that no step up to the current one reaches: drawn dimmed. */
  later: Set<string>;
}

/** What step `at` (1-based; 0 = the whole diagram) does to the scene: which edges are earlier, current or later, and which nodes come later. */
export function stepLook(scene: Scene, steps: Step[], at: number): StepLook | null {
  if (at < 1 || at > steps.length) return null;
  const edges = new Map<string, StepState>();
  steps.forEach((s, i) => { for (const id of s.edges) edges.set(id, i + 1 < at ? 'earlier' : i + 1 === at ? 'current' : 'later'); });
  const reached = new Set<string>();
  const stepped = new Set<string>();
  for (const e of scene.edges) {
    const st = edges.get(e.id);
    if (!st) continue;
    for (const end of [e.source, e.target]) {
      if (typeof end !== 'string') continue;
      stepped.add(end);
      if (st !== 'later') reached.add(end);
    }
  }
  return { edges, later: new Set([...stepped].filter((id) => !reached.has(id))) };
}

/** The text of a step's edge: its label's first line without the "3: " the build puts in front, else the relationship's description. */
export function stepText(scene: Scene, edgeId: string, relDescription: (relId: string) => string | null): string {
  const e = scene.edges.find((x) => x.id === edgeId);
  if (!e) return '';
  const first = e.label?.lines.find((l) => l.tier === 0)?.text;
  if (first) return e.order && first.startsWith(`${e.order}: `) ? first.slice(e.order.length + 2) : first;
  return e.rels.length ? relDescription(e.rels[0]) ?? '' : '';
}
