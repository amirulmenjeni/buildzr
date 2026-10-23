import { useEffect, useMemo, useRef, useState, type JSX, type KeyboardEvent } from 'react';
import { computeMatches, typeLabel, type ModelIndex } from './model';
import { useStore } from './store';

/** WAI-ARIA tree over the model's containment: roving tabindex, arrows, Home/End, type-ahead. */
export function Tree() {
  const m = useStore((s) => s.m)!;
  const selection = useStore((s) => s.selection);
  const treeOpen = useStore((s) => s.treeOpen);
  const filter = useStore((s) => s.filter);
  const select = useStore((s) => s.select);
  const expand = useStore((s) => s.expand);
  const toggleTree = useStore((s) => s.toggleTree);
  const setUi = useStore((s) => s.setUi);
  const match = useMemo(() => computeMatches(m, filter), [m, filter]);
  const [focusId, setFocusId] = useState<string | null>(null);
  const root = useRef<HTMLUListElement>(null);
  const typed = useRef({ buf: '', t: 0 });

  const visible = useMemo(() => {
    const out: string[] = [];
    const walk = (id: string) => { out.push(id); if (treeOpen[id]) for (const c of m.byId.get(id)!.children) walk(c); };
    for (const r of m.roots) walk(r);
    return out;
  }, [m, treeOpen]);
  const tabId = focusId && visible.includes(focusId) ? focusId : selection && visible.includes(selection) ? selection : visible[0];

  useEffect(() => {
    // Selection changes from elsewhere (canvas, search, hash) move the roving stop with it.
    if (selection && m.byId.has(selection)) setFocusId(selection);
  }, [selection, m]);

  const focusItem = (id: string) => {
    setFocusId(id);
    requestAnimationFrame(() => root.current?.querySelector<HTMLElement>(`[data-id="${CSS.escape(id)}"]`)?.focus());
  };

  const onKeyDown = (ev: KeyboardEvent) => {
    const id = (ev.target as HTMLElement).closest<HTMLElement>('[role=treeitem]')?.dataset.id;
    if (!id) return;
    const el = m.byId.get(id)!;
    const i = visible.indexOf(id);
    const hasKids = el.children.length > 0;
    let handled = true;
    switch (ev.key) {
      case 'ArrowDown': if (i < visible.length - 1) focusItem(visible[i + 1]); break;
      case 'ArrowUp': if (i > 0) focusItem(visible[i - 1]); break;
      case 'Home': focusItem(visible[0]); break;
      case 'End': focusItem(visible[visible.length - 1]); break;
      case 'ArrowRight':
        if (hasKids && !treeOpen[id]) toggleTree(id, true);
        else if (hasKids) focusItem(el.children[0]);
        break;
      case 'ArrowLeft':
        if (hasKids && treeOpen[id]) toggleTree(id, false);
        else if (el.parent) focusItem(el.parent);
        break;
      case 'Enter': expand(id); setUi({ drawer: false }); break; // Open: expand the canvas into it (or just select a leaf)
      case ' ': select(id, { reveal: true }); setUi({ drawer: false }); break;
      default:
        if (ev.key.length === 1 && !ev.ctrlKey && !ev.metaKey && !ev.altKey) {
          const now = Date.now();
          const t = typed.current;
          t.buf = now - t.t > 700 ? ev.key.toLowerCase() : t.buf + ev.key.toLowerCase();
          t.t = now;
          const start = t.buf.length === 1 ? i + 1 : i;
          const order = [...visible.slice(start), ...visible.slice(0, start)];
          const hit = order.find((v) => m.byId.get(v)!.name.toLowerCase().startsWith(t.buf));
          if (hit) focusItem(hit);
        } else handled = false;
    }
    if (handled) ev.preventDefault();
  };

  const renderItem = (id: string, level: number): JSX.Element => {
    const el = m.byId.get(id)!;
    const hasKids = el.children.length > 0;
    const open = !!treeOpen[id];
    const hit = !!match?.set.has(id);
    const below = match?.under.get(id) ?? 0;
    const cls = ['row', selection === id ? 'selected' : '', match && !hit ? 'dimmed' : '', hit ? 'match' : '', below > 0 ? 'has-match' : ''].filter(Boolean).join(' ');
    return (
      <li key={id} role="treeitem" aria-level={level} aria-expanded={hasKids ? open : undefined} aria-selected={selection === id}
          data-id={id} tabIndex={tabId === id ? 0 : -1}>
        <div className={cls} style={{ paddingLeft: 6 + (level - 1) * 14 }}
             onClick={() => { setFocusId(id); select(id, { reveal: true }); setUi({ drawer: false }); }} onDoubleClick={() => expand(id)}>
          {hasKids ? (
            <span className="twisty" aria-hidden="true" onClick={(e) => { e.stopPropagation(); toggleTree(id); }}>{open ? '▾' : '▸'}</span>
          ) : <span className="twisty" aria-hidden="true" />}
          <span className="name">{el.name}</span>
          <span className="kind">{typeLabel(el.type)}</span>
          {below > 0 && <span className="count" title="matches below">{below}</span>}
        </div>
        {hasKids && open && <ul role="group">{el.children.map((c) => renderItem(c, level + 1))}</ul>}
      </li>
    );
  };

  return (
    <ul role="tree" aria-label="Model" ref={root} className="tree" onKeyDown={onKeyDown}>
      {m.roots.map((r) => renderItem(r, 1))}
    </ul>
  );
}

export function ViewsList({ m }: { m: ModelIndex }) {
  const view = useStore((s) => s.view);
  const openView = useStore((s) => s.openView);
  const setUi = useStore((s) => s.setUi);
  const selection = useStore((s) => s.selection);
  return (
    <ul className="views" aria-label="Views">
      {m.views.map((v) => (
        <li key={v.key}>
          <button className={view === v.key ? 'on' : ''} data-view={v.key} aria-current={view === v.key ? 'page' : undefined}
                  onClick={() => { openView(v.key, selection && m.byId.has(selection) ? selection : null); setUi({ drawer: false }); }}>
            {v.title}<span className="kind">{v.kind}</span>
          </button>
        </li>
      ))}
    </ul>
  );
}
