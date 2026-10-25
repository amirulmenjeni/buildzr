import { Handle, Position, useStore, type NodeProps } from '@xyflow/react';
import { useMemo, type CSSProperties, type ReactNode, type SyntheticEvent } from 'react';
import { fitScale } from './branding';
import type { FlowNode } from './compose';
import type { LabelLine, SceneNode } from './types';
import { measureEm } from './textwidth';
import { useStore as useViewer } from './store';
import { nodeColors, type NodeColors } from './theme';
import { childFade, fitFade, fitZoom, labelFade, NAME_FIT, NAME_FLOOR_PX, phoneLayout, reducedMotion } from './zoomfx';

const MIN_TIER_PX = 6; // tiers whose effective size is below this are hidden

// Invisible handles on EVERY node: React Flow drops edges whose endpoints have none.
const hidden: CSSProperties = { opacity: 0, width: 1, height: 1, minWidth: 1, minHeight: 1, border: 0, pointerEvents: 'none', left: '50%', top: '50%' };
export const Handles = () => (
  <>
    <Handle type="target" position={Position.Left} style={hidden} isConnectable={false} />
    <Handle type="source" position={Position.Right} style={hidden} isConnectable={false} />
  </>
);

/**
 * The cap on a frame's name (local px) at this zoom: twice its child frames' names on screen, and a child's name is at least the
 * floor (it is drawn at 9 px at the smallest), so the cap never goes below twice the floor. Without that, a frame whose children
 * are floored would shrink below the floor and jump back up to it when it collapses.
 */
export const capSize = (nameCap: number | null, K: number, zoom: number): number =>
  nameCap === null ? Infinity : Math.max(nameCap, (2 * NAME_FLOOR_PX) / (K * zoom));

/** What the label looks like at this zoom. Only changes (and re-renders) when a threshold is crossed. */
export function labelMode(lines: LabelLine[], base: number, K: number, zoom: number, allowFloor = true, nameCap: number | null = null): string {
  const tiers: number[] = [];
  let floor = false;
  for (const l of lines) {
    const px = (l.tier === 0 ? Math.min(l.size ?? base, capSize(nameCap, K, zoom)) : l.size ?? base) * K * zoom;
    if (l.tier === 0) { if (allowFloor && px < NAME_FLOOR_PX) floor = true; } else if (px >= MIN_TIER_PX) tiers.push(l.tier);
  }
  // when floored, or when the cap is held up by the floor, the font size depends on the zoom: include it (6 significant digits) so the label re-renders
  const capHeld = nameCap !== null && (2 * NAME_FLOOR_PX) / (K * zoom) > nameCap;
  return `${[...new Set(tiers)].sort().join('')}|${floor || capHeld ? zoom.toPrecision(6) : ''}|${floor ? 'f' : ''}`;
}

/**
 * Opacity of the (floored) name of a leaf node or collapsed frame: 1 while the text at its on-screen size fits in the box, then a ramp
 * down to 0 (zoomfx NAME_FIT). The widths come from the font's metrics (textwidth.ts) because the scene carries only the wrapped lines.
 * `offset` = distance from the box's left edge to the text of a left-aligned label (scene px).
 */
export function nameFit(lines: LabelLine[], base: number, K: number, nameCap: number | null, boxW: number, offset: number, zoom: number,
                        family: string | null = null, fit = 1): number {
  let widest = 0;
  for (const l of lines) {
    if (l.tier !== 0) continue;
    const px = Math.max(Math.min(l.size ?? base, nameCap ?? Infinity) * fit * K * zoom, NAME_FLOOR_PX);
    widest = Math.max(widest, measureEm(l.text, l.weight === 'bold', !!l.italic, family ?? undefined) * px);
  }
  const inner = NAME_FIT.inner * boxW * zoom * K - offset * K * zoom;
  return widest === 0 ? 1 : fitFade(inner > 0 ? widest / inner : Infinity, reducedMotion());
}

/** A node's icon: `block` above the label of a leaf box (the layout left room for it), `inline` before the name of a frame, a boundary or a person. */
export interface NodeIcon { src: string; mode: 'block' | 'inline' }
/** Sizes in scene px, as buildzr/site/fonts reserves them (ICON, ICON_GAP, icon_inline_w). */
export const ICON_PX = 40, ICON_GAP_PX = 6, ICON_INLINE_GAP_PX = 4;
const hideBroken = (ev: SyntheticEvent<HTMLImageElement>): void => {
  ev.currentTarget.style.display = 'none'; // the box is drawn without it
  console.warn('buildzr: an icon of this workspace could not be drawn (its image data is damaged); the box is shown without it');
};

export function Lines({ lines, base, K, zoomKey, align, color, maxTier = 2, nameCap = null, fade = 1, frame = false, nameFade = 1, fit = 1, icon = null }: { lines: LabelLine[]; base: number; K: number; zoomKey: string; align: 'center' | 'left'; color: string; maxTier?: number; nameCap?: number | null; fade?: number; frame?: boolean; nameFade?: number; fit?: number; icon?: NodeIcon | null }) {
  const [tiers, zoomPart, flag] = zoomKey.split('|');
  const floored = flag === 'f';
  const zoom = zoomPart !== '' ? Number(zoomPart) : 1; // only present when a size depends on the zoom (floor, or a cap held up by the floor)
  let inlineDone = false;
  return (
    <div data-role={frame ? 'frame-label' : undefined} data-fade={frame ? fade : undefined} data-fit={fit === 1 ? undefined : fit} style={{ textAlign: align, color, lineHeight: 1.25, whiteSpace: 'pre', fontSize: base * fit, opacity: fade === 1 ? undefined : fade }}>
      {icon?.mode === 'block' && (
        <img data-role="icon" src={icon.src} alt="" aria-hidden="true" draggable={false} onError={hideBroken}
             style={{ display: 'block', width: ICON_PX, height: ICON_PX, margin: `0 auto ${ICON_GAP_PX}px`, objectFit: 'contain', opacity: nameFade === 1 ? undefined : nameFade }} />
      )}
      {lines.map((l, i) => {
        if (l.tier > maxTier || (l.tier !== 0 && !tiers.includes(String(l.tier)))) return null;
        let size = (l.size ?? base) * fit;
        if (l.tier === 0) size = Math.min(size, zoomPart !== '' ? capSize(nameCap, K, zoom) : nameCap ?? Infinity); // no zoom in the key: the floor is not holding the cap up
        if (l.tier === 0 && floored) size = NAME_FLOOR_PX / (K * zoom); // the floor wins over the cap: it is only used where the capped size is smaller
        const withIcon = icon?.mode === 'inline' && l.tier === 0 && !inlineDone;
        if (withIcon) inlineDone = true;
        return (
          <div key={i} data-tier={l.tier} style={{ opacity: l.tier === 0 && nameFade !== 1 ? nameFade : undefined, fontSize: size, fontWeight: l.weight === 'bold' ? 700 : 400, fontStyle: l.italic ? 'italic' : 'normal' }}>
            {withIcon && <img data-role="icon" src={icon.src} alt="" aria-hidden="true" draggable={false} onError={hideBroken}
                              style={{ width: '1.25em', height: '1.25em', verticalAlign: 'top', marginRight: ICON_INLINE_GAP_PX, objectFit: 'contain' }} />}
            {l.text}
          </div>
        );
      })}
    </div>
  );
}

function Shape({ n, expanded, c }: { n: SceneNode; expanded: boolean; c: NodeColors }) {
  const { w, h, shape, style: s } = n;
  const sw = s.strokeWidth ?? 1;
  const common = { fill: c.fill, stroke: c.stroke, strokeWidth: sw, fillOpacity: c.fillOpacity, strokeDasharray: expanded ? '8 5' : undefined };
  const i = sw / 2;
  let body: ReactNode;
  if (shape === 'Cylinder') {
    const ry = Math.min(14, h / 6);
    body = (
      <>
        <path d={`M${i},${ry} A${w / 2 - i},${ry} 0 0 1 ${w - i},${ry} V${h - ry} A${w / 2 - i},${ry} 0 0 1 ${i},${h - ry} Z`} {...common} />
        <path d={`M${i},${ry} A${w / 2 - i},${ry} 0 0 0 ${w - i},${ry}`} fill="none" stroke={c.stroke} strokeWidth={sw} />
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

const useZoomKey = (lines: LabelLine[], base: number, K: number, allowFloor: boolean, nameCap: number | null): string =>
  useStore((s) => labelMode(lines, base, K, s.transform[2], allowFloor, nameCap));

function Badges({ d }: { d: FlowNode['data'] }) {
  return (
    <>
      {d.n.instances && <span className="badge instances" data-badge="instances" title={`${d.n.instances} instances`}>×{d.n.instances}</span>}
      {d.frameBadge && <span className="badge count" data-badge="count">{d.frameBadge}</span>}
      {d.matchBadge && <span className="badge matches" data-badge="matches">{d.matchBadge}</span>}
    </>
  );
}

function Box({ d, boundary }: { d: FlowNode['data']; boundary: boolean }) {
  const n = d.n;
  const zoomKey = useZoomKey(n.label.lines, n.style.fontSize, d.K, !d.expanded, d.nameCap);
  // Expanded frames (the focused one and its ancestors): the name scales with the zoom like everything else and fades out between 12 and 6 px.
  const nameSize = n.label.lines.find((l) => l.tier === 0)?.size ?? n.style.fontSize;
  const labelOpacity = useStore((s) => (d.expanded ? labelFade(Math.min(nameSize, capSize(d.nameCap, d.K, s.transform[2])) * d.K * s.transform[2], reducedMotion()) : 1));
  // Children of an expanded frame fade out as the zoom falls below the frame's fit zoom (it collapses at CHILD_FADE.gone).
  const kidsOpacity = useStore((s) => (d.owner ? childFade(s.transform[2] / fitZoom(d.owner.w, d.owner.h, s.width, s.height, phoneLayout(), s.maxZoom), reducedMotion()) : 1));
  const a = n.label.anchor;
  // Not expanded: the floored name fades out where it no longer fits its box (expanded frames have the size-based fade above).
  const leftAligned = boundary || a === 'top-left' || a === 'bottom-left';
  const family = useViewer((s) => s.branding?.font?.family ?? null);
  const fontEpoch = useViewer((s) => (s.branding?.font ? s.fontEpoch : 0));
  const fit = useMemo(() => fitScale(n.label.lines, family), [n.label.lines, family, fontEpoch]); // fontEpoch: measure again once a face has loaded
  const iconSrc = useViewer((s) => (n.style.icon ? s.branding?.images?.[n.style.icon] ?? null : null));
  const icon: NodeIcon | null = iconSrc ? { src: iconSrc, mode: boundary || a !== 'center' || n.shape === 'Person' ? 'inline' : 'block' } : null;
  const nameFade = useStore((s) => (d.expanded ? 1 : nameFit(n.label.lines, n.style.fontSize, d.K, d.nameCap, n.w, leftAligned ? 8 : 0, s.transform[2], family, fit)));
  const personPad = n.shape === 'Person' ? Math.min(n.w, n.h) * 0.34 : 0;
  const theme = useViewer((s) => s.theme);
  const c = nodeColors(n.style, boundary, d.expanded, theme, d.under);
  const color = c.color;
  const cls = [boundary ? 'c4b' : 'c4el', d.hit ? 'hit' : '', d.selected ? 'sel' : '', d.expanded ? 'expanded' : '', d.matchBadge ? 'has-match' : ''].filter(Boolean).join(' ');
  const inner: CSSProperties = { position: 'absolute', left: 0, top: 0, width: n.w, height: n.h, transformOrigin: '0 0', transform: d.K === 1 ? undefined : `scale(${d.K})`, overflow: 'hidden' };
  const label = <Lines lines={n.label.lines} base={n.style.fontSize} K={d.K} zoomKey={zoomKey} align={boundary ? 'left' : 'center'} color={color}
    maxTier={d.expanded ? (d.focused ? 1 : 0) : 2} nameCap={d.nameCap} fade={labelOpacity} frame={d.expanded} nameFade={nameFade} fit={fit} icon={icon} />;
  return (
    <div className={cls} data-id={n.id} data-selected={d.selected ? 'true' : undefined} data-expanded={d.expanded ? 'true' : undefined} data-fresh={d.K !== 1 ? '' : undefined}
         style={{ width: n.w * d.K, height: n.h * d.K, opacity: d.opacity }}>
      <div className="fx" style={{ ...inner, overflow: 'visible', opacity: kidsOpacity === 1 ? undefined : kidsOpacity }}>
        {boundary ? (
          <div className="boundary-box" style={{ position: 'absolute', inset: 0, background: c.fill, border: `${n.style.strokeWidth ?? 1}px ${n.style.dash ? 'dashed' : 'solid'} ${c.stroke}` }} />
        ) : <Shape n={n} expanded={d.expanded} c={c} />}
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
