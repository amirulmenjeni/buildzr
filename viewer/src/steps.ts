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

export interface Box { x: number; y: number; w: number; h: number }
export interface Viewport { x: number; y: number; zoom: number }

/** On screen (px): a camera move leaves this much room around the step. */
export const FOLLOW = { pad: 32 };

/** The smallest box around all of these; null for none. */
export function unionBox(boxes: Box[]): Box | null {
  if (!boxes.length) return null;
  const x0 = Math.min(...boxes.map((b) => b.x)), y0 = Math.min(...boxes.map((b) => b.y));
  const x1 = Math.max(...boxes.map((b) => b.x + b.w)), y1 = Math.max(...boxes.map((b) => b.y + b.h));
  return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
}

/**
 * The camera that shows a step: `target` is in flow coordinates, `free` the part of the canvas no overlay covers (canvas px).
 * Null when the target is already in `free` at the camera `vp`: nothing moves. Otherwise the target is centred in `free`
 * at the current zoom, lowered only as far as the target needs to fit with `pad` around it. It never zooms in.
 */
export function follow(target: Box, vp: Viewport, free: Box): Viewport | null {
  const sx = vp.x + target.x * vp.zoom, sy = vp.y + target.y * vp.zoom;
  if (sx >= free.x && sy >= free.y && sx + target.w * vp.zoom <= free.x + free.w && sy + target.h * vp.zoom <= free.y + free.h) return null;
  const room = (n: number): number => Math.max(1, n - 2 * FOLLOW.pad);
  const zoom = Math.max(0.01, Math.min(vp.zoom, room(free.w) / Math.max(target.w, 1e-6), room(free.h) / Math.max(target.h, 1e-6)));
  return { zoom, x: free.x + free.w / 2 - (target.x + target.w / 2) * zoom, y: free.y + free.h / 2 - (target.y + target.h / 2) * zoom };
}
