import { BaseEdge, EdgeLabelRenderer, type EdgeProps, type Edge } from '@xyflow/react';
import type { SceneEdge } from './scene';

export type ElkData = { scene: SceneEdge; dim: boolean } & Record<string, unknown>;
export type ElkEdgeT = Edge<ElkData>;

/** Orthogonal polyline with rounded corners; the last segment stops short by the arrow length. */
export function pathFor(pts: [number, number][], r = 6): string {
  let d = `M${pts[0][0]},${pts[0][1]}`;
  for (let i = 1; i < pts.length - 1; i++) {
    const [px, py] = pts[i - 1], [cx, cy] = pts[i], [nx, ny] = pts[i + 1];
    const l1 = Math.hypot(cx - px, cy - py), l2 = Math.hypot(nx - cx, ny - cy);
    const rr = Math.min(r, l1 / 2, l2 / 2);
    const ax = cx - ((cx - px) / l1) * rr, ay = cy - ((cy - py) / l1) * rr;
    const bx = cx + ((nx - cx) / l2) * rr, by = cy + ((ny - cy) / l2) * rr;
    d += ` L${ax},${ay} Q${cx},${cy} ${bx},${by}`;
  }
  const last = pts[pts.length - 1];
  return d + ` L${last[0]},${last[1]}`;
}

export function ElkEdge({ id, data }: EdgeProps<ElkEdgeT>) {
  const e = data!.scene;
  const s = e.style;
  const color = s.stroke;
  const mEnd = s.arrow === 'end' || s.arrow === 'both';
  const mStart = s.arrow === 'start' || s.arrow === 'both';
  const mid = `m-${id}`;
  return (
    <>
      <defs>
        <marker id={`${mid}-e`} viewBox="0 0 10 10" refX="9" refY="5" markerWidth="8" markerHeight="8" orient="auto-start-reverse" markerUnits="userSpaceOnUse">
          <path d="M0,0 L10,5 L0,10 Z" fill={color} />
        </marker>
      </defs>
      <BaseEdge id={id} path={pathFor(e.points)} interactionWidth={0}
        markerEnd={mEnd ? `url(#${mid}-e)` : undefined} markerStart={mStart ? `url(#${mid}-e)` : undefined}
        style={{ stroke: color, strokeWidth: s.width ?? 1.5, strokeDasharray: s.dash?.join(' '), fill: 'none', opacity: data!.dim ? 0.15 : (s.opacity ?? 1) }} />
      {e.label && (
        <EdgeLabelRenderer>
          <div className="edge-label" data-edge={e.id}
               style={{ position: 'absolute', transform: `translate(${e.label.x}px,${e.label.y}px)`, width: e.label.w, height: e.label.h,
                        color: s.color ?? color, textAlign: 'center', opacity: data!.dim ? 0.15 : 1, zIndex: 2000 }}>
            {e.label.lines.map((l, i) => (
              <div key={i} style={{ fontSize: l.size ?? s.fontSize ?? 12, fontWeight: l.weight === 'bold' ? 700 : 400, whiteSpace: 'pre', lineHeight: 1.25 }}>{l.text}</div>
            ))}
          </div>
        </EdgeLabelRenderer>
      )}
    </>
  );
}
