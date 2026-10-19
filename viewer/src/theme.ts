// Light and dark theme: the resolved theme, and the canvas colours that depend on it.
// The page chrome takes its colours from the CSS tokens in app.css (:root and [data-theme=dark]); the canvas draws
// the scene's colours (the model's styles), adjusted here only where text or a box edge would not stand out:
// text at least 4.5:1 against what is behind it, box edges and arrows at least 3:1 against the canvas (WCAG AA).
import type { ThemeChoice } from './protocol';
import type { NodeStyle } from './types';

export type Theme = 'light' | 'dark';

/** The canvas background and the edge-label box of each theme (also in app.css as --canvas and --label-bg). */
export const CANVAS: Record<Theme, string> = { light: '#ffffff', dark: '#15181d' };
export const LABEL_BG: Record<Theme, string> = { light: '#ffffff', dark: '#15181d' };
/** Expanded frames are drawn with their fill at this opacity (nodes.tsx). */
export const FRAME_FILL_OPACITY = 0.12;
export const TEXT_MIN = 4.5;
export const UI_MIN = 3;
/** Frame names get a margin over AA: what is behind them is a blend that the canvas can tint further (groups, filters). */
export const FRAME_TEXT_MIN = 5;

export const resolveTheme = (choice: ThemeChoice, prefersDark: boolean): Theme =>
  choice === 'system' ? (prefersDark ? 'dark' : 'light') : choice;

type RGB = [number, number, number];
const parse = (hex: string): RGB | null => {
  const h = hex.trim().toLowerCase();
  if (/^#[0-9a-f]{6}$/.test(h)) return [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16)) as RGB;
  if (/^#[0-9a-f]{3}$/.test(h)) return [1, 2, 3].map((i) => parseInt(h[i] + h[i], 16)) as RGB;
  return null;
};
const hex = (c: RGB): string => '#' + c.map((v) => Math.round(Math.min(255, Math.max(0, v))).toString(16).padStart(2, '0')).join('');

export function luminance(c: string): number {
  const rgb = parse(c);
  if (!rgb) return 0;
  const ch = rgb.map((v) => v / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * ch[0] + 0.7152 * ch[1] + 0.0722 * ch[2];
}
/** WCAG contrast ratio of two colours (#rgb or #rrggbb). */
export function contrast(a: string, b: string): number {
  const [x, y] = [luminance(a), luminance(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
}
/** `top` drawn at `alpha` over `bottom`. */
export function mix(bottom: string, top: string, alpha: number): string {
  const b = parse(bottom), t = parse(top);
  if (!b || !t) return bottom;
  return hex([0, 1, 2].map((i) => b[i] + (t[i] - b[i]) * alpha) as RGB);
}

/**
 * `c` unchanged when it reaches `min` against `bg`; else `c` moved towards white (on a dark background) or black (on a
 * light one) by the smallest step that reaches it, so the hue stays recognisable. Unparsable colours are returned as given.
 */
export function ensure(c: string, bg: string, min: number): string {
  if (!parse(c) || !parse(bg) || contrast(c, bg) >= min) return c;
  const to = luminance(bg) < 0.18 ? '#ffffff' : '#000000';
  let lo = 0, hi = 1;
  for (let i = 0; i < 16; i++) {
    const mid = (lo + hi) / 2;
    if (contrast(mix(c, to, mid), bg) >= min) hi = mid; else lo = mid;
  }
  return mix(c, to, hi);
}

const FG_DARK = '#e6e9ed';
/** A grey (black, #444, white...) has no hue to keep: on the dark canvas it becomes the theme's text colour. */
const grey = (c: string): boolean => { const v = parse(c); return !!v && v[0] === v[1] && v[1] === v[2]; };
const text = (c: string, bg: string, theme: Theme, min = TEXT_MIN): string =>
  theme === 'dark' && grey(c) && contrast(c, bg) < min && contrast(FG_DARK, bg) >= min ? FG_DARK : ensure(c, bg, min);

/** What the canvas draws for one node: the scene's style, with the theme's adjustments. */
export interface NodeColors { fill: string; stroke: string; color: string; fillOpacity: number }

/**
 * Element boxes keep their fill and text colour (the text was chosen against the fill when the workspace was built); the
 * outline is adjusted so the box stands out from the canvas. Expanded frames and boundaries are see-through or the
 * default white: their label is drawn on the canvas, so it is adjusted against what is really behind it.
 */
export function nodeColors(s: NodeStyle, boundary: boolean, expanded: boolean, theme: Theme, under: readonly string[] = []): NodeColors {
  const canvas = under.reduce((bg, f) => mix(bg, f, FRAME_FILL_OPACITY), CANVAS[theme]);
  if (boundary) {
    // A boundary's default fill is white: on the dark canvas it becomes the canvas itself (a user's own fill is kept).
    const fill = theme === 'dark' && s.fill.toLowerCase() === '#ffffff' ? canvas : s.fill;
    return { fill, fillOpacity: 1, stroke: ensure(s.stroke, canvas, UI_MIN), color: text(s.color, parse(fill) ? fill : canvas, theme) };
  }
  if (expanded) {
    const behind = mix(canvas, s.fill, FRAME_FILL_OPACITY);
    const stroke = ensure(s.stroke, behind, UI_MIN);
    return { fill: s.fill, fillOpacity: FRAME_FILL_OPACITY, stroke, color: text(s.stroke, behind, theme, FRAME_TEXT_MIN) };
  }
  // The outline only matters where the fill itself does not stand out from the canvas.
  const stroke = parse(s.fill) && contrast(s.fill, canvas) >= UI_MIN ? s.stroke : ensure(s.stroke, canvas, UI_MIN);
  return { fill: s.fill, fillOpacity: 1, stroke, color: s.color };
}

/** An arrow and its label: the line at least 3:1 against the canvas, the label text 4.5:1 against its box. */
export function edgeColors(stroke: string, labelColor: string | undefined, theme: Theme): { stroke: string; label: string } {
  return { stroke: ensure(stroke, CANVAS[theme], UI_MIN), label: text(labelColor ?? stroke, LABEL_BG[theme], theme) };
}
