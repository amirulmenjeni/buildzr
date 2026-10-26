import { Fragment, useMemo, useRef } from 'react';
import { DEPLOYABLE_TYPES, deploymentsOf, isCustom, isDeployment, isInternalTag, relationsOf, typeLabel, type DeploymentGroup, type ModelIndex, type RelRow } from './model';
import { useStore } from './store';
import { usePhone } from './usePhone';

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

/** Where a software system or container runs: one line per instance, by environment. */
function Deployments({ groups, headingRef }: { groups: DeploymentGroup[]; headingRef: React.RefObject<HTMLHeadingElement | null> }) {
  const showInstance = useStore((s) => s.showInstance);
  const total = groups.reduce((n, g) => n + g.rows.length, 0);
  return (
    <section data-section="deployments" aria-labelledby="deployments-h">
      <h3 id="deployments-h" tabIndex={-1} ref={headingRef}>Deployed on <span className="n" data-count={total}>{total}</span></h3>
      {total === 0 ? <p className="note" data-empty="deployments">Not deployed in any environment.</p> : groups.map((g) => (
        <div key={g.environment} data-environment={g.environment}>
          <h4>{g.name}</h4>
          <ul>{g.rows.map((r) => (
            <li key={r.id} data-instance={r.id}>
              {r.shown ? (
                <button className="link" onClick={() => showInstance(r.id)}>{r.nodes.map((n, i) => (<Fragment key={i}>{i > 0 && <> <span aria-hidden="true">›</span> </>}{n}</Fragment>))}</button>
              ) : (
                <span>{r.nodes.join(' › ')} <span className="desc">(in no deployment view)</span></span>
              )}
              {r.copies && <span className="tech"> ×{r.copies}</span>}
            </li>
          ))}</ul>
        </div>
      ))}
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
  const showInstance = useStore((s) => s.showInstance);
  const sheet = useStore((s) => s.sheet);
  const environments = useStore((s) => s.model?.deployment.environments);
  const setUi = useStore((s) => s.setUi);
  const phone = usePhone();

  const deployHeading = useRef<HTMLHeadingElement>(null);

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
  // A software system or container shows where it runs, when the workspace has deployment environments at all.
  const deployments = useMemo(
    () => (el && DEPLOYABLE_TYPES.has(el.type) && environments && environments.length > 0 ? deploymentsOf(m, el.id, environments) : null),
    [m, el, environments]);
  const reachable = deployments ? deployments.flatMap((g) => g.rows).filter((r) => r.shown) : [];
  /** Take the reader to the list of instances: the phone's peeking sheet grows to show it, the heading is scrolled to the top and focused (with a visible ring). */
  const showDeployments = () => {
    const reveal = () => { deployHeading.current?.scrollIntoView({ block: 'start' }); deployHeading.current?.focus(); };
    if (phone && sheet === 'peek') { setUi({ sheet: 'half' }); requestAnimationFrame(reveal); } else reveal();
  };

  return (
    <aside role="complementary" aria-label="Inspector" className="inspector">
      {el && rel ? (
        <div data-selected-id={el.id}>
          <h2 tabIndex={-1}>{el.name}</h2>
          <p className="type" data-field="type">{typeLabel(el.type)}{el.technology ? ` · ${el.technology}` : ''}{el.metadata ? ` · ${el.metadata}` : ''}</p>
          <div className="actions">
            {m.expandable.has(el.id) && path !== el.id && <button data-action="open" onClick={() => expand(el.id)}>Open</button>}
            {reachable.length === 1 && <button data-action="show-deployment" onClick={() => showInstance(reachable[0].id)}>Show deployment</button>}
            {reachable.length > 1 && <button data-action="show-deployment" onClick={showDeployments}>Deployments ({reachable.length})</button>}
            {view && !isCustom(el) && (!isDeployment(el) || el.instanceOf) && <button data-action="show-in-model" onClick={showInModel}>Show in model</button>}
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
          {deployments && <Deployments groups={deployments} headingRef={deployHeading} />}
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
