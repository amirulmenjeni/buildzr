import { BaseEdge, EdgeLabelRenderer, useStore, type EdgeProps } from '@xyflow/react';
import type { FlowEdge } from './compose';
import { labelMode } from './nodes';
import { useStore as useViewer } from './store';
import { edgeColors } from './theme';
import { childFade, fitZoom, phoneLayout, reducedMotion } from './zoomfx';

/** Orthogonal polyline with rounded corners (absolute points). */
export function pathFor(pts: [number, number][], r = 6): string {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1], [cx, cy] = pts[i], [nx, ny] = pts[i + 1];
    const l1 = Math.hypot(cx - px, cy - py), l2 = Math.hypot(nx - cx, ny - cy);
    const rr = Math.min(r, l1 / 2, l2 / 2);
    if (l1 === 0 || l2 === 0) continue;
    const ax = cx - ((cx - px) / l1) * rr, ay = cy - ((cy - py) / l1) * rr;
    const bx = cx + ((nx - cx) / l2) * rr, by = cy + ((ny - cy) / l2) * rr;
    d += ` L${ax},${ay} Q${cx},${cy} ${bx},${by}`;
  }
  const last = pts[pts.length - 1];
  return d + ` L${last[0]},${last[1]}`;
}


export function ElkEdge({ id, data }: EdgeProps<FlowEdge>) {
  const d = data!;
  const e = d.e;
  const s = e.style;
  const theme = useViewer((st) => st.theme);
  const ec = edgeColors(s.stroke, s.color, theme); // line 3:1 against the canvas, label text 4.5:1 against its box
  const color = ec.stroke;
  const mEnd = (s.arrow === 'end' || s.arrow === 'both') && !d.noEnd;
  const mStart = (s.arrow === 'start' || s.arrow === 'both') && !d.noStart;
  const mid = `m-${id.replace(/[^a-zA-Z0-9_-]/g, '_')}`;
  const width = (s.width ?? 1.5) * d.K * (d.selected ? 1.8 : 1) + (e.count > 1 ? 0.5 * d.K : 0);
  const zoomKey = useStore((st) => (e.label ? labelMode(e.label.lines, s.fontSize ?? 12, d.K, st.transform[2]) : ''));
  const tiers = zoomKey.split('|')[0];
  const kids = useStore((st) => (d.owner ? childFade(st.transform[2] / fitZoom(d.owner.w, d.owner.h, st.width, st.height, phoneLayout(), st.maxZoom), reducedMotion()) : 1));
  const arrow = 8 * d.K;
  return (
    <g data-edge={e.id} data-count={e.count} data-selected={d.selected ? 'true' : undefined} className="rolled-edge" style={{ opacity: d.opacity * kids }}>
      <defs>
        <marker id={`${mid}-e`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth={arrow} markerHeight={arrow} orient="auto-start-reverse" markerUnits="userSpaceOnUse">
          <path d="M0,0 L10,5 L0,10 Z" fill={color} />
        </marker>
      </defs>
      <BaseEdge id={id} path={pathFor(d.pts, 6 * d.K)} interactionWidth={14}
        markerEnd={mEnd ? `url(#${mid}-e)` : undefined} markerStart={mStart ? `url(#${mid}-e)` : undefined}
        style={{ stroke: color, strokeWidth: width, strokeDasharray: s.dash?.map((x) => x * d.K).join(' '), fill: 'none' }} />
      {e.label && d.opacity >= 0.9 && ( // faded labels are dropped: they could not meet contrast anyway
        <EdgeLabelRenderer>
          <div className="edge-label" aria-hidden="true" data-edge={e.id}
               style={{ position: 'absolute', transform: `translate(${d.labelPos[0]}px,${d.labelPos[1]}px)`, width: e.label.w * d.K, height: e.label.h * d.K,
                        color: ec.label, textAlign: 'center', opacity: d.opacity * kids, zIndex: 2000, transformOrigin: '0 0' }}>
            <div style={{ transform: d.K === 1 ? undefined : `scale(${d.K})`, transformOrigin: '0 0', width: e.label.w }}>
              {e.label.lines.map((l, i) => (l.tier !== 0 && !tiers.includes(String(l.tier)) ? null : (
                <div key={i} style={{ fontSize: l.size ?? s.fontSize ?? 12, fontWeight: l.weight === 'bold' ? 700 : 400, whiteSpace: 'pre', lineHeight: 1.25 }}>{l.text}</div>
              )))}
            </div>
          </div>
        </EdgeLabelRenderer>
      )}
    </g>
  );
}
