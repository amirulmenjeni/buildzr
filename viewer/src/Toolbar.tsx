import { useMemo } from 'react';
import { computeMatches } from './model';
import { useStore } from './store';

export function Toolbar() {
  const m = useStore((s) => s.m)!;
  const filter = useStore((s) => s.filter);
  const setFilter = useStore((s) => s.setFilter);
  const gotoMatch = useStore((s) => s.gotoMatch);
  const selection = useStore((s) => s.selection);
  const match = useMemo(() => computeMatches(m, filter), [m, filter]);
  const idx = match && selection ? match.list.indexOf(selection) : -1;
  return (
    <div className="toolbar" role="search">
      <input type="search" aria-label="Search" placeholder="Search name, path, type, technology, description, tags" value={filter.q}
        onChange={(e) => setFilter({ ...filter, q: e.target.value })}
        onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); gotoMatch(e.shiftKey ? -1 : 1); } }} />
      {(
        <span className="matchbar" style={match ? undefined : { visibility: 'hidden' }} aria-hidden={match ? undefined : true}>
          <span role="status" data-testid="match-count">{!match ? '' : match.list.length === 0 ? 'No matches' : `${idx >= 0 ? idx + 1 + ' of ' : ''}${match.list.length} match${match.list.length === 1 ? '' : 'es'}`}</span>
          <button aria-label="Previous match" disabled={!match || match.list.length === 0} onClick={() => gotoMatch(-1)}>↑</button>
          <button aria-label="Next match" disabled={!match || match.list.length === 0} onClick={() => gotoMatch(1)}>↓</button>
        </span>
      )}
      <select aria-label="Tag mode" value={filter.mode} onChange={(e) => setFilter({ ...filter, mode: e.target.value as 'and' | 'or' })}>
        <option value="or">any tag</option><option value="and">all tags</option>
      </select>
      <span className="chips">
        {m.tags.filter((t) => t !== 'Element').map((t) => (
          <button key={t} className={'chip' + (filter.tags.includes(t) ? ' on' : '')} data-tag={t} aria-pressed={filter.tags.includes(t)}
            onClick={() => setFilter({ ...filter, tags: filter.tags.includes(t) ? filter.tags.filter((x) => x !== t) : [...filter.tags, t] })}>{t}</button>
        ))}
      </span>
      <button className="clear" style={filter.q || filter.tags.length > 0 ? undefined : { visibility: 'hidden' }} onClick={() => setFilter({ q: '', tags: [], mode: 'or' })}>Clear</button>
    </div>
  );
}

export function Breadcrumbs() {
  const m = useStore((s) => s.m)!;
  const path = useStore((s) => s.path);
  const view = useStore((s) => s.view);
  const setPath = useStore((s) => s.setPath);
  const chain: string[] = [];
  if (!view) for (let p: string | null = path; p; p = m.byId.get(p)?.parent ?? null) chain.unshift(p);
  const v = view ? m.viewByKey.get(view) : null;
  return (
    <nav aria-label="Breadcrumb" className="crumbs">
      <ol>
        <li><button onClick={() => setPath('')} aria-current={!view && !path ? 'page' : undefined}>{view ? 'Model' : 'Landscape'}</button></li>
        {chain.map((id, i) => (
          <li key={id}><button data-crumb={id} onClick={() => setPath(id)} aria-current={i === chain.length - 1 ? 'page' : undefined}>{m.byId.get(id)!.name}</button></li>
        ))}
        {v && <li><span aria-current="page" data-crumb-view={v.key}>View: {v.title}</span></li>}
      </ol>
    </nav>
  );
}
