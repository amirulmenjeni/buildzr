// Image export: the diagram as drawn now (React Flow's own DOM: HTML nodes, SVG shapes and arrows, HTML arrow labels), whole,
// as PNG or SVG, entirely in this browser. modern-screenshot clones the DOM with its computed styles and embeds the fonts and
// images it uses into one SVG (an HTML tree in a <foreignObject>); the PNG is that same SVG drawn on a canvas, so the two
// formats cannot differ. The viewer's own state is never touched: everything that is not the diagram is removed from the clone.
import { domToBlob, domToForeignObjectSvg } from 'modern-screenshot';
import type { Rect } from './compose';
import { MAX_PNG_PIXELS, pngScale, sortFontFaces } from './exportfile';
import { CANVAS, type Theme } from './theme';

export type ExportFormat = 'png' | 'svg';
export interface ExportRequest {
  format: ExportFormat;
  /** `.react-flow__viewport` of the canvas. */
  viewport: HTMLElement;
  /** The drawing in flow coordinates (exportfile.ts diagramRect). */
  rect: Rect;
  /** The theme the canvas is drawn in. */
  theme: Theme;
  /** No background at all (see backgroundFor). */
  transparent: boolean;
  /** Text for the SVG's <title> (screen readers, and what a browser shows for the file). */
  title: string;
}

/** An error the user can act on; `message` is shown as it is. */
export class ExportError extends Error {}

/**
 * The fill behind the diagram. The canvas colour of the theme on screen by default, in both formats: the text and arrow colours
 * of the drawing were chosen against that colour (a dark theme lightens them), so a file without it can be unreadable on
 * the page it is placed on. `transparent` leaves it out for a figure that sits on a page of the same theme.
 */
export const backgroundFor = (theme: Theme, transparent: boolean): string | null => (transparent ? null : CANVAS[theme]);

/** What is on the canvas but is not the diagram: React Flow's invisible handles and the wide invisible hit area of each arrow. */
const isChrome = (n: Node): boolean =>
  n instanceof Element && (n.classList.contains('react-flow__handle') || n.classList.contains('react-flow__edge-interaction'));

/** The clone, without selection and search marks: outlines, the "N matches" badges, the thicker selected arrow. */
function plain(root: Node): void {
  if (!(root instanceof Element)) return;
  root.querySelectorAll('.badge.matches').forEach((b) => b.remove());
  // React Flow draws each arrow in an <svg> that is far smaller than the arrow and relies on a style sheet's `overflow: visible`.
  // The clone only keeps computed values that differ from an unstyled element's, and `visible` does not, so the browser's own
  // `svg { overflow: hidden }` would cut every arrow off. Say it again.
  root.querySelectorAll<SVGSVGElement>('.react-flow__edges svg').forEach((svg) => { svg.style.overflow = 'visible'; });
  root.querySelectorAll<HTMLElement>('.react-flow__node, .c4el, .c4b').forEach((n) => { n.style.outline = 'none'; });
  root.querySelectorAll<SVGGElement>('g[data-plain-width]').forEach((g) => {
    const path = g.querySelector<SVGPathElement>('.react-flow__edge-path');
    if (path) path.style.strokeWidth = g.getAttribute('data-plain-width') ?? '';
  });
}

const fail = (e: unknown, format: ExportFormat): ExportError => {
  const why = e instanceof Error ? e.message : String(e);
  if (e instanceof ExportError) return e;
  if (/memory|too large|canvas/i.test(why)) return new ExportError(`The diagram is too large for this browser to draw as a ${format.toUpperCase()}. Try SVG, or export a smaller part of the model.`);
  return new ExportError(`${why || 'Unknown error'}. Try again, or use ${format === 'png' ? 'SVG' : 'PNG'}. If it keeps failing, reload the page.`);
};

export async function renderDiagram(r: ExportRequest): Promise<Blob> {
  const { rect, format } = r;
  const w = Math.max(1, Math.round(rect.w)), h = Math.max(1, Math.round(rect.h));
  const scale = format === 'png' ? pngScale(w, h) : 1;
  if (scale === null) {
    throw new ExportError(`The diagram is ${w} x ${h} px, too large to draw as a PNG (at most ${MAX_PNG_PIXELS.toLocaleString('en')} pixels). Use SVG instead.`);
  }
  try {
    await document.fonts?.ready; // the fonts to embed are those of the page: wait until they have loaded
    const o = {
      width: w, height: h, scale, backgroundColor: backgroundFor(r.theme, r.transparent),
      // The viewport is moved so that the drawing's top-left is the image's origin, at scale 1 whatever the user's zoom is.
      style: { transform: `translate(${-rect.x}px, ${-rect.y}px) scale(1)`, width: `${w}px`, height: `${h}px` },
      filter: (n: Node) => !isChrome(n),
      onCloneNode: plain,
    };
    if (format === 'png') return await domToBlob(r.viewport, { ...o, type: 'image/png' });
    const svg = await domToForeignObjectSvg(r.viewport, o);
    svg.querySelectorAll('style').forEach((st) => { st.textContent = sortFontFaces(st.textContent ?? ''); });
    svg.setAttribute('viewBox', `0 0 ${w} ${h}`);
    svg.setAttribute('width', String(w));
    svg.setAttribute('height', String(h));
    svg.setAttribute('role', 'img');
    const title = svg.ownerDocument.createElementNS('http://www.w3.org/2000/svg', 'title');
    title.textContent = r.title;
    svg.insertBefore(title, svg.firstChild);
    return new Blob(['<?xml version="1.0" encoding="UTF-8"?>\n', new XMLSerializer().serializeToString(svg)], { type: 'image/svg+xml;charset=utf-8' });
  } catch (e) {
    throw fail(e, format);
  }
}

/** Hand the file to the browser's download. The object URL lives until the click has been processed. */
export function download(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = filename;
  a.rel = 'noopener';
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 10_000);
}
