// Unit tests without a browser: the pure parts of the image export (exportfile.ts): file names, the PNG scale, the area exported.
// Run: npm run test:unit
import { T } from './lib.mjs';
import { diagramRect, exportFilename, pngScale, slug, sortFontFaces, EXPORT_PAD, MAX_PNG_PIXELS, MAX_PNG_SIDE, PNG_SCALE } from '../src/exportfile.ts';

const t = new T('exportfile');

// ---- file names: stable, readable, and safe on every file system
t.eq(exportFilename('Shop', { view: null, path: '' }, 'png'), 'shop--model.png', 'landscape');
t.eq(exportFilename('Shop', { view: null, path: 'online-shop/api' }, 'svg'), 'shop--model-online-shop-api.svg', 'element path of the model canvas');
t.eq(exportFilename('Shop', { view: 'shop-containers', path: '' }, 'svg'), 'shop--shop-containers.svg', 'authored view');
t.eq(exportFilename('Shop', { view: 'landscape', path: '' }, 'png'), 'shop--landscape.png', 'a view called landscape is not the model landscape');
t.eq(exportFilename('Shop', { view: 'v', path: 'ignored' }, 'png'), 'shop--v.png', 'a view wins over a path');
t.eq(exportFilename('Shop', { view: null, path: 'a' }, 'png'), exportFilename('Shop', { view: null, path: 'a' }, 'png'), 'deterministic');
t.eq(exportFilename('Online Shop (EU) v2', { view: 'k', path: '' }, 'png'), 'online-shop-eu-v2--k.png', 'spaces and punctuation become one hyphen');
t.eq(exportFilename('Café Zoë', { view: 'k', path: '' }, 'png'), 'cafe-zoe--k.png', 'accented Latin letters fold to their base letters');
t.ok(slug('日本A', 'x') !== slug('中文A', 'x'), 'names that differ only in letters without an ASCII form stay different files');

const UNSAFE = ['../../etc/passwd', '..\\..\\windows\\system32', 'a/b\\c:d*e?f"g<h>i|j', 'name\u0000with\u0007control\nchars', '   ', '...', 'CON', 'nul.txt', '日本語の名前', '🙂🙂', '', 'a'.repeat(500), 'x'.repeat(10) + '‮' + 'gnp.exe'];
for (const w of UNSAFE) {
  for (const v of UNSAFE) {
    const f = exportFilename(w, { view: v, path: '' }, 'png');
    t.ok(/^[a-z0-9]+(?:-[a-z0-9]+)*--[a-z0-9]+(?:-[a-z0-9]+)*\.png$/.test(f), `safe name for ${JSON.stringify(w).slice(0, 30)} / ${JSON.stringify(v).slice(0, 30)}: ${f}`);
    t.ok(f.length <= 48 + 48 + 2 + 9 + 4 + 9 + 8, `short name: ${f.length}`);
    t.ok(!f.startsWith('-') && !f.startsWith('.'), `no leading dot or hyphen: ${f}`);
  }
}
t.ok(slug('日本語', 'workspace') !== slug('中文字', 'workspace'), 'two names without ASCII letters stay two files');
t.eq(slug('日本語', 'workspace'), slug('日本語', 'workspace'), 'and the same name stays the same file');
t.ok(slug('', 'view').startsWith('view-'), 'an empty name falls back');
t.ok(!/--/.test(slug('a -- b', 'x')), 'a part never contains the separator');
t.ok(exportFilename('x', { view: null, path: '' }, 'png').startsWith('x--'), 'the stem is never a bare device name (CON, NUL...)');

// ---- PNG scale: sharp when it fits, smaller when it must, none when it cannot
t.eq(pngScale(1000, 800), PNG_SCALE, 'a normal diagram: 2x');
t.eq(pngScale(0, 10), null, 'empty');
t.eq(pngScale(NaN, 10), null, 'not a number');
const big = pngScale(6000, 4000);
t.ok(big !== null && big < PNG_SCALE && big >= 0.5, `a big one is reduced: ${big}`);
t.ok(6000 * big * 4000 * big <= MAX_PNG_PIXELS + 1, 'and fits the pixel budget');
t.ok(pngScale(30000, 100) * 30000 <= MAX_PNG_SIDE + 1e-6, 'a long thin one fits the side limit');
t.eq(pngScale(40000, 40000), null, 'too large even at the smallest scale: use SVG');

// ---- the area: everything the drawing has, whatever the scene bounds say
const edge = (pts, label) => ({ data: { pts, labelPos: label ? [label.x, label.y] : [0, 0], K: label?.K ?? 1, e: { label: label ? { w: label.w, h: label.h } : null } } });
const c = {
  bounds: { x: 100, y: 200, w: 300, h: 400 },
  rects: new Map([['a', { x: 100, y: 200, w: 50, h: 50 }], ['b', { x: 350, y: 550, w: 50, h: 50 }]]),
  edges: [],
};
t.eq(diagramRect(c), { x: 100 - EXPORT_PAD, y: 200 - EXPORT_PAD, w: 300 + 2 * EXPORT_PAD, h: 400 + 2 * EXPORT_PAD }, 'the scene bounds with a margin');
c.rects.set('c', { x: 50, y: 700, w: 100, h: 100 }); // a node outside the bounds
t.eq(diagramRect(c), { x: 50 - EXPORT_PAD, y: 200 - EXPORT_PAD, w: 350 + 2 * EXPORT_PAD, h: 600 + 2 * EXPORT_PAD }, 'a node outside the bounds is included');
c.edges = [edge([[10, 10], [500, 900]], { x: 480, y: 880, w: 100, h: 30, K: 0.5 })]; // an arrow and its label box outside
const r = diagramRect(c);
t.ok(r.x <= 10 - EXPORT_PAD && r.y <= 10 - EXPORT_PAD, `arrow points are included: ${JSON.stringify(r)}`);
t.ok(r.x + r.w >= 530 + EXPORT_PAD && r.y + r.h >= 895 + EXPORT_PAD, `the label box (scaled by K) is included: ${JSON.stringify(r)}`);
c.edges = [edge([[NaN, 5], [Infinity, 7]])];
const r2 = diagramRect(c);
t.ok(Object.values(r2).every(Number.isFinite), 'a bad point does not poison the area');

// ---- the font rules come out in one order whatever order the fonts arrived in
const ff = (w) => `@font-face { font-family: Inter; font-weight: ${w}; src: url("data:font/woff2;base64,AAAA"); }\n`;
const pre = '.a { color: red; }\n', post = '.b { x: y; }\n';
t.eq(sortFontFaces(pre + ff(700) + ff(400) + post), pre + ff(400) + ff(700) + post, 'two fonts in the other order');
t.eq(sortFontFaces(pre + ff(400) + ff(700) + post), pre + ff(400) + ff(700) + post, 'already in order');
t.eq(sortFontFaces(pre + post), pre + post, 'no font rules');
t.eq(sortFontFaces(pre + ff(400) + post), pre + ff(400) + post, 'one font rule');

console.log(`\nexportfile: ${t.checks} checks, ${t.fails} failed`);
process.exit(t.fails ? 1 : 0);
