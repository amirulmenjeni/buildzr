import { useEffect, useMemo, useState, useCallback } from 'react';
import { ReactFlow, ReactFlowProvider, MiniMap, Controls, useNodesInitialized, useReactFlow, useStore, type Node, type Edge } from '@xyflow/react';
import { C4Element, C4Boundary, type C4Node } from './nodes';
import { ElkEdge, type ElkEdgeT } from './edge';
import type { IndexEntry, Scene } from './scene';
import { allTags, buildHash, matchNodes, parseHash, type FilterState } from './filter';

const nodeTypes = { c4element: C4Element, c4boundary: C4Boundary };
const edgeTypes = { elk: ElkEdge };

declare global { interface Window { __spike: Spike } }
interface Spike { positions(): Record<string, { x: number; y: number; w: number; h: number }>; ready: boolean; metrics: Record<string, number>; setView?(v: string): void }
window.__spike = { positions: () => ({}), ready: false, metrics: {} };

function useHash() {
  const [h, setH] = useState(location.hash);
  useEffect(() => {
    const f = () => setH(location.hash);
    addEventListener('hashchange', f);
    return () => removeEventListener('hashchange', f);
  }, []);
  return h;
}

/** Scene coordinates are absolute; React Flow wants children relative to the parent. Parents precede children in the scene. */
function toFlow(scene: Scene, match: Set<string> | null) {
  const abs = new Map(scene.nodes.map((n) => [n.id, n]));
  const nodes: C4Node[] = scene.nodes.map((n) => {
    const p = n.parent ? abs.get(n.parent)! : null;
    const hit = match?.has(n.id) ?? false;
    return {
      id: n.id, type: n.role === 'boundary' ? 'c4boundary' : 'c4element',
      position: { x: n.x - (p?.x ?? 0), y: n.y - (p?.y ?? 0) },
      parentId: n.parent ?? undefined,
      width: n.w, height: n.h,
      draggable: false, connectable: false, selectable: true, focusable: true,
      data: { scene: n, hit, dim: match !== null && !hit },
    };
  });
  const edges: ElkEdgeT[] = scene.edges.map((e) => ({
    id: e.id, source: e.source, target: e.target, type: 'elk',
    // Edges are rendered in their own layer; give them a z-index above every node (see RESULT.md).
    zIndex: new URLSearchParams(location.search).has('nozindex') ? undefined : 1000, // ?nozindex=1: z-order experiment
    selectable: false, focusable: false,
    data: { scene: e, dim: match !== null && !(match.has(e.source) && match.has(e.target)) },
  }));
  return { nodes: nodes as Node[], edges: edges as Edge[] };
}

function Probe({ scene }: { scene: Scene }) {
  // useNodesInitialized() was not reliable on its own in my first run (ready never fired, cause not found); derive readiness from the lookup and record the hook value in metrics.
  const hookInit = useNodesInitialized();
  const init = useStore((st) => st.nodeLookup.size > 0 && [...st.nodeLookup.values()].every((n) => !!n.internals.handleBounds && !!n.measured.width));
  window.__spike.metrics.hookInitialized = hookInit ? 1 : 0;
  const rf = useReactFlow();
  const lookup = useStore((s) => s.nodeLookup);
  useEffect(() => {
    window.__spike.positions = () => {
      const o: Record<string, { x: number; y: number; w: number; h: number }> = {};
      for (const [id, n] of lookup) {
        const a = n.internals.positionAbsolute;
        o[id] = { x: a.x, y: a.y, w: n.measured.width ?? n.width ?? 0, h: n.measured.height ?? n.height ?? 0 };
      }
      return o;
    };
  }, [lookup]);
  useEffect(() => {
    if (init && !window.__spike.ready) {
      rf.fitView({ duration: 0 });
      window.__spike.metrics.initializedAtMs = performance.now();
      window.__spike.metrics.nodes = scene.nodes.length;
      window.__spike.metrics.edges = scene.edges.length;
      requestAnimationFrame(() => requestAnimationFrame(() => {
        window.__spike.metrics.firstPaintAfterInitMs = performance.now();
        window.__spike.ready = true;
      }));
    }
  }, [init, rf, scene]);
  return null;
}

function Viewer({ scene, f }: { scene: Scene; f: FilterState }) {
  const match = useMemo(() => matchNodes(scene, f), [scene, f]);
  const { nodes, edges } = useMemo(() => toFlow(scene, match), [scene, match]);
  return (
    <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
      nodesDraggable={false} nodesConnectable={false} elementsSelectable fitView minZoom={0.05} maxZoom={4}
      onlyRenderVisibleElements={false}>
      <MiniMap pannable zoomable />
      <Controls showInteractive={false} />
      <Probe scene={scene} />
    </ReactFlow>
  );
}

export function App() {
  const hash = useHash();
  const [index, setIndex] = useState<IndexEntry[]>([]);
  const [scene, setScene] = useState<Scene | null>(null);
  const { view: hv, f } = parseHash(hash);
  const view = hv ?? index[0]?.view ?? null;

  useEffect(() => { fetch('scenes/index.json').then((r) => r.json()).then(setIndex); }, []);
  useEffect(() => {
    const e = index.find((x) => x.view === view);
    if (!e) return;
    setScene(null);
    window.__spike.ready = false;
    fetch('scenes/' + e.file).then((r) => r.json()).then(setScene);
  }, [index, view]);

  const set = useCallback((nf: FilterState) => { if (view) location.hash = buildHash(view, nf); }, [view]);
  const tags = useMemo(() => (scene ? allTags(scene) : []), [scene]);
  const fkey = f.q + '|' + f.tags.join(',') + '|' + f.mode;
  const stable = useMemo(() => f, [fkey]); // eslint-disable-line react-hooks/exhaustive-deps

  return (
    <div style={{ width: '100%', height: '100%' }}>
      <div className="toolbar">
        <select aria-label="view" value={view ?? ''} onChange={(e) => (location.hash = buildHash(e.target.value, { q: '', tags: [], mode: 'or' }))}>
          {index.map((x) => <option key={x.view} value={x.view}>{x.title} ({x.view})</option>)}
        </select>
        <input type="text" aria-label="search" placeholder="Search name, id, type, tech, description, tags" value={f.q} onChange={(e) => set({ ...f, q: e.target.value })} />
        <label>
          <select aria-label="mode" value={f.mode} onChange={(e) => set({ ...f, mode: e.target.value as 'and' | 'or' })}>
            <option value="or">tags: OR</option><option value="and">tags: AND</option>
          </select>
        </label>
        <span className="chips" style={{ display: 'flex', gap: 4, flexWrap: 'wrap' }}>
          {tags.map((t) => (
            <button key={t} className={'chip' + (f.tags.includes(t) ? ' on' : '')} data-tag={t}
              onClick={() => set({ ...f, tags: f.tags.includes(t) ? f.tags.filter((x) => x !== t) : [...f.tags, t] })}>{t}</button>
          ))}
        </span>
      </div>
      {scene && (
        <ReactFlowProvider key={scene.view}>
          <Viewer scene={scene} f={stable} />
        </ReactFlowProvider>
      )}
    </div>
  );
}
