// Compose the scenes of the current path into one React Flow graph (design C, "Renderer and viewer").
// Pure function of (scenes, path, filter results): nothing here ever lays anything out.
import type { Edge, Node } from '@xyflow/react';
import type { MatchInfo, ModelIndex } from './model';
import { chainOf, DEPLOYMENT_TYPES } from './model';
import { stepLook, stepsOf, type StepLook, type StepState } from './steps';
import type { Scene, SceneEdge, SceneNode } from './types';

export const OPACITY = { focus: 1, connected: 0.55, context: 0.25, filtered: 0.15, later: 0.25 };

export interface NodeData extends Record<string, unknown> {
  n: SceneNode;
  K: number; // cumulative scale of the scene this node is drawn in
  opacity: number;
  lit: boolean; // matches the filter, or contains a match
  hit: boolean; // matches the filter itself
  expanded: boolean;
  focused: boolean; // the deepest expanded frame
  owner: { w: number; h: number } | null; // size of the expanded frame this node is drawn inside (its children fade with the zoom relative to that frame's fit)
  nameCap: number | null; // frames with child frames: max name font size (local px), so the name stays <= 2x the largest child-frame name on screen
  frameBadge: string | null; // "3 containers" on collapsed frames
  matchBadge: string | null; // "2 matches"
  selected: boolean;
  under: string[]; // fills of the expanded frames this node is drawn inside, outermost first (theme.ts: what is behind its label)
}
export interface EdgeData extends Record<string, unknown> {
  e: SceneEdge;
  K: number;
  pts: [number, number][]; // absolute flow coordinates
  opacity: number;
  owner: { w: number; h: number } | null;
  noStart: boolean; // arrow suppressed because that end is the border of an expanded frame (the continuation draws it)
  noEnd: boolean;
  selected: boolean;
  labelPos: [number, number]; // absolute position of the label box
  step: StepState | null; // a dynamic view being stepped through: where this edge stands; null otherwise
}
export type FlowNode = Node<NodeData>;
export type FlowEdge = Edge<EdgeData>;

export interface Rect { x: number; y: number; w: number; h: number }
export interface Composed {
  nodes: FlowNode[];
  edges: FlowEdge[];
  /** Absolute rect of every drawn node. */
  rects: Map<string, Rect>;
  /** Absolute rect of the whole drawing (landscape bounds or view bounds). */
  bounds: Rect;
  /** True when every scene the path needs is loaded. */
  complete: boolean;
  /** Smallest cumulative scale of any frame seen, for maxZoom. */
  minScale: number;
}

interface Level {
  scene: Scene;
  K: number;
  origin: [number, number]; // absolute position of scene.bounds[0..1]
  frameId: string | null; // node the scene is drawn inside
}

export interface ComposeInput {
  m: ModelIndex;
  scenes: Record<string, Scene>;
  path: string;
  view: string | null;
  selection: string | null;
  match: MatchInfo | null;
  /** The step of a dynamic view on screen (1-based); 0 or absent: the whole diagram. */
  step?: number;
}

const plural = (n: number, noun: string) => `${n} ${noun}${n === 1 ? '' : 's'}`;

export function compose(inp: ComposeInput): Composed {
  const { m, scenes, view, match, selection } = inp;
  const nodes: FlowNode[] = [];
  const edges: FlowEdge[] = [];
  const rects = new Map<string, Rect>();
  const empty: Composed = { nodes, edges, rects, bounds: { x: 0, y: 0, w: 1, h: 1 }, complete: false, minScale: 1 };

  // ---- levels
  const levels: Level[] = [];
  let complete = true;
  const chain = view ? [] : chainOf(m, inp.path);
  let look: StepLook | null = null; // stepping through a dynamic view: earlier steps as drawn, the current one marked, later ones dimmed
  if (view) {
    const v = m.viewByKey.get(view);
    const sc = scenes[v?.scene ?? ''];
    if (!sc) return empty;
    levels.push({ scene: sc, K: 1, origin: [sc.bounds[0], sc.bounds[1]], frameId: null });
    if (inp.step) look = stepLook(sc, stepsOf(sc, v?.kind), inp.step);
  } else {
    const root = scenes['landscape'];
    if (!root) return empty;
    levels.push({ scene: root, K: 1, origin: [0, 0], frameId: null });
    for (const id of chain) {
      const prev = levels[levels.length - 1];
      const sc = scenes['e/' + id];
      const fn = prev.scene.nodes.find((n) => n.id === id);
      if (!sc || !fn?.frame) { complete = false; break; }
      const r = absRect(prev, fn);
      const K = prev.K * fn.frame.scale;
      levels.push({ scene: sc, K, origin: [r.x, r.y], frameId: id });
    }
  }
  const expandedIds = new Set(levels.map((l) => l.frameId).filter((x): x is string => !!x));
  const last = levels.length - 1;
  const focusId = levels[last].frameId; // null on the landscape or in a view
  let minScale = 1;
  /** Name size (px at zoom 1) of a scene node, before any cap or floor. */
  const nameSize = (n: SceneNode): number => n.label.lines.find((x) => x.tier === 0)?.size ?? n.style.fontSize;
  /**
   * Cap on the name size of frame `n` drawn at cumulative scale `K`, in px at zoom 1: twice the largest name among its own child
   * frames (the model children that can expand) at their scene's scale; Infinity when it has none. The viewer applies it at the
   * zoom at hand with the child names' 9 px floor (nodes.tsx `capSize`). It does not depend on what is expanded or focused, so a
   * name keeps its size when the frame collapses. A child's name size comes from its scene when that is loaded, else it is taken
   * to be the frame's own, which is what the scenes use.
   */
  const capPx = (n: SceneNode, K: number): number => {
    if (!n.frame) return Infinity;
    const kids = (m.byId.get(n.id)?.children ?? []).filter((c) => m.expandable.has(c));
    if (kids.length === 0) return Infinity;
    const sc = scenes['e/' + n.id];
    let widest = 0;
    for (const c of kids) {
      const cn = sc?.nodes.find((x) => x.id === c);
      widest = Math.max(widest, (cn ? nameSize(cn) : nameSize(n)) * K * n.frame.scale);
    }
    return 2 * widest;
  };

  function absRect(l: Level, n: SceneNode): Rect {
    const [bx, by] = [l.scene.bounds[0], l.scene.bounds[1]];
    if (l.frameId === null) return { x: n.x, y: n.y, w: n.w, h: n.h }; // root scene: scene coordinates are absolute
    return { x: l.origin[0] + l.K * (n.x - bx), y: l.origin[1] + l.K * (n.y - by), w: l.K * n.w, h: l.K * n.h };
  }

  // Which scene nodes are lit (match or contain a match) under the current filter.
  const litIn = (sc: Scene): Set<string> | null => {
    if (!match) return null;
    const lit = new Set<string>();
    for (const n of sc.nodes) {
      if (match.set.has(n.id) || (match.under.get(n.id) ?? 0) > 0) lit.add(n.id);
    }
    // boundaries (groups, the scoped element of a view) are lit when something inside them is
    for (const n of sc.nodes) {
      let p = n.parent;
      if (lit.has(n.id)) while (p) { lit.add(p); p = sc.nodes.find((q) => q.id === p)?.parent ?? null; }
    }
    return lit;
  };

  const under: string[][] = [[]];
  for (let i = 1; i < levels.length; i++) {
    const fn = levels[i - 1].scene.nodes.find((n) => n.id === levels[i].frameId);
    under.push([...under[i - 1], ...(fn ? [fn.style.fill] : [])]);
  }

  levels.forEach((l, li) => {
    const sc = l.scene;
    const lit = litIn(sc);
    const byId = new Map(sc.nodes.map((n) => [n.id, n]));
    // Boundary ids (group:<name>, the scoped element) can repeat in another level's scene: make them unique per scene.
    // A deployment node is only ever in its deployment view: it keeps its id, so a click or a link selects it.
    const rid = (id: string): string => {
      const b = byId.get(id);
      return b?.role === 'boundary' && !DEPLOYMENT_TYPES.has(b.type) ? `${sc.key}|${id}` : id;
    };
    // connected context: nodes in this scene with an edge to the next expanded element
    const focusHere = li < last ? levels[li + 1].frameId : null;
    const connected = new Set<string>();
    if (focusHere) {
      for (const e of sc.edges) {
        if (typeof e.source === 'string' && typeof e.target === 'string') {
          if (e.source === focusHere) connected.add(e.target);
          if (e.target === focusHere) connected.add(e.source);
        }
      }
    }
    const ownerRect = l.frameId ? rects.get(l.frameId) : undefined;
    const owner = ownerRect ? { w: ownerRect.w, h: ownerRect.h } : null;
    for (const n of sc.nodes) {
      const r = absRect(l, n);
      rects.set(rid(n.id), r);
      const parent = n.parent ? rid(n.parent) : l.frameId;
      // Relative position by the same arithmetic in every state: K * (local - min), so nothing outside
      // an expanded subtree can differ between the before and after graphs.
      const rel = n.parent
        ? { x: l.K * (n.x - byId.get(n.parent)!.x), y: l.K * (n.y - byId.get(n.parent)!.y) }
        : l.frameId === null ? { x: n.x, y: n.y }
        : { x: l.K * (n.x - sc.bounds[0]), y: l.K * (n.y - sc.bounds[1]) };
      const expanded = expandedIds.has(n.id);
      let state = OPACITY.focus;
      // Scenes above the deepest one are context; the landscape alone or a view is all in focus.
      if (li < last) state = connected.has(n.id) ? OPACITY.connected : OPACITY.context;
      if (n.id === focusId) state = OPACITY.focus;
      const isLit = lit ? lit.has(n.id) : true;
      const fb = n.frame && !expanded ? plural(n.frame.children, (n.frame.childType ?? 'element').toLowerCase()) : null;
      const nm = match && n.frame && !expanded ? (match.under.get(n.id) ?? 0) : 0;
      if (n.frame) minScale = Math.min(minScale, l.K * n.frame.scale);
      const sty = n.style.opacity ?? 1;
      if (look?.later.has(n.id)) state = Math.min(state, OPACITY.later);
      nodes.push({
        id: rid(n.id), type: n.role === 'boundary' ? 'c4boundary' : 'c4element',
        position: rel, parentId: parent ?? undefined,
        width: r.w, height: r.h,
        draggable: false, connectable: false, selectable: true, focusable: true, selected: selection === n.id,
        data: {
          n, K: l.K, opacity: Math.min(state * sty, lit && !isLit ? OPACITY.filtered : 1),
          owner, lit: isLit, hit: !!match?.set.has(n.id), expanded, focused: n.id === focusId,
          nameCap: n.frame && Number.isFinite(capPx(n, l.K)) ? capPx(n, l.K) / l.K : null, frameBadge: fb,
          matchBadge: nm > 0 ? plural(nm, 'match').replace('matchs', 'matches') : null,
          selected: selection === n.id, under: under[li],
        },
      });
    }
  });

  // ---- edges
  levels.forEach((l, li) => {
    const sc = l.scene;
    const lit = litIn(sc);
    const focusHere = li < last ? levels[li + 1].frameId : null;
    const ownerRect = l.frameId ? rects.get(l.frameId) : undefined;
    const owner = ownerRect ? { w: ownerRect.w, h: ownerRect.h } : null;
    const ptAbs = (p: [number, number]): [number, number] => [
      l.frameId === null ? p[0] : l.origin[0] + l.K * (p[0] - sc.bounds[0]),
      l.frameId === null ? p[1] : l.origin[1] + l.K * (p[1] - sc.bounds[1]),
    ];
    for (const e of sc.edges) {
      const rid = (id: string): string => {
        const b = sc.nodes.find((n) => n.id === id);
        return b?.role === 'boundary' && !DEPLOYMENT_TYPES.has(b.type) ? `${sc.key}|${id}` : id;
      };
      const s = typeof e.source === 'string' ? rid(e.source) : l.frameId;
      const t = typeof e.target === 'string' ? rid(e.target) : l.frameId;
      if (!s || !t || !rects.has(s) || !rects.has(t)) continue;
      const touchesFocus = focusHere !== null && (e.source === focusHere || e.target === focusHere);
      const state = li === last ? OPACITY.focus : touchesFocus ? OPACITY.connected : OPACITY.context;
      const isLit = !lit || ((typeof e.source !== 'string' || lit.has(e.source)) && (typeof e.target !== 'string' || lit.has(e.target)));
      const startExpanded = typeof e.source === 'string' && expandedIds.has(e.source);
      const endExpanded = typeof e.target === 'string' && expandedIds.has(e.target);
      const step = look?.edges.get(e.id) ?? null;
      edges.push({
        id: `${sc.key}::${e.id}`, source: s, target: t, type: 'elk',
        selectable: false, focusable: false, zIndex: 1000,
        data: {
          e, K: l.K, pts: e.points.map(ptAbs), opacity: Math.min(state * (e.style.opacity ?? 1), isLit ? 1 : OPACITY.filtered, step === 'later' ? OPACITY.later : 1),
          owner, noStart: startExpanded || typeof e.source !== 'string', noEnd: endExpanded || typeof e.target !== 'string',
          selected: selection === e.id, labelPos: e.label ? ptAbs([e.label.x, e.label.y]) : [0, 0], step,
        },
      });
    }
  });

  const root = levels[0];
  const bounds: Rect = { x: root.origin[0], y: root.origin[1], w: root.scene.bounds[2], h: root.scene.bounds[3] };
  return { nodes, edges, rects, bounds, complete, minScale };
}

/** Camera target: the deepest expanded frame, or the whole drawing. */
export function pathRect(c: Composed, path: string, m: ModelIndex): Rect {
  if (!path) return c.bounds;
  return c.rects.get(path) ?? c.rects.get(chainOf(m, path).slice(-1)[0]) ?? c.bounds;
}
