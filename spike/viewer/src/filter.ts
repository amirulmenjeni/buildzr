import type { Scene, SceneNode } from './scene';

export interface FilterState { q: string; tags: string[]; mode: 'and' | 'or' }

export function parseHash(hash: string): { view: string | null; f: FilterState } {
  const m = hash.replace(/^#/, '');
  const [path, qs = ''] = m.split('?');
  const view = path.startsWith('/v/') ? decodeURIComponent(path.slice(3)) : null;
  const p = new URLSearchParams(qs);
  return {
    view,
    f: { q: p.get('q') ?? '', tags: (p.get('tags') ?? '').split(',').filter(Boolean), mode: p.get('mode') === 'and' ? 'and' : 'or' },
  };
}

export function buildHash(view: string, f: FilterState): string {
  const p = new URLSearchParams();
  if (f.q) p.set('q', f.q);
  if (f.tags.length) p.set('tags', f.tags.join(','));
  if (f.tags.length > 1 || f.mode === 'and') p.set('mode', f.mode);
  const s = p.toString();
  return `#/v/${encodeURIComponent(view)}${s ? '?' + s : ''}`;
}

export const isActive = (f: FilterState) => f.q.trim() !== '' || f.tags.length > 0;

function haystack(n: SceneNode): string {
  return [n.name, n.id, n.type, n.technology, n.description, ...n.tags].filter(Boolean).join('\n').toLowerCase();
}

/** Returns the set of matching node ids, or null when no filter is active. */
export function matchNodes(scene: Scene, f: FilterState): Set<string> | null {
  if (!isActive(f)) return null;
  const toks = f.q.toLowerCase().split(/\s+/).filter(Boolean);
  const out = new Set<string>();
  for (const n of scene.nodes) {
    const hay = haystack(n);
    const qOk = toks.every((t) => hay.includes(t));
    let tOk = true;
    if (f.tags.length) tOk = f.mode === 'and' ? f.tags.every((t) => n.tags.includes(t)) : f.tags.some((t) => n.tags.includes(t));
    if (qOk && tOk) out.add(n.id);
  }
  return out;
}

export function allTags(scene: Scene): string[] {
  return [...new Set(scene.nodes.flatMap((n) => n.tags))].sort();
}
