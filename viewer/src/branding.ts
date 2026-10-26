// The workspace's branding font: the diagram text (node and arrow labels) is set in it, the page chrome stays Inter.
// The layout was made at build time with Inter's metrics, so a label set in another font is scaled down (never up) to
// the width Inter would take, once the font is ready: the same font gives the same picture, and no text overflows its box.
import type { LabelLine } from './types';
import { measureEm } from './textwidth';

export const DEFAULT_FAMILY = 'Inter, sans-serif';
/** How long the first drawing waits for a branding font to load before it is drawn with what the browser has. */
export const FONT_WAIT_MS = 3000;

/** Set the font of the diagram text (null: Inter). */
export function applyFamily(family: string | null): void {
  document.documentElement.style.setProperty('--diagram-font', family ?? DEFAULT_FAMILY);
}

/** Wait (at most `ms`) until the faces of `family` the diagrams use are loaded; false when it timed out or failed. */
export async function fontsReady(family: string, ms = FONT_WAIT_MS): Promise<boolean> {
  if (!document.fonts) return true;
  const load = Promise.all(['400', '700'].map((w) => document.fonts.load(`${w} 16px ${family}`))).then(() => document.fonts.ready).then(() => true, () => false);
  let timer = 0;
  const timeout = new Promise<boolean>((r) => { timer = window.setTimeout(() => r(false), ms); });
  const ok = await Promise.race([load, timeout]);
  window.clearTimeout(timer);
  return ok;
}

/** Scale (<= 1) that makes every line of a label as wide as it is in Inter; 1 without a branding font. */
export function fitScale(lines: readonly LabelLine[], family: string | null): number {
  if (!family) return 1;
  let s = 1;
  for (const l of lines) {
    if (!l.text) continue;
    const bold = l.weight === 'bold', italic = !!l.italic;
    const own = measureEm(l.text, bold, italic, family);
    const inter = measureEm(l.text, bold, italic);
    if (own > 0 && inter > 0) s = Math.min(s, inter / own);
  }
  return Math.round(s * 1000) / 1000; // stable keys and sizes: 3 decimals
}
