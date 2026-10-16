import type { Element, IndexJson, ModelJson, Relationship, ViewDef } from './types';
import type { Filter } from './route';

/** Element types the viewer draws. Anything else (e.g. a future DeploymentNode) is dropped, with its descendants. */
export const KNOWN_TYPES = new Set(['Person', 'SoftwareSystem', 'Container', 'Component']);

export interface ModelIndex {
  elements: Element[]; // known elements, pre-order, as in model.json
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
}

export function indexModel(model: ModelJson, index: IndexJson): ModelIndex {
  const byId = new Map<string, Element>();
  const elements: Element[] = [];
  for (const e of model.elements) {
    if (!KNOWN_TYPES.has(e.type)) continue;
    if (e.parent !== null && !byId.has(e.parent)) continue; // under an unknown element
    const el = { ...e, children: [] as string[] };
    byId.set(el.id, el);
    elements.push(el);
  }
  for (const e of elements) if (e.parent) byId.get(e.parent)!.children.push(e.id);
  const rels = model.relationships.filter((r) => byId.has(r.source) && byId.has(r.destination));
  const own = new Map<string, { out: Relationship[]; in: Relationship[] }>();
  for (const e of elements) own.set(e.id, { out: [], in: [] });
  for (const r of rels) { own.get(r.source)!.out.push(r); own.get(r.destination)!.in.push(r); }
  const tagSet = new Set<string>();
  for (const e of elements) for (const t of e.tags) if (!isInternalTag(t)) tagSet.add(t);
  return {
    elements, byId, rels, relById: new Map(rels.map((r) => [r.id, r])),
    views: model.views, viewByKey: new Map(model.views.map((v) => [v.key, v])),
    order: new Map(elements.map((e, i) => [e.id, i])),
    expandable: new Set(elements.filter((e) => e.children.length > 0 && ('e/' + e.id) in index.scenes).map((e) => e.id)),
    roots: elements.filter((e) => e.parent === null).map((e) => e.id),
    tags: [...tagSet].sort(),
    own,
  };
}

/** Internal style tags written by buildzr; they stay in the data but are not shown. */
export const isInternalTag = (t: string): boolean => /^buildzr-style(elements|relationships)-/.test(t);

export const typeLabel = (t: string): string => t.replace(/([a-z])([A-Z])/g, '$1 $2');

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
  return [e.name, e.id, e.type, typeLabel(e.type), e.technology, e.description, ...e.tags].filter(Boolean).join('\n').toLowerCase();
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
