// Zoom-driven fades and the zoom-out collapse rule. Pure functions: the components feed them the zoom.

/** An expanded frame's children are fully visible at >= `full` x the frame's own fit zoom, gone at <= `gone`; below `gone` it collapses. */
export const CHILD_FADE = { full: 0.8, gone: 0.5 };
/** A frame label's opacity ramps from 1 at `full` on-screen px (font size) to 0 at `gone` px. */
export const LABEL_FADE = { full: 12, gone: 6 };
/** With reduced motion nothing is faded gradually: labels switch at this size. */
export const LABEL_STEP_PX = 9;

const clamp01 = (x: number): number => Math.min(1, Math.max(0, x));
/** Quantised to 1/100 so a continuous zoom does not re-render every node on every wheel tick. */
const q = (x: number): number => Math.round(x * 100) / 100;

export const reducedMotion = (): boolean => matchMedia('(prefers-reduced-motion: reduce)').matches;
export const phoneLayout = (): boolean => matchMedia('(max-width: 767px)').matches;

/** The zoom at which the camera fits a frame of this size (the same number the camera uses). */
export function fitZoom(w: number, h: number, width: number, height: number, phone: boolean, maxZoom: number): number {
  const share = phone ? 0.92 : 0.7; // the frame fills this share of the canvas
  return Math.min(maxZoom, Math.max(0.01, Math.min((share * width) / w, (share * height) / h)));
}

/** Opacity of the children of an expanded frame; `ratio` = zoom / the frame's fit zoom. */
export const childFade = (ratio: number, reduced: boolean): number =>
  reduced ? 1 : q(clamp01((ratio - CHILD_FADE.gone) / (CHILD_FADE.full - CHILD_FADE.gone)));

/** Opacity of a frame label whose text is `px` high on screen. */
export const labelFade = (px: number, reduced: boolean): number =>
  reduced ? (px >= LABEL_STEP_PX ? 1 : 0) : q(clamp01((px - LABEL_FADE.gone) / (LABEL_FADE.full - LABEL_FADE.gone)));

/** An expanded frame goes back to collapsed when it is drawn smaller than this x its fit zoom. */
export const shouldCollapse = (ratio: number): boolean => ratio < CHILD_FADE.gone;
