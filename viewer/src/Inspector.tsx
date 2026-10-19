import { useMemo } from 'react';
import { isDeployment, isInternalTag, relationsOf, typeLabel, type ModelIndex, type RelRow } from './model';
import { useStore } from './store';

function RelList({ title, rows, m, kind }: { title: string; rows: RelRow[]; m: ModelIndex; kind: 'outgoing' | 'incoming' }) {
  const select = useStore((s) => s.select);
  return (
    <section data-section={kind}>
      <h3>{title} <span className="n" data-count={rows.length}>{rows.length}</span></h3>
      <ul>
        {rows.map(({ rel, other }) => (
          <li key={rel.id} data-rel={rel.id}>
            <button className="link" onClick={() => select(other, { reveal: true })}>
              {kind === 'outgoing' ? '→' : '←'} {m.byId.get(other)?.name ?? other}
            </button>
            {rel.description && <span className="desc"> {rel.description}</span>}
            {rel.technology && <span className="tech"> [{rel.technology}]</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

export function Inspector() {
  const m = useStore((s) => s.m)!;
  const selection = useStore((s) => s.selection);
  const scenes = useStore((s) => s.scenes);
  const view = useStore((s) => s.view);
  const path = useStore((s) => s.path);
  const rolled = useStore((s) => s.rolled);
  const setRolled = useStore((s) => s.setRolled);
  const select = useStore((s) => s.select);
  const expand = useStore((s) => s.expand);
  const openView = useStore((s) => s.openView);
  const showInModel = useStore((s) => s.showInModel);
  const environments = useStore((s) => s.model?.deployment.environments);

  const el = selection ? m.byId.get(selection) : undefined;
  const edge = useMemo(() => {
    if (!selection || el) return null;
    for (const sc of Object.values(scenes)) {
      const e = sc.edges.find((x) => x.id === selection);
      if (e) return e;
    }
    return null;
  }, [selection, el, scenes]);
  const rel = useMemo(() => (el ? relationsOf(m, el.id, rolled) : null), [m, el, rolled]);

  return (
    <aside role="complementary" aria-label="Inspector" className="inspector">
      {el && rel ? (
        <div data-selected-id={el.id}>
          <h2>{el.name}</h2>
          <p className="type">{typeLabel(el.type)}{el.technology ? ` · ${el.technology}` : ''}</p>
          <div className="actions">
            {m.expandable.has(el.id) && path !== el.id && <button data-action="open" onClick={() => expand(el.id)}>Open</button>}
            {view && (!isDeployment(el) || el.instanceOf) && <button data-action="show-in-model" onClick={showInModel}>Show in model</button>}
          </div>
          {el.description && <p className="description">{el.description}</p>}
          <dl>
            <dt>Path</dt><dd><code>{el.id}</code></dd>
            {el.environment && (<><dt>Environment</dt><dd data-field="environment">{environments?.find((e) => e.key === el.environment)?.name ?? el.environment}</dd></>)}
            {el.instances && (<><dt>Instances</dt><dd data-field="instances">{el.instances}</dd></>)}
            {el.instanceOf && (<><dt>Instance of</dt><dd data-field="instance-of"><button className="link" onClick={() => select(el.instanceOf!, { reveal: true })}>{m.byId.get(el.instanceOf)?.name ?? el.instanceOf}</button></dd></>)}
            {el.group && (<><dt>Group</dt><dd>{el.group}</dd></>)}
            {el.url && (<><dt>URL</dt><dd><a href={el.url} target="_blank" rel="noreferrer noopener">{el.url}</a></dd></>)}
          </dl>
          {el.tags.some((t) => !isInternalTag(t)) && <p className="tags" aria-label="Tags">{el.tags.filter((t) => !isInternalTag(t)).map((t) => <span className="tag" key={t}>{t}</span>)}</p>}
          {Object.keys(el.properties).length > 0 && (
            <section data-section="properties"><h3>Properties</h3>
              <dl>{Object.entries(el.properties).map(([k, v]) => (<span key={k}><dt>{k}</dt><dd>{v}</dd></span>))}</dl>
            </section>
          )}
          {el.healthChecks && el.healthChecks.length > 0 && (
            <section data-section="health-checks"><h3>Health checks</h3>
              <ul>{el.healthChecks.map((h, i) => (
                <li key={i}>{h.name} <code>{h.url}</code>{h.interval !== null ? ` every ${h.interval} s` : ''}{h.timeout !== null ? `, timeout ${h.timeout} ms` : ''}</li>
              ))}</ul>
            </section>
          )}
          <label className="toggle">
            <input type="checkbox" checked={rolled} onChange={(e) => setRolled(e.target.checked)} data-testid="rolled" /> Include relationships of descendants
          </label>
          <RelList title="Outgoing" rows={rel.out} m={m} kind="outgoing" />
          <RelList title="Incoming" rows={rel.in} m={m} kind="incoming" />
          <section data-section="views"><h3>In views <span className="n" data-count={el.views.length}>{el.views.length}</span></h3>
            <ul>{el.views.map((k) => (
              <li key={k}><button className="link" data-view={k} onClick={() => openView(k, el.id)}>{m.viewByKey.get(k)?.title ?? k}</button></li>
            ))}</ul>
          </section>
        </div>
      ) : edge ? (
        <div data-selected-edge={edge.id}>
          <h2>Relationships</h2>
          <p className="type">{edge.count} rolled up into one edge</p>
          <section data-section="rels"><ul>
            {edge.rels.map((id) => {
              const r = m.relById.get(id);
              return (
                <li key={id} data-rel={id}>
                  {r ? (
                    <>
                      <button className="link" onClick={() => select(r.source, { reveal: true })}>{m.byId.get(r.source)?.name}</button>
                      {' → '}
                      <button className="link" onClick={() => select(r.destination, { reveal: true })}>{m.byId.get(r.destination)?.name}</button>
                      {r.description && <span className="desc"> {r.description}</span>}
                      {r.technology && <span className="tech"> [{r.technology}]</span>}
                    </>
                  ) : id}
                </li>
              );
            })}
          </ul></section>
        </div>
      ) : (
        <p className="empty">Select an element or a relationship.</p>
      )}
    </aside>
  );
}
