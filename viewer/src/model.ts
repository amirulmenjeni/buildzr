import type { Element, IndexJson, ModelJson, Relationship, ViewDef } from './types';
import type { Filter } from './route';

/** Element types of the model tree and its scenes. */
export const KNOWN_TYPES = new Set(['Person', 'SoftwareSystem', 'Container', 'Component']);
/** Element types drawn in deployment views only: not in the tree, reached through those views, search and links. */
export const DEPLOYMENT_TYPES = new Set(['DeploymentNode', 'InfrastructureNode', 'ContainerInstance', 'SoftwareSystemInstance']);
/** Custom elements: outside the C4 hierarchy. Roots without children, shown in the tree after the people and systems, drawn in the views that list them. */
export const CUSTOM_TYPES = new Set(['Element']);
/** Anything else (a type this viewer does not know) is dropped, with its descendants. */
const indexed = (t: string): boolean => KNOWN_TYPES.has(t) || DEPLOYMENT_TYPES.has(t) || CUSTOM_TYPES.has(t);
export const isDeployment = (e: Element | undefined): boolean => !!e && DEPLOYMENT_TYPES.has(e.type);
export const isCustom = (e: Element | undefined): boolean => !!e && CUSTOM_TYPES.has(e.type);
/** Drawn in authored views only, never on the model canvas (the landscape and the element levels): deployment and custom elements. */
export const isViewOnly = (e: Element | undefined): boolean => isDeployment(e) || isCustom(e);

export interface ModelIndex {
  elements: Element[]; // known and deployment elements, pre-order, as in model.json
  byId: Map<string, Element>;
  rels: Relationship[];
  relById: Map<string, Relationship>;
  views: ViewDef[];
  viewByKey: Map<string, ViewDef>;
  order: Map<string, number>;
  /** Elements whose inside is a scene (index.json has e/<id>). */
  expandable: Set<string>;
  roots: string[];
  tags: string[];
  /** Relationships whose source or destination is the element itself. */
  own: Map<string, { out: Relationship[]; in: Relationship[] }>;
  /** Software system or container id -> the deployment instances that run it (instanceOf), in model order. */
  instancesOf: Map<string, string[]>;
}

export function indexModel(model: ModelJson, index: IndexJson): ModelIndex {
  const byId = new Map<string, Element>();
  const elements: Element[] = [];
  for (const e of model.elements) {
    if (!indexed(e.type)) continue;
    if (e.parent !== null && !byId.has(e.parent)) continue; // under an unknown element
    // A deployment element sits under a deployment node or at the top; nothing else nests with deployment elements.
    if (e.parent !== null && DEPLOYMENT_TYPES.has(e.type) !== DEPLOYMENT_TYPES.has(byId.get(e.parent)!.type)) continue;
    // A custom element is a root with no children: one under or over another element is not understood and dropped.
    if (e.parent !== null && (CUSTOM_TYPES.has(e.type) || CUSTOM_TYPES.has(byId.get(e.parent)!.type))) continue;
    if (DEPLOYMENT_TYPES.has(e.type) && e.instanceOf !== undefined && !byId.has(e.instanceOf)) continue;
    const el = { ...e, children: [] as string[] };
    byId.set(el.id, el);
    elements.push(el);
  }
  for (const e of elements) if (e.parent) byId.get(e.parent)!.children.push(e.id);
  const rels = model.relationships.filter((r) => byId.has(r.source) && byId.has(r.destination));
  const own = new Map<string, { out: Relationship[]; in: Relationship[] }>();
  for (const e of elements) own.set(e.id, { out: [], in: [] });
  for (const r of rels) { own.get(r.source)!.out.push(r); own.get(r.destination)!.in.push(r); }
  const instancesOf = new Map<string, string[]>();
  for (const e of elements) {
    if (!e.instanceOf) continue;
    const list = instancesOf.get(e.instanceOf);
    if (list) list.push(e.id); else instancesOf.set(e.instanceOf, [e.id]);
  }
  const tagSet = new Set<string>();
  for (const e of elements) for (const t of e.tags) if (!isInternalTag(t)) tagSet.add(t);
  return {
    elements, byId, rels, relById: new Map(rels.map((r) => [r.id, r])),
    views: model.views, viewByKey: new Map(model.views.map((v) => [v.key, v])),
    order: new Map(elements.map((e, i) => [e.id, i])),
    expandable: new Set(elements.filter((e) => e.children.length > 0 && ('e/' + e.id) in index.scenes).map((e) => e.id)),
    roots: [
      ...elements.filter((e) => e.parent === null && KNOWN_TYPES.has(e.type)),
      ...elements.filter((e) => e.parent === null && CUSTOM_TYPES.has(e.type)),
    ].map((e) => e.id),
    tags: [...tagSet].sort(),
    own, instancesOf,
  };
}

/** Internal style tags written by buildzr; they stay in the data but are not shown. */
export const isInternalTag = (t: string): boolean => /^buildzr-style(elements|relationships)-/.test(t);

/** The name of an element type for people: "SoftwareSystem" -> "Software System"; a custom element is an "Element" in the data. */
export const typeLabel = (t: string): string => (t === 'Element' ? 'Custom element' : t.replace(/([a-z])([A-Z])/g, '$1 $2'));

/** Ancestors from the root down to (excluding) id. */
export function ancestors(m: ModelIndex, id: string): string[] {
  const out: string[] = [];
  for (let p = m.byId.get(id)?.parent ?? null; p; p = m.byId.get(p)?.parent ?? null) out.unshift(p);
  return out;
}

/** The chain of expanded elements for a path: ancestors first, then the element itself. */
export const chainOf = (m: ModelIndex, path: string): string[] => (path ? [...ancestors(m, path), path] : []);

export function descendants(m: ModelIndex, id: string): string[] {
  const out: string[] = [];
  const walk = (i: string) => { for (const c of m.byId.get(i)!.children) { out.push(c); walk(c); } };
  walk(id);
  return out;
}

/** Element types that can be deployed: the ones a deployment node can hold an instance of. */
export const DEPLOYABLE_TYPES = new Set(['SoftwareSystem', 'Container']);

export interface DeploymentRow {
  id: string;
  /** Names of the deployment nodes the instance sits in, outermost first. */
  nodes: string[];
  /** Copies of the innermost node, when more than one ("2", "0..N"). */
  copies: string | null;
  /** Whether a deployment view draws it: only then can the viewer show it. */
  shown: boolean;
}
export interface DeploymentGroup { environment: string; name: string; rows: DeploymentRow[] }

/** Where a software system or container runs, by environment (environment order of model.json). Empty when it runs nowhere. */
export function deploymentsOf(m: ModelIndex, id: string, environments: { key: string; name: string }[]): DeploymentGroup[] {
  const groups = new Map<string, DeploymentGroup>(environments.map((e) => [e.key, { environment: e.key, name: e.name, rows: [] }]));
  for (const instId of m.instancesOf.get(id) ?? []) {
    const inst = m.byId.get(instId)!;
    const key = inst.environment ?? '';
    let g = groups.get(key);
    if (!g) { g = { environment: key, name: key, rows: [] }; groups.set(key, g); }
    const nodes = ancestors(m, instId).map((a) => m.byId.get(a)!.name);
    const parent = inst.parent ? m.byId.get(inst.parent) : undefined;
    g.rows.push({
      id: instId, nodes, copies: parent?.instances && parent.instances !== '1' ? parent.instances : null,
      shown: inst.views.some((k) => m.viewByKey.has(k)),
    });
  }
  return [...groups.values()].filter((g) => g.rows.length > 0);
}

export interface RelRow { rel: Relationship; other: string }

/** Incoming and outgoing relationships of an element: its own, or rolled up from its subtree (internal ones excluded). */
export function relationsOf(m: ModelIndex, id: string, rolled: boolean): { out: RelRow[]; in: RelRow[] } {
  const ids = rolled ? new Set([id, ...descendants(m, id)]) : new Set([id]);
  const out: RelRow[] = [];
  const inc: RelRow[] = [];
  for (const x of ids) {
    const o = m.own.get(x)!;
    for (const r of o.out) if (!ids.has(r.destination)) out.push({ rel: r, other: r.destination });
    for (const r of o.in) if (!ids.has(r.source)) inc.push({ rel: r, other: r.source });
  }
  return { out, in: inc };
}

// ---- search and tag filter (matching only; dimming happens in the views)

export const filterActive = (f: Filter): boolean => f.q.trim() !== '' || f.tags.length > 0;

function haystack(e: Element): string {
  return [e.name, e.id, e.type, typeLabel(e.type), e.technology, e.metadata, e.description, ...e.tags].filter(Boolean).join('\n').toLowerCase();
}

export interface MatchInfo {
  /** Matching element ids in model order. */
  list: string[];
  set: Set<string>;
  /** Proper ancestors of a match -> number of matches below them (all depths). */
  under: Map<string, number>;
}

let memo: { m: ModelIndex; key: string; v: MatchInfo | null } | null = null;
export function computeMatches(m: ModelIndex, f: Filter): MatchInfo | null {
  if (!filterActive(f)) return null;
  const key = JSON.stringify(f);
  if (memo && memo.m === m && memo.key === key) return memo.v;
  const v = computeMatchesUncached(m, f);
  memo = { m, key, v };
  return v;
}

function computeMatchesUncached(m: ModelIndex, f: Filter): MatchInfo {
  const phrase = f.q.toLowerCase().split(/\s+/).filter(Boolean).join(' '); // the whole text is one phrase: "System 7" must not match "System 17" or "Container 7"
  const list: string[] = [];
  for (const e of m.elements) {
    const hay = haystack(e);
    const qOk = phrase === '' || hay.includes(phrase);
    let tOk = true;
    if (f.tags.length) tOk = f.mode === 'and' ? f.tags.every((t) => e.tags.includes(t)) : f.tags.some((t) => e.tags.includes(t));
    if (qOk && tOk) list.push(e.id);
  }
  const under = new Map<string, number>();
  for (const id of list) for (const a of ancestors(m, id)) under.set(a, (under.get(a) ?? 0) + 1);
  return { list, set: new Set(list), under };
}
