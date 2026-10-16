import { Handle, Position, useStore, type NodeProps } from '@xyflow/react';
import type { CSSProperties, ReactNode } from 'react';
import type { FlowNode } from './compose';
import type { LabelLine, SceneNode } from './types';
import { childFade, fitZoom, labelFade, phoneLayout, reducedMotion } from './zoomfx';

const MIN_TIER_PX = 6; // tiers whose effective size is below this are hidden
const NAME_FLOOR_PX = 9; // the name alone of a NOT expanded node is drawn at this size when everything is smaller (expanded frames never grow: they shrink and fade)

// Invisible handles on EVERY node: React Flow drops edges whose endpoints have none.
const hidden: CSSProperties = { opacity: 0, width: 1, height: 1, minWidth: 1, minHeight: 1, border: 0, pointerEvents: 'none', left: '50%', top: '50%' };
export const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={hidden} isConnectable={false} />
    <Handle type="source" position={Position.Right} style={hidden} isConnectable={false} />
  </>
);

/** What the label looks like at this zoom. Only changes (and re-renders) when a threshold is crossed. */
export function labelMode(lines: LabelLine[], base: number, K: number, zoom: number, allowFloor = true): string {
  const tiers: number[] = [];
  let floor = false;
  for (const l of lines) {
    const px = (l.size ?? base) * K * zoom;
    if (l.tier === 0) { if (allowFloor && px < NAME_FLOOR_PX) floor = true; } else if (px >= MIN_TIER_PX) tiers.push(l.tier);
  }
  // when floored, the font size depends on the zoom: include it (quantised to 1e-4) so the label re-renders
  return `${[...new Set(tiers)].sort().join('')}|${floor ? Math.round(zoom * 10000) : ''}`;
}

export function Lines({ lines, base, K, zoomKey, align, color, maxTier = 2, nameCap = null, fade = 1, frame = false }: { lines: LabelLine[]; base: number; K: number; zoomKey: string; align: 'center' | 'left'; color: string; maxTier?: number; nameCap?: number | null; fade?: number; frame?: boolean }) {
  const [tiers, floorZoom] = zoomKey.split('|');
  const floored = floorZoom !== '';
  const zoom = floored ? Number(floorZoom) / 10000 : 1;
  return (
    <div data-role={frame ? 'frame-label' : undefined} data-fade={frame ? fade : undefined} style={{ textAlign: align, color, lineHeight: 1.25, whiteSpace: 'pre', fontSize: base, opacity: fade === 1 ? undefined : fade }}>
      {lines.map((l, i) => {
        if (l.tier > maxTier || (l.tier !== 0 && !tiers.includes(String(l.tier)))) return null;
        let size = l.size ?? base;
        if (l.tier === 0 && floored) size = NAME_FLOOR_PX / (K * zoom);
        if (l.tier === 0 && nameCap !== null) size = Math.min(size, nameCap);
        return (
          <div key={i} data-tier={l.tier} style={{ fontSize: size, fontWeight: l.weight === 'bold' ? 700 : 400, fontStyle: l.italic ? 'italic' : 'normal' }}>{l.text}</div>
        );
      })}
    </div>
  );
}

function Shape({ n, expanded }: { n: SceneNode; expanded: boolean }) {
  const { w, h, shape, style: s } = n;
  const sw = s.strokeWidth ?? 1;
  const common = { fill: s.fill, stroke: s.stroke, strokeWidth: sw, fillOpacity: expanded ? 0.12 : 1, strokeDasharray: expanded ? '8 5' : undefined };
  const i = sw / 2;
  let body: ReactNode;
  if (shape === 'Cylinder') {
    const ry = Math.min(14, h / 6);
    body = (
      <>
        <path d={`M${i},${ry} A${w / 2 - i},${ry} 0 0 1 ${w - i},${ry} V${h - ry} A${w / 2 - i},${ry} 0 0 1 ${i},${h - ry} Z`} {...common} />
        <path d={`M${i},${ry} A${w / 2 - i},${ry} 0 0 0 ${w - i},${ry}`} fill="none" stroke={s.stroke} strokeWidth={sw} />
      </>
    );
  } else if (shape === 'Person') {
    const r = Math.min(w, h) * 0.17, cx = w / 2;
    body = (
      <>
        <rect x={i} y={r * 2 - 4} width={w - sw} height={h - r * 2 + 4 - i} rx={Math.min(18, w / 4)} {...common} />
        <circle cx={cx} cy={r + i} r={r} {...common} />
      </>
    );
  } else {
    body = <rect x={i} y={i} width={w - sw} height={h - sw} rx={shape === 'RoundedBox' ? 12 : 0} {...common} />;
  }
  return <svg width={w} height={h} style={{ position: 'absolute', inset: 0, overflow: 'visible' }}>{body}</svg>;
}

const useZoomKey = (lines: LabelLine[], base: number, K: number, allowFloor: boolean): string =>
  useStore((s) => labelMode(lines, base, K, s.transform[2], allowFloor));

function Badges({ d }: { d: FlowNode['data'] }) {
  return (
    <>
      {d.frameBadge && <span className="badge count" data-badge="count">{d.frameBadge}</span>}
      {d.matchBadge && <span className="badge matches" data-badge="matches">{d.matchBadge}</span>}
    </>
  );
}

function Box({ d, boundary }: { d: FlowNode['data']; boundary: boolean }) {
  const n = d.n;
  const zoomKey = useZoomKey(n.label.lines, n.style.fontSize, d.K, !d.expanded);
  // Expanded frames (the focused one and its ancestors): the name scales with the zoom like everything else and fades out between 12 and 6 px.
  const namePx = Math.min(n.label.lines.find((l) => l.tier === 0)?.size ?? n.style.fontSize, d.nameCap ?? Infinity) * d.K;
  const labelOpacity = useStore((s) => (d.expanded ? labelFade(namePx * s.transform[2], reducedMotion()) : 1));
  // Children of an expanded frame fade out as the zoom falls below the frame's fit zoom (it collapses at CHILD_FADE.gone).
  const kidsOpacity = useStore((s) => (d.owner ? childFade(s.transform[2] / fitZoom(d.owner.w, d.owner.h, s.width, s.height, phoneLayout(), s.maxZoom), reducedMotion()) : 1));
  const a = n.label.anchor;
  const personPad = n.shape === 'Person' ? Math.min(n.w, n.h) * 0.34 : 0;
  const color = d.expanded ? n.style.stroke : n.style.color;
  const cls = [boundary ? 'c4b' : 'c4el', d.hit ? 'hit' : '', d.selected ? 'sel' : '', d.expanded ? 'expanded' : '', d.matchBadge ? 'has-match' : ''].filter(Boolean).join(' ');
  const inner: CSSProperties = { position: 'absolute', left: 0, top: 0, width: n.w, height: n.h, transformOrigin: '0 0', transform: d.K === 1 ? undefined : `scale(${d.K})`, overflow: 'hidden' };
  const label = <Lines lines={n.label.lines} base={n.style.fontSize} K={d.K} zoomKey={zoomKey} align={boundary ? 'left' : 'center'} color={color}
    maxTier={d.expanded ? (d.focused ? 1 : 0) : 2} nameCap={d.nameCap} fade={labelOpacity} frame={d.expanded} />;
  return (
    <div className={cls} data-id={n.id} data-selected={d.selected ? 'true' : undefined} data-expanded={d.expanded ? 'true' : undefined} data-fresh={d.K !== 1 ? '' : undefined}
         style={{ width: n.w * d.K, height: n.h * d.K, opacity: d.opacity }}>
      <div className="fx" style={{ ...inner, overflow: 'visible', opacity: kidsOpacity === 1 ? undefined : kidsOpacity }}>
        {boundary ? (
          <div className="boundary-box" style={{ position: 'absolute', inset: 0, background: n.style.fill, border: `${n.style.strokeWidth ?? 1}px ${n.style.dash ? 'dashed' : 'solid'} ${n.style.stroke}` }} />
        ) : <Shape n={n} expanded={d.expanded} />}
        <div style={{ position: 'absolute', inset: 0, overflow: 'hidden' }}>
          {boundary || a === 'top-left' || a === 'bottom-left' ? (
            <div style={{ position: 'absolute', left: 8, [a === 'bottom-left' ? 'bottom' : 'top']: 6 }}>{label}</div>
          ) : a === 'top' ? (
            <div style={{ position: 'absolute', left: 0, right: 0, top: 10, display: 'flex', justifyContent: 'center' }}>{label}</div>
          ) : (
            <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: personPad }}>{label}</div>
          )}
        </div>
        <Badges d={d} />
      </div>
      <Handles />
    </div>
  );
}

export const C4Element = ({ data }: NodeProps<FlowNode>) => <Box d={data} boundary={false} />;
export const C4Boundary = ({ data }: NodeProps<FlowNode>) => <Box d={data} boundary />;
