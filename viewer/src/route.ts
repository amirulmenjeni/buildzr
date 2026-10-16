// Hash grammar: docs/viewer-hash-routes.md. The store is the source of truth; this only converts.

export interface Filter { q: string; tags: string[]; mode: 'and' | 'or' }
export const emptyFilter: Filter = { q: '', tags: [], mode: 'or' };
export interface Route { view: string | null; path: string; sel: string | null; filter: Filter }

const dec = (s: string): string => { try { return decodeURIComponent(s); } catch { return s; } };
// Edge ids contain '->', ':' and '/'; '/' stays readable, the rest is percent-encoded.
const enc = (s: string): string => encodeURIComponent(s).replace(/%2F/g, '/');

export function parseHash(hash: string): Route {
  const h = hash.replace(/^#/, '');
  const qi = h.indexOf('?');
  const route = qi < 0 ? h : h.slice(0, qi);
  const qs = qi < 0 ? '' : h.slice(qi + 1);
  const params = new Map<string, string>();
  for (const part of qs.split('&')) {
    if (!part) continue;
    const i = part.indexOf('=');
    const k = i < 0 ? part : part.slice(0, i);
    if (!params.has(k)) params.set(k, i < 0 ? '' : dec(part.slice(i + 1).replace(/\+/g, ' ')));
  }
  let view: string | null = null;
  let path = '';
  if (route.startsWith('/v/')) view = dec(route.slice(3)).replace(/\/+$/, '') || null;
  else if (route.startsWith('/m/')) path = dec(route.slice(3)).replace(/\/+$/, '');
  const tags = (params.get('tags') ?? '').split(',').filter(Boolean);
  return {
    view, path, sel: params.get('sel') || null,
    filter: { q: params.get('q') ?? '', tags, mode: params.get('mode') === 'and' ? 'and' : 'or' },
  };
}

export function buildHash(r: Route): string {
  const base = r.view ? `#/v/${enc(r.view)}` : r.path ? `#/m/${enc(r.path)}` : '#/m';
  const p: string[] = [];
  if (r.sel) p.push('sel=' + enc(r.sel));
  if (r.filter.q) p.push('q=' + encodeURIComponent(r.filter.q));
  if (r.filter.tags.length) p.push('tags=' + r.filter.tags.map(encodeURIComponent).join(','));
  if (r.filter.mode === 'and') p.push('mode=and');
  return p.length ? `${base}?${p.join('&')}` : base;
}
