// Unit tests without a browser: the contrast of the theme (theme.ts, the app.css tokens), WCAG AA in both themes.
// Run: npm run test:unit
import fs from 'node:fs';
import path from 'node:path';
import { T, ROOT } from './lib.mjs';
import { CANVAS, LABEL_BG, contrast, edgeColors, ensure, mix, nodeColors, FRAME_FILL_OPACITY } from '../src/theme.ts';

const t = new T('contrast');
// ---- contrast: the default C4 palette as the build writes it (buildzr/site/styles.py, text_color "wcag")
const darken = (c, f = 0.7) => '#' + [1, 3, 5].map((i) => Math.floor(parseInt(c.slice(i, i + 2), 16) * f).toString(16).padStart(2, '0')).join('');
const wcag = (fill) => (contrast('#000000', fill) >= contrast('#ffffff', fill) ? '#000000' : '#ffffff');
const leaf = (fill) => ({ fill, stroke: darken(fill), color: wcag(fill), fontSize: 16 });
const ELEMENTS = { Person: '#08427b', SoftwareSystem: '#1168bd', Container: '#438dd5', Component: '#85bbf0' };
// boundaries: groups (#888 border, black label), deployment nodes (#888, black), and a boundary with a user fill
const BOUNDARIES = { Group: { fill: '#ffffff', stroke: '#888888', color: '#000000', fontSize: 16 },
  'filled boundary': { fill: '#fff3c4', stroke: '#b8860b', color: '#000000', fontSize: 16 } };
const rows = [];
for (const theme of ['light', 'dark']) {
  const canvas = CANVAS[theme];
  for (const [type, fill] of Object.entries(ELEMENTS)) {
    const s = leaf(fill);
    const c = nodeColors(s, false, false, theme);
    const edge = Math.max(contrast(c.fill, canvas), contrast(c.stroke, canvas));
    t.ok(contrast(c.color, c.fill) >= 4.5, `${theme} ${type}: text on the box ${contrast(c.color, c.fill).toFixed(2)}`);
    t.ok(edge >= 3, `${theme} ${type}: box against the canvas ${edge.toFixed(2)}`);
    t.eq([c.fill, c.color], [s.fill, s.color], `${theme} ${type}: fill and text colour kept`);
    // expanded, at every depth of nesting (the frames above it tint what is behind its name)
    for (let depth = 0; depth < 4; depth++) {
      const under = Array(depth).fill(fill);
      const e = nodeColors(s, false, true, theme, under);
      const behind = mix(under.reduce((bg, f) => mix(bg, f, FRAME_FILL_OPACITY), canvas), fill, FRAME_FILL_OPACITY);
      t.ok(contrast(e.color, behind) >= 4.5, `${theme} ${type} frame (depth ${depth}): name ${contrast(e.color, behind).toFixed(2)}`);
      t.ok(contrast(e.stroke, behind) >= 3, `${theme} ${type} frame (depth ${depth}): border ${contrast(e.stroke, behind).toFixed(2)}`);
      if (depth === 0) rows.push({ theme, type, text: contrast(c.color, c.fill).toFixed(2), box: edge.toFixed(2), frameName: contrast(e.color, behind).toFixed(2), frameName3deep: '' });
      if (depth === 3) rows[rows.length - 1].frameName3deep = contrast(e.color, behind).toFixed(2);
    }
  }
  for (const [type, s] of Object.entries(BOUNDARIES)) {
    const c = nodeColors(s, true, false, theme);
    t.ok(contrast(c.color, c.fill) >= 4.5, `${theme} ${type}: label ${contrast(c.color, c.fill).toFixed(2)}`);
    t.ok(contrast(c.stroke, canvas) >= 3, `${theme} ${type}: border ${contrast(c.stroke, canvas).toFixed(2)}`);
    if (type === 'filled boundary') t.eq(c.fill, s.fill, `${theme}: a user's boundary fill is kept`);
    rows.push({ theme, type, text: contrast(c.color, c.fill).toFixed(2), box: contrast(c.stroke, canvas).toFixed(2), frameName: '', frameName3deep: '' });
  }
  for (const stroke of ['#707070', '#000000', '#ffffff', '#1168bd', '#ff0000', '#cccccc']) {
    const e = edgeColors(stroke, undefined, theme);
    t.ok(contrast(e.stroke, canvas) >= 3, `${theme} arrow ${stroke}: ${contrast(e.stroke, canvas).toFixed(2)}`);
    t.ok(contrast(e.label, LABEL_BG[theme]) >= 4.5, `${theme} arrow label ${stroke}: ${contrast(e.label, LABEL_BG[theme]).toFixed(2)}`);
  }
  t.eq(edgeColors('#707070', undefined, theme).stroke, '#707070', `${theme}: the default arrow colour is kept`);
}
console.table(rows);
t.eq(ensure('#1168bd', '#ffffff', 4.5), '#1168bd', 'ensure keeps a colour that already passes');
t.ok(contrast(ensure('#08427b', '#15181d', 4.5), '#15181d') >= 4.5, 'ensure lightens on dark');

// ---- page tokens (app.css): every text/background pair at 4.5:1, every UI part at 3:1, in both themes
const css = fs.readFileSync(path.join(ROOT, 'src/app.css'), 'utf8');
const block = (sel) => {
  const i = css.indexOf(sel + ' {');
  const body = css.slice(css.indexOf('{', i) + 1, css.indexOf('}', i));
  return Object.fromEntries([...body.matchAll(/--([a-z-]+):\s*([^;]+);/g)].map((m) => [m[1], m[2].trim()]));
};
const TOK = { light: block(':root, :root[data-theme=light]'), dark: block(':root[data-theme=dark]') };
t.eq(Object.keys(TOK.light).sort(), Object.keys(TOK.dark).sort(), 'both themes define the same tokens');
t.eq([TOK.light.canvas, TOK.dark.canvas], [CANVAS.light, CANVAS.dark], 'app.css --canvas = theme.ts CANVAS');
// rgba(r,g,b,a) over a background -> #rrggbb
const solid = (v, over) => {
  const m = /rgba\((\d+),\s*(\d+),\s*(\d+),\s*([\d.]+)\)/.exec(v);
  if (!m) return v;
  const top = '#' + [m[1], m[2], m[3]].map((x) => Number(x).toString(16).padStart(2, '0')).join('');
  return mix(over, top, Number(m[4]));
};
const PAIRS = [ // [foreground, background, minimum, what]
  ['fg', 'bg', 4.5, 'text on the page'], ['fg', 'panel', 4.5, 'text on panels'], ['muted', 'panel', 4.5, 'muted text on panels'],
  ['muted', 'bg', 4.5, 'muted text on the page'], ['accent', 'panel', 4.5, 'links on panels'], ['accent', 'bg', 4.5, 'links on the page'],
  ['accent-fg', 'accent', 4.5, 'text on accent buttons'], ['fg', 'sel-bg', 4.5, 'selected row'], ['accent', 'sel-bg', 3, 'selected row marker'],
  ['fg', 'match-bg', 4.5, 'match row'], ['hit-fg', 'hit-bg', 4.5, 'match badges'], ['fg', 'notice-bg', 4.5, 'notice'],
  ['fg', 'surface', 4.5, 'text on buttons and popovers'], ['control-line', 'surface', 3, 'button and chip borders'], ['control-line', 'panel', 3, 'borders on panels'],
  ['focus', 'bg', 3, 'focus ring on the page'], ['focus', 'panel', 3, 'focus ring on panels'], ['focus', 'canvas', 3, 'focus ring on the canvas'],
  ['accent', 'canvas', 3, 'selection outline'], ['hit', 'canvas', 3, 'match outline'], ['broken-fg', 'broken-bg', 4.5, 'broken banner'],
  ['broken-err-fg', 'broken-err-bg', 4.5, 'broken errors'], ['attrib-fg', 'attrib-bg', 4.5, 'attribution'], ['badge-fg', 'badge-bg', 4.5, 'badges'],
  ['grip', 'panel', 3, 'sheet grip'],
];
const tok = [];
for (const theme of ['light', 'dark']) {
  const k = TOK[theme];
  for (const [fg, bg, min, what] of PAIRS) {
    // translucent backgrounds are judged over the canvas (badges, labels) or the page; the worst case of the fills below for badges
    const backs = fg === 'badge-fg' ? [k.canvas, ...Object.values(ELEMENTS), '#ffffff', '#000000'] : [k.canvas];
    let worst = Infinity;
    for (const under of backs) worst = Math.min(worst, contrast(solid(k[fg], under), solid(k[bg], under)));
    t.ok(worst >= min, `${theme} ${what} (--${fg} on --${bg}): ${worst.toFixed(2)} < ${min}`);
    tok.push({ theme, what, ratio: worst.toFixed(2), min });
  }
}
console.table(tok);

console.log(`\ncontrast: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
