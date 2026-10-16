import { Handle, Position, type NodeProps, type Node } from '@xyflow/react';
import type { SceneNode } from './scene';

export type C4Data = { scene: SceneNode; dim: boolean; hit: boolean } & Record<string, unknown>;
export type C4Node = Node<C4Data>;

const hidden: React.CSSProperties = { opacity: 0, width: 1, height: 1, minWidth: 1, minHeight: 1, border: 0, pointerEvents: 'none', left: '50%', top: '50%' };
const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={hidden} isConnectable={false} />
    <Handle type="source" position={Position.Right} style={hidden} isConnectable={false} />
  </>
);

function Lines({ n, align }: { n: SceneNode; align: 'center' | 'left' }) {
  return (
    <div style={{ textAlign: align, color: n.style.color, lineHeight: 1.25, whiteSpace: 'pre', fontSize: n.style.fontSize }}>
      {n.label.lines.map((l, i) => (
        <div key={i} style={{ fontSize: l.size ?? n.style.fontSize, fontWeight: l.weight === 'bold' ? 700 : 400, fontStyle: l.italic ? 'italic' : 'normal' }}>{l.text}</div>
      ))}
    </div>
  );
}

function Shape({ n }: { n: SceneNode }) {
  const { w, h, shape, style: s } = n;
  const sw = s.strokeWidth ?? 1;
  const common = { fill: s.fill, stroke: s.stroke, strokeWidth: sw };
  const i = sw / 2;
  let body: React.ReactNode;
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

export function C4Element({ data }: NodeProps<C4Node>) {
  const n = data.scene;
  const personPad = n.shape === 'Person' ? Math.min(n.w, n.h) * 0.34 : 0;
  return (
    <div className={'c4el' + (data.hit ? ' hit' : '')} data-id={n.id}
         style={{ width: n.w, height: n.h, opacity: data.dim ? 0.15 : (n.style.opacity ?? 1) }}>
      <Shape n={n} />
      <div style={{ position: 'absolute', inset: 0, display: 'flex', alignItems: 'center', justifyContent: 'center', paddingTop: personPad }}>
        <Lines n={n} align="center" />
      </div>
      <Handles />
    </div>
  );
}

export function C4Boundary({ data }: NodeProps<C4Node>) {
  const n = data.scene;
  const top = n.label.anchor === 'top-left';
  return (
    <div className={'c4b' + (data.hit ? ' hit' : '')} data-id={n.id}
         style={{ width: n.w, height: n.h, opacity: data.dim ? 0.15 : (n.style.opacity ?? 1),
                  background: n.style.fill, border: `${n.style.strokeWidth ?? 1}px ${n.style.dash ? 'dashed' : 'solid'} ${n.style.stroke}` }}>
      <div style={{ position: 'absolute', left: 8, [top ? 'top' : 'bottom']: 6 }}>
        <Lines n={n} align="left" />
      </div>
      <Handles />
    </div>
  );
}
