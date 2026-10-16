// Text width from the font's own metrics, for deciding whether a floored name fits its box. The scene carries the wrapped lines
// but not their widths, so we measure with the same Inter the page renders with (canvas measureText, scaled from a large size).

let ctx: CanvasRenderingContext2D | null = null;
const cache = new Map<string, number>();
const fontOf = (bold: boolean, italic: boolean): string => `${italic ? 'italic ' : ''}${bold ? 700 : 400} 100px Inter, sans-serif`;

if (typeof document !== 'undefined' && document.fonts) {
  // fetch the faces early so the first measurement already sees them
  void document.fonts.load('400 16px Inter').catch(() => undefined);
  void document.fonts.load('700 16px Inter').catch(() => undefined);
}

/** Width of `text` in em (multiply by the font size in px). */
export function measureEm(text: string, bold: boolean, italic: boolean): number {
  const key = `${bold ? 'b' : 'n'}${italic ? 'i' : ''}|${text}`;
  const hit = cache.get(key);
  if (hit !== undefined) return hit;
  ctx ??= document.createElement('canvas').getContext('2d');
  if (!ctx) return text.length * 0.6; // no canvas: a generous average glyph width
  const font = fontOf(bold, italic);
  ctx.font = font;
  const em = ctx.measureText(text).width / 100;
  if (document.fonts.check(font)) cache.set(key, em); // a fallback-font measurement is not kept
  return em;
}
