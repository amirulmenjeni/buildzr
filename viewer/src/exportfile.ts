// Image export, the parts that need no browser: the area to export, the PNG scale and the file name.
// The drawing itself is in export.ts.
import type { Composed, Rect } from './compose';

/** Empty margin around the drawing (flow px), so strokes and arrow heads at its edge are not cut. */
export const EXPORT_PAD = 24;
/** PNG: the largest canvas every supported browser draws (Safari: 16 777 216 px; Chrome and Firefox allow a side of 32 767 px, and most platforms 16 384). */
export const MAX_PNG_PIXELS = 16_777_216;
export const MAX_PNG_SIDE = 16_384;
/** PNG: pixels per flow px when the canvas is not too big: 2 is sharp on a high-density screen and in a document. */
export const PNG_SCALE = 2;
/** Below this the PNG would be too coarse to read: the user is told to use SVG instead. */
export const PNG_MIN_SCALE = 0.5;

/**
 * The whole drawing in flow coordinates, plus EXPORT_PAD: the scene bounds, and every node, arrow and label box, because the
 * bounds of a scene alone do not promise that nothing sticks out (a label box beside a long arrow, a frame that is drawn larger).
 */
export function diagramRect(c: Composed): Rect {
  let x0 = c.bounds.x, y0 = c.bounds.y, x1 = c.bounds.x + c.bounds.w, y1 = c.bounds.y + c.bounds.h;
  const add = (x: number, y: number, w = 0, h = 0) => {
    if (![x, y, w, h].every(Number.isFinite)) return;
    x0 = Math.min(x0, x); y0 = Math.min(y0, y); x1 = Math.max(x1, x + w); y1 = Math.max(y1, y + h);
  };
  for (const r of c.rects.values()) add(r.x, r.y, r.w, r.h);
  for (const e of c.edges) {
    const d = e.data;
    if (!d) continue;
    for (const [x, y] of d.pts) add(x, y);
    if (d.e.label) add(d.labelPos[0], d.labelPos[1], d.e.label.w * d.K, d.e.label.h * d.K);
  }
  return { x: Math.floor(x0 - EXPORT_PAD), y: Math.floor(y0 - EXPORT_PAD), w: Math.ceil(x1 - x0 + 2 * EXPORT_PAD), h: Math.ceil(y1 - y0 + 2 * EXPORT_PAD) };
}

/**
 * Pixels per flow px for a PNG of this drawing, or null when even the smallest acceptable scale would be too big a canvas
 * (a browser cannot draw it; the SVG has no such limit).
 */
export function pngScale(w: number, h: number): number | null {
  if (!(w > 0) || !(h > 0)) return null;
  const s = Math.min(PNG_SCALE, Math.sqrt(MAX_PNG_PIXELS / (w * h)), MAX_PNG_SIDE / Math.max(w, h));
  return s >= PNG_MIN_SCALE ? s : null;
}

/** 32-bit FNV-1a, 8 hex digits: a stable tag for names that the file system cannot keep as they are. */
function tag(s: string): string {
  let h = 0x811c9dc5;
  for (let i = 0; i < s.length; i++) { h ^= s.charCodeAt(i); h = Math.imul(h, 0x01000193) >>> 0; }
  return h.toString(16).padStart(8, '0');
}

/**
 * One part of a file name: lower-case ASCII letters, digits and single hyphens (accents dropped), at most 48 characters; no
 * path separator, dot, space, control or reserved character can occur, on any operating system. A name with characters that
 * have no ASCII form (Chinese, Arabic...) gets a short stable tag so two different names never become the same file.
 */
export function slug(name: string, fallback: string): string {
  const folded = name.normalize('NFKD').replace(/[̀-ͯ]/g, '');
  const base = folded.toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '').slice(0, 48).replace(/-+$/, '');
  const lossy = /[^\x00-\x7f]/.test(folded);
  if (!base) return `${fallback}-${tag(name)}`;
  return lossy ? `${base}-${tag(name)}` : base;
}

/**
 * `<workspace>--<view>.<ext>`: the workspace name and what is drawn: `model` (landscape) or `model-<element path>` for the
 * model canvas, `<view key>` for an authored view. The same drawing always has the same name. The two parts are joined by
 * `--` and never contain it, so the stem is never a reserved Windows device name such as CON or NUL.
 */
export function exportFilename(workspace: string, what: { view: string | null; path: string }, ext: 'png' | 'svg'): string {
  const drawing = what.view !== null ? slug(what.view, 'view') : what.path ? `model-${slug(what.path, 'element')}` : 'model';
  return `${slug(workspace, 'workspace')}--${drawing}.${ext}`;
}

/**
 * The CSS of the exported SVG with its `@font-face` rules in a fixed order. The library embeds the fonts as they finish
 * downloading, so the order of two fonts changes from run to run; the same diagram must give the same file.
 */
export function sortFontFaces(css: string): string {
  const re = /@font-face\s*\{[^}]*\}\n?/g;
  const rules = css.match(re);
  if (!rules || rules.length < 2) return css;
  const at = css.search(re);
  const rest = css.replace(re, '');
  return rest.slice(0, at) + rules.map((r) => (r.endsWith('\n') ? r : r + '\n')).sort().join('') + rest.slice(at);
}
