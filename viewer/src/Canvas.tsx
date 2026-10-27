import { useEffect, useMemo, useRef } from 'react';
import { Controls, ReactFlow, ReactFlowProvider, useReactFlow, useStoreApi, useStore as useFlowStore, type NodeMouseHandler, type EdgeMouseHandler } from '@xyflow/react';
import { compose, pathRect, type Composed, type FlowEdge, type FlowNode } from './compose';
import { ElkEdge } from './edge';
import { useDiagram } from './exportsource';
import { chainOf, computeMatches, type ModelIndex } from './model';
import { C4Boundary, C4Element } from './nodes';
import { defaults, type SettingValues } from './settings';
import { MODE, useStore } from './store';
import { follow, unionBox, type Box, type Viewport } from './steps';
import { usePhone } from './usePhone';
import { EXPAND, fitZoom, shouldCollapse, shouldExpand } from './zoomfx';

const nodeTypes = { c4element: C4Element, c4boundary: C4Boundary };
const edgeTypes = { elk: ElkEdge };

declare global {
  interface Window {
    __viewer: {
      positions(): Record<string, { x: number; y: number; w: number; h: number }>;
      viewport(): { x: number; y: number; zoom: number };
      setViewport(v: { x: number; y: number; zoom: number }): void;
      ready: boolean;
      cameraDone: number;
      readonly settings: SettingValues; // the current settings (read-only view of the store)
      readonly embed: boolean; // embed mode (?embed=1)
      readonly theme: 'light' | 'dark'; // the resolved theme
      autoCollapse: boolean; // test hook: false pauses the zoom-out collapse (tests that restore an old viewport on purpose)
      stepMs: number; // how long Play shows each step of a dynamic view (a test hook shortens it)
      stepCamera: { seq: number; step: number; moved: boolean; to: Viewport | null; duration: number; free: Box | null; done: boolean }; // the last step's camera move (StepCamera)
    };
  }
}
window.__viewer = { positions: () => ({}), viewport: () => ({ x: 0, y: 0, zoom: 1 }), setViewport: () => {}, ready: false, cameraDone: 0, autoCollapse: true, stepMs: 2000, stepCamera: { seq: 0, step: 0, moved: false, to: null, duration: 0, free: null, done: true }, settings: defaults(), embed: MODE.embed, theme: 'light' };
Object.defineProperty(window.__viewer, 'settings', { get: () => useStore.getState().settings });
Object.defineProperty(window.__viewer, 'theme', { get: () => useStore.getState().theme });

const reduced = (): boolean => matchMedia('(prefers-reduced-motion: reduce)').matches;
const phone = (): boolean => matchMedia('(max-width: 767px)').matches;
/** A tap selects (the sheet's Open expands) in the phone layout; an embedded frame narrower than 768 px used with a mouse keeps click-to-expand. */
const isPhone = (): boolean => phone() && !(MODE.embed && matchMedia('(pointer: fine)').matches);

function Camera({ composed }: { composed: Composed }) {
  const rf = useReactFlow();
  const flowStore = useStoreApi();
  const camera = useStore((s) => s.camera);
  const path = useStore((s) => s.path);
  const m = useStore((s) => s.m)!;
  const done = useRef(-1);
  const lookup = useFlowStore((s) => s.nodeLookup);
  const initialized = useFlowStore((s) => s.nodeLookup.size > 0 && [...s.nodeLookup.values()].every((n) => !!n.internals.handleBounds && !!n.measured.width));
  const timer = useRef<number>(0);

  useEffect(() => {
    window.__viewer.positions = () => {
      const o: Record<string, { x: number; y: number; w: number; h: number }> = {};
      for (const [id, n] of lookup) {
        const a = n.internals.positionAbsolute;
        o[id] = { x: a.x, y: a.y, w: n.measured.width ?? n.width ?? 0, h: n.measured.height ?? n.height ?? 0 };
      }
      return o;
    };
    window.__viewer.viewport = () => rf.getViewport();
    window.__viewer.setViewport = (v) => { void rf.setViewport(v, { duration: 0 }); };
  }, [lookup, rf]);

  useEffect(() => {
    if (!composed.complete || !initialized || camera.seq === done.current) return;
    done.current = camera.seq;
    const dur = reduced() ? 0 : 400;
    window.__viewer.ready = false;
    let target = composed.bounds;
    if (camera.kind === 'path') target = pathRect(composed, path, m);
    else if (camera.id && composed.rects.has(camera.id)) target = composed.rects.get(camera.id)!;
    const { width, height } = flowStore.getState();
    const fit = camera.kind !== 'node';
    const maxZoom = fit ? Math.max(2, 2 / composed.minScale) : Math.max(rf.getZoom(), 0.001);
    const zoom = fit ? fitZoom(target.w, target.h, width, height, phone(), maxZoom)
      : Math.min(maxZoom, Math.max(0.01, Math.min((0.5 * width) / target.w, (0.5 * height) / target.h)));
    const vp = { zoom, x: width / 2 - (target.x + target.w / 2) * zoom, y: height / 2 - (target.y + target.h / 2) * zoom };
    void rf.setViewport(vp, { duration: dur });
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => { window.__viewer.ready = true; window.__viewer.cameraDone = camera.seq; }, dur + 30);
  }, [composed, initialized, camera, path, m, rf, flowStore]);
  return null;
}

/** The part of the canvas (canvas px) that the step bar and the phone's inspector sheet leave free. */
function freeRect(canvas: HTMLElement): Box {
  const r = canvas.getBoundingClientRect();
  let top = 0, bottom = r.height;
  const bar = document.querySelector('[data-testid=steps]')?.getBoundingClientRect();
  if (bar && bar.height > 0 && bar.bottom > r.top) top = Math.max(top, bar.bottom - r.top);
  const sheet = document.querySelector('.sheet-wrap[data-sheet]:not([data-sheet=closed])')?.getBoundingClientRect(); // the phone's bottom sheet
  if (sheet && sheet.height > 0 && sheet.top < r.bottom) bottom = Math.min(bottom, sheet.top - r.top);
  return { x: 0, y: top, w: r.width, h: Math.max(1, bottom - top) };
}

/**
 * Stepping through a dynamic view brings the current step into view: its arrows with their labels and the boxes at both ends,
 * in the part of the canvas no overlay covers (freeRect). A step already in view does not move the camera; otherwise it is
 * centred at the current zoom, zoomed out only as far as it needs to fit, never in (steps.ts: follow). Only a change of step
 * moves the camera, so the user can pan and zoom freely between steps. Step 0 is the default fit again (store: setStep).
 */
function StepCamera({ composed }: { composed: Composed }) {
  const rf = useReactFlow();
  const flowStore = useStoreApi();
  const step = useStore((s) => s.step);
  const latest = useRef(composed);
  latest.current = composed;
  const timer = useRef<number>(0);
  useEffect(() => {
    const dom = flowStore.getState().domNode;
    if (!step || !dom) return;
    const c = latest.current;
    const boxes: Box[] = [];
    for (const e of c.edges) {
      const d = e.data!;
      if (d.step !== 'current') continue;
      for (const [x, y] of d.pts) boxes.push({ x, y, w: 0, h: 0 });
      if (d.e.label) boxes.push({ x: d.labelPos[0], y: d.labelPos[1], w: d.e.label.w * d.K, h: d.e.label.h * d.K });
      for (const end of [e.source, e.target]) {
        const n = c.nodes.find((x) => x.id === end);
        if (n && !n.data.expanded) boxes.push(c.rects.get(end)!); // an expanded frame is around the step, not part of it
      }
    }
    const target = unionBox(boxes);
    if (!target) return;
    const free = freeRect(dom);
    const to = follow(target, rf.getViewport(), free);
    const duration = to && !reduced() ? 300 : 0;
    const seq = window.__viewer.stepCamera.seq + 1;
    window.__viewer.stepCamera = { seq, step, moved: !!to, to, duration, free, done: !to };
    window.clearTimeout(timer.current);
    if (!to) return;
    void rf.setViewport(to, { duration });
    timer.current = window.setTimeout(() => { if (window.__viewer.stepCamera.seq === seq) window.__viewer.stepCamera.done = true; }, duration + 30);
  }, [step, rf, flowStore]);
  return null;
}

/**
 * Zooming out collapses: when the deepest expanded frame is drawn at less than half its fit zoom it goes back to collapsed,
 * the same state change as Back (path, hash, tree, selection), but the camera is left alone. A big jump collapses every
 * frame that qualifies, in one step. Zooming back in never expands anything. The rule is a pure function of the zoom
 * (no state besides the path), so the camera cannot make it flicker. It is paused while a camera request is still being
 * served (an expand animates up from a small zoom) and while the scenes are loading.
 */
function ZoomCollapse({ composed, m }: { composed: Composed; m: ModelIndex }) {
  const flowStore = useStoreApi();
  const zoom = useFlowStore((s) => s.transform[2]);
  const latest = useRef({ composed, m });
  latest.current = { composed, m };
  useEffect(() => {
    const { composed: c, m: model } = latest.current;
    const st = useStore.getState();
    if (!window.__viewer.autoCollapse || st.view || !st.path || !c.complete || window.__viewer.cameraDone !== st.camera.seq) return;
    const { width, height, maxZoom } = flowStore.getState();
    const phoneNow = phone();
    const chain = chainOf(model, st.path);
    let to = st.path;
    while (to) {
      const r = c.rects.get(to);
      if (!r || !shouldCollapse(zoom / fitZoom(r.w, r.h, width, height, phoneNow, maxZoom))) break;
      to = model.byId.get(to)?.parent ?? '';
      while (to && !chain.includes(to)) to = model.byId.get(to)?.parent ?? '';
    }
    if (to !== st.path) st.zoomCollapse(to);
  }, [zoom, flowStore]);
  return null;
}

/**
 * Zooming in expands (setting `zoomExpand`, default off): a collapsed frame of the current scene whose box contains the viewport
 * centre expands when it is drawn at EXPAND.at x its fit zoom, one level per step (the next level is judged after the new scene is
 * drawn). Its scene is prefetched from EXPAND.prefetch x. It only acts while the zoom is increasing, so Back, a collapse, fit view
 * or a camera move never expand anything, and it is paused under the same conditions as the collapse. Collapse is below
 * CHILD_FADE.gone, so between the two thresholds nothing changes and a wiggle around either causes at most one change.
 */
function ZoomExpand({ composed, m }: { composed: Composed; m: ModelIndex }) {
  const flowStore = useStoreApi();
  const zoom = useFlowStore((s) => s.transform[2]);
  const last = useRef(zoom);
  const latest = useRef({ composed, m });
  latest.current = { composed, m };
  useEffect(() => {
    const before = last.current;
    last.current = zoom;
    const { composed: c, m: model } = latest.current;
    const st = useStore.getState();
    if (!st.settings.zoomExpand || !window.__viewer.autoCollapse || st.view || !c.complete || window.__viewer.cameraDone !== st.camera.seq) return;
    const { width, height, maxZoom, transform } = flowStore.getState();
    const cx = (width / 2 - transform[0]) / zoom, cy = (height / 2 - transform[1]) / zoom;
    const phoneNow = phone();
    for (const node of c.nodes) {
      const d = node.data;
      if (!d.n.frame || d.expanded || !model.expandable.has(node.id) || (model.byId.get(node.id)?.parent ?? '') !== st.path) continue;
      const r = c.rects.get(node.id);
      if (!r || cx < r.x || cx > r.x + r.w || cy < r.y || cy > r.y + r.h) continue;
      const ratio = zoom / fitZoom(r.w, r.h, width, height, phoneNow, maxZoom);
      if (ratio >= EXPAND.prefetch) st.prefetch(node.id);
      if (zoom > before && shouldExpand(ratio)) st.zoomExpand(node.id);
      break; // frames do not overlap: only one can hold the centre
    }
  }, [zoom, flowStore]);
  return null;
}

function Flow() {
  const m = useStore((s) => s.m)!;
  const scenes = useStore((s) => s.scenes);
  const path = useStore((s) => s.path);
  const view = useStore((s) => s.view);
  const selection = useStore((s) => s.selection);
  const filter = useStore((s) => s.filter);
  const select = useStore((s) => s.select);
  const expand = useStore((s) => s.expand);
  const collapse = useStore((s) => s.collapse);
  const theme = useStore((s) => s.theme);
  const step = useStore((s) => s.step);
  const phoneNow = usePhone();
  const match = useMemo(() => computeMatches(m, filter), [m, filter]);
  const composed = useMemo(() => compose({ m, scenes, path, view, selection, match, step }), [m, scenes, path, view, selection, match, step]);

  // The export menu in the header draws what is on screen
  useEffect(() => { useDiagram.setState({ composed }); return () => useDiagram.setState({ composed: null }); }, [composed]);

  // Clicking a collapsed frame expands it in place (and selects it, so the inspector shows it); anything else just selects.
  const onNodeClick: NodeMouseHandler<FlowNode> = (_, node) => {
    const d = node.data;
    if (isPhone()) select(node.id, { zoom: d.K < 1 }); // phone: a tap selects (peek sheet); "Open" in the sheet expands
    else if (d.n.frame && !d.expanded && m.expandable.has(node.id)) expand(node.id);
    else select(node.id);
  };
  const onEdgeClick: EdgeMouseHandler<FlowEdge> = (_, edge) => select(edge.data!.e.id);
  const logo = useStore((s) => (s.branding?.logo ? s.branding.images?.[s.branding.logo] ?? null : null));
  const workspaceName = useStore((s) => s.model?.workspace.name ?? '');

  return (
    <div className="canvas" data-testid="canvas" onKeyDown={(ev) => {
      if (ev.key === 'Escape' && MODE.embed && useStore.getState().inspectorOpen) return; // Esc closes the inspector first (App)
      if (ev.key === 'Escape' && path && !view) { collapse(); return; }
      const nodeEl = (ev.target as HTMLElement).closest<HTMLElement>('.react-flow__node');
      if (ev.key === 'Enter' && nodeEl?.dataset.id) { ev.preventDefault(); expand(nodeEl.dataset.id); }
    }}>
      <ReactFlow<FlowNode, FlowEdge> nodes={composed.nodes} edges={composed.edges} nodeTypes={nodeTypes} edgeTypes={edgeTypes}
        nodesDraggable={false} nodesConnectable={false} elementsSelectable minZoom={0.01} maxZoom={Math.max(2, 2 / composed.minScale)}
        defaultViewport={{ x: 0, y: 0, zoom: 1 }} onlyRenderVisibleElements={false} colorMode={theme}
        onNodeClick={onNodeClick} onEdgeClick={onEdgeClick}
        onPaneClick={() => select(null)} deleteKeyCode={null} selectionKeyCode={null} multiSelectionKeyCode={null}>
        {!phoneNow && <Controls showInteractive={false} />}
        <Camera composed={composed} />
        <StepCamera composed={composed} />
        <ZoomCollapse composed={composed} m={m} />
        <ZoomExpand composed={composed} m={m} />
      </ReactFlow>
      {logo && <img className="brand-logo" data-testid="brand-logo" src={logo} alt={`${workspaceName} logo`} draggable={false}
                    onError={(ev) => { ev.currentTarget.style.display = 'none'; console.warn('buildzr: the branding logo could not be drawn (its image data is damaged)'); }} />}
    </div>
  );
}

export function Canvas() {
  const ready = useStore((s) => s.status === 'ready');
  return ready ? <ReactFlowProvider><Flow /></ReactFlowProvider> : null;
}
