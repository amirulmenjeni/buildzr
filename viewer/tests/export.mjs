// Image export: "Download PNG" and "Download SVG" for the diagram on screen. For the model landscape, a nested element and every
// authored view of the data: the real download (file name, PNG header and pixels, SVG parsed as XML), the whole diagram even when
// the camera shows a part of it, no selection or search marks, the background in each theme and transparent, a phone and an embedded
// frame, and a failure (the viewer must go on working, with a notice that says what to do).
// Run: node tests/run.mjs --only export --data <dir>
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';
import { newPage, open, mouseClick, raf, T, deviceTheme } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');

const CANVAS = { light: [255, 255, 255], dark: [21, 24, 29] }; // theme.ts CANVAS, written out here on purpose
const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'viewer-export-'));
const clean = (s) => s.toLowerCase().normalize('NFKD').replace(/[̀-ͯ]/g, '').replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');

/** The export menu, open (it closes when something else is clicked). */
async function openMenu(p) {
  const toggle = p.getByTestId('export-toggle');
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click();
  await p.getByTestId('export').waitFor();
}

/** Click an export button and take the file the browser downloads. */
async function download(p, fmt) {
  await openMenu(p);
  const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 30000 }), p.click(`[data-testid=export] [data-format=${fmt}]`)]);
  const file = path.join(tmp, `${Date.now()}-${Math.random().toString(36).slice(2)}-${dl.suggestedFilename()}`);
  await dl.saveAs(file);
  return { name: dl.suggestedFilename(), file, buf: fs.readFileSync(file) };
}
const pngSize = (buf) => (buf.subarray(1, 4).toString() === 'PNG' ? { w: buf.readUInt32BE(16), h: buf.readUInt32BE(20) } : null);

/** The PNG as the browser decodes it: size, the colour of the corner pixel, and how much of it is not that colour. */
const pixels = (p, buf) => p.evaluate(async (b64) => {
  const img = new Image();
  await new Promise((r, j) => { img.onload = r; img.onerror = j; img.src = 'data:image/png;base64,' + b64; });
  const c = document.createElement('canvas'); c.width = img.width; c.height = img.height;
  const g = c.getContext('2d'); g.drawImage(img, 0, 0);
  const d = g.getImageData(0, 0, c.width, c.height).data;
  const corner = [...d.slice(0, 4)];
  let other = 0;
  for (let i = 0; i < d.length; i += 4) if (Math.abs(d[i] - corner[0]) + Math.abs(d[i + 1] - corner[1]) + Math.abs(d[i + 2] - corner[2]) + Math.abs(d[i + 3] - corner[3]) > 24) other++;
  return { w: img.width, h: img.height, corner, other: other / (d.length / 4) };
}, buf.toString('base64'));

/** What the live page says about the drawing, measured from the DOM (not from the viewer's code): its size in flow px, and what it holds. */
const live = (p) => p.evaluate(() => {
  const z = window.__viewer.viewport().zoom;
  let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
  const els = [...document.querySelectorAll('.react-flow__node, .react-flow__edge-path, .edge-label')];
  for (const e of els) { const r = e.getBoundingClientRect(); if (!r.width && !r.height) continue; x0 = Math.min(x0, r.left); y0 = Math.min(y0, r.top); x1 = Math.max(x1, r.right); y1 = Math.max(y1, r.bottom); }
  const canvas = document.querySelector('.react-flow').getBoundingClientRect();
  return {
    w: (x1 - x0) / z, h: (y1 - y0) / z, zoom: z,
    shown: x0 >= canvas.left - 1 && y0 >= canvas.top - 1 && x1 <= canvas.right + 1 && y1 <= canvas.bottom + 1, // is it all in the camera?
    edges: document.querySelectorAll('.react-flow__edge-path').length,
    names: [...document.querySelectorAll('.react-flow__node [data-tier="0"]')].map((n) => n.textContent).filter(Boolean),
    ws: document.querySelector('header.top h1')?.textContent ?? '',
  };
});

/** The SVG file as XML, and what it contains. */
const svgFacts = (p, text) => p.evaluate((src) => {
  const doc = new DOMParser().parseFromString(src, 'image/svg+xml');
  const bad = doc.querySelector('parsererror');
  const root = doc.documentElement;
  const q = (s) => doc.querySelectorAll(s).length;
  const body = root.querySelector('foreignObject > *');
  return {
    bad: bad ? bad.textContent.slice(0, 200) : null, tag: root.localName, w: root.getAttribute('width'), h: root.getAttribute('height'), box: root.getAttribute('viewBox'),
    title: root.querySelector('title')?.textContent ?? null, foreign: q('foreignObject'), scripts: q('script'), edges: q('.react-flow__edge-path'),
    handles: q('.react-flow__handle, .react-flow__edge-interaction'), chrome: q('.react-flow__controls, .react-flow__panel, .react-flow__attribution, .react-flow__minimap, [data-testid=export], button, input, select'),
    badges: q('.badge.matches'), fonts: (src.match(/data:font\/woff2;base64,/g) ?? []).length, external: (src.match(/(?:href|src)="(?!data:|#)[^"]+"|url\((?!(?:["']|&quot;)?(?:data:|#))[^)]+\)/g) ?? []).slice(0, 3),
    text: root.textContent, bg: body ? body.style.backgroundColor : null,
    outlined: [...doc.querySelectorAll('.sel, .hit, .has-match, .c4el, .c4b, .react-flow__node')].filter((e) => e.style.outline && e.style.outline !== 'none' && !/^0px|none/.test(e.style.outline)).length,
    sel: [...doc.querySelectorAll('g[data-selected]')].map((g) => [g.getAttribute('data-plain-width'), g.querySelector('.react-flow__edge-path')?.style.strokeWidth]),
  };
}, text);

export default async function exportTest(browser, srv, F, name) {
  const t = new T(`export:${name}`);
  const errors = [];
  const theme = deviceTheme();
  const targets = [['the landscape', '#/m', { view: null, path: '' }]];
  const nested = F.expandable.find((id) => !F.parentOf(id)) ?? F.expandable[0];
  if (nested) targets.push([`the element ${nested}`, `#/m/${nested}`, { view: null, path: nested }]);
  for (const v of F.model.views.slice(0, 8)) targets.push([`view ${v.key} (${v.kind})`, `#/v/${v.key}`, { view: v.key, path: '', title: v.title }]);

  // ---- every target, both formats
  const p = await newPage(browser, errors);
  let sizes = {};
  for (const [label, hash, id] of targets) {
    await open(p, srv.url, hash);
    const L = await live(p);
    const drawing = id.view !== null ? clean(id.view) : id.path ? `model-${clean(id.path)}` : 'model';
    const want = (ext) => `${clean(L.ws)}--${drawing}.${ext}`;

    const png = await download(p, 'png');
    t.eq(png.name, want('png'), `${label}: PNG file name`);
    const sz = pngSize(png.buf);
    t.ok(!!sz, `${label}: the PNG is a PNG`);
    if (!sz) continue;
    const px = await pixels(p, png.buf);
    t.eq([px.w, px.h], [sz.w, sz.h], `${label}: the browser decodes the PNG at the size of its header`);
    const scale = sz.w / Math.round(sz.w / 2) > 1.99 ? 2 : sz.w / (L.w + 48);
    // the whole drawing plus the margin (24 px each side): at least what the DOM measures, and not much more
    t.ok(sz.w / scale >= L.w + 48 - 3 && sz.h / scale >= L.h + 48 - 3, `${label}: PNG ${sz.w}x${sz.h} at ${scale}x holds the drawing ${L.w.toFixed(0)}x${L.h.toFixed(0)} flow px and its margin`);
    t.ok(sz.w / scale <= L.w + 48 + 250 && sz.h / scale <= L.h + 48 + 250, `${label}: and is not much bigger than it`);
    t.ok(sz.w >= 100 && sz.h >= 60, `${label}: a useful resolution (${sz.w}x${sz.h})`);
    t.eq(px.corner.slice(0, 3), CANVAS[theme], `${label}: opaque, in the canvas colour of the ${theme} theme`);
    t.eq(px.corner[3], 255, `${label}: the corner is not transparent`);
    t.ok(px.other > 0.01, `${label}: something is drawn (${(px.other * 100).toFixed(1)}% of the pixels are not background)`);
    sizes[hash] = sz;

    const svg = await download(p, 'svg');
    t.eq(svg.name, want('svg'), `${label}: SVG file name`);
    t.ok(/^[a-z0-9-]+--[a-z0-9-]+\.(png|svg)$/.test(png.name) && /^[a-z0-9-]+--[a-z0-9-]+\.svg$/.test(svg.name), `${label}: names use only a-z, 0-9 and hyphens`);
    const text = svg.buf.toString('utf8');
    const S = await svgFacts(p, text);
    t.eq(S.bad, null, `${label}: the SVG is well-formed XML`);
    t.eq([S.tag, S.foreign, S.scripts], ['svg', 1, 0], `${label}: an svg with its drawing and no script`);
    t.eq([Number(S.w), Number(S.h), S.box], [Math.round(sz.w / scale), Math.round(sz.h / scale), `0 0 ${Math.round(sz.w / scale)} ${Math.round(sz.h / scale)}`], `${label}: the SVG is the size of the PNG (at 1x)`);
    t.ok(!!S.title && S.title.startsWith(L.ws), `${label}: title "${S.title}"`);
    t.eq(S.edges, L.edges, `${label}: every arrow (${L.edges}) is in the SVG`);
    const missing = [...new Set(L.names)].filter((n) => !S.text.includes(n));
    t.eq(missing, [], `${label}: every name drawn is in the SVG`);
    t.eq([S.handles, S.chrome, S.badges, S.outlined], [0, 0, 0, 0], `${label}: no handles, viewer controls, buttons, search badges or outlines`);
    t.ok(S.fonts >= 1, `${label}: the font is embedded (${S.fonts} @font-face)`);
    t.eq(S.external, [], `${label}: nothing is loaded from outside the file`);
    t.eq(S.bg, `rgb(${CANVAS[theme].join(', ')})`, `${label}: SVG background is the canvas colour`);
    t.ok(!/<\/?(?:html|body)[ >]/.test(text.replace(/<style[\s\S]*?<\/style>/g, '')), `${label}: no page around the drawing`);

    const again = await download(p, 'svg');
    t.ok(again.buf.equals(svg.buf), `${label}: exporting twice gives the same SVG file`);
  }
  await p.context().close();

  // ---- the whole diagram, not what the camera shows
  {
    const q = await newPage(browser, errors);
    const [, hash] = targets[targets.length - 1];
    await open(q, srv.url, hash);
    const before = await download(q, 'png');
    await q.evaluate(() => { const v = window.__viewer.viewport(); window.__viewer.setViewport({ zoom: v.zoom * 3, x: v.x * 3 - 900, y: v.y * 3 - 600 }); });
    await raf(q, 4);
    const L = await live(q);
    t.ok(!L.shown, `zoomed in and panned: the camera shows only a part of the diagram`);
    const part = await download(q, 'png');
    t.eq(pngSize(part.buf), pngSize(before.buf), 'the PNG has the size of the whole diagram, whatever the camera shows');
    const svgPart = await svgFacts(q, (await download(q, 'svg')).buf.toString('utf8'));
    t.eq(svgPart.edges, L.edges, 'and the SVG has every arrow');
    const px = await pixels(q, part.buf);
    t.ok(px.other > 0.01, 'and it is drawn there, not blank');
    await q.context().close();
  }

  // ---- no selection, no search marks, no thicker arrow
  {
    const q = await newPage(browser, errors);
    const [, hash] = targets[targets.length - 1];
    await open(q, srv.url, hash);
    // a node that only selects: clicking a frame that has an inside expands it (and leaves the view)
    const ids = await q.locator('.react-flow__node').evaluateAll((ns) => ns.map((n) => n.dataset.id));
    const leaf = ids.find((id) => !id.includes('|') && !F.expandable.includes(id)); // not a view's boundary box (id v/<key>|<group>)
    await mouseClick(q, leaf);
    t.ok((await q.locator('.sel').count()) >= 1, 'a node is selected on screen (outline)');
    const e0 = q.locator('.react-flow__edge-interaction').first();
    if (await e0.count()) await e0.dispatchEvent('click');
    const selEdge = await q.locator('g[data-selected=true] .react-flow__edge-path').count();
    const S = await svgFacts(q, (await download(q, 'svg')).buf.toString('utf8'));
    t.eq(S.outlined, 0, 'the SVG has no selection outline');
    t.eq(S.sel.filter(([plain, now]) => !plain || Number(plain) !== parseFloat(now)), [], `a selected arrow (${selEdge}) is drawn at its normal width`);
    const lead = F.model.elements.find((e) => e.name.length > 3)?.name ?? '';
    await open(q, srv.url, `${hash.split('?')[0]}?q=${encodeURIComponent(lead.slice(0, 4))}`);
    const marks = await q.locator('.hit, .has-match, [data-badge=matches]').count();
    const S2 = await svgFacts(q, (await download(q, 'svg')).buf.toString('utf8'));
    t.eq([S2.outlined, S2.badges], [0, 0], `with a search that marks ${marks} things on screen: no outline, no "matches" badge in the SVG`);
    await q.context().close();
  }

  // ---- the other theme, and transparent
  {
    const other = theme === 'dark' ? 'light' : 'dark';
    const q = await newPage(browser, errors, { colorScheme: other });
    await open(q, srv.url, targets[targets.length - 1][1]);
    t.eq(await q.evaluate(() => window.__viewer.theme), other, `the viewer is in the ${other} theme`);
    const px = await pixels(q, (await download(q, 'png')).buf);
    t.eq(px.corner.slice(0, 3), CANVAS[other], `${other} theme: PNG background is that theme's canvas colour`);
    const S = await svgFacts(q, (await download(q, 'svg')).buf.toString('utf8'));
    t.eq(S.bg, `rgb(${CANVAS[other].join(', ')})`, `${other} theme: SVG background`);
    await openMenu(q);
    const box = await q.getByLabel('Transparent background').boundingBox();
    t.ok(!!box && box.width >= 14 && box.width <= 16 && box.height >= 14 && box.height <= 16, `the checkbox is compact (${box && Math.round(box.width)}x${box && Math.round(box.height)})`);
    await q.getByLabel('Transparent background').focus();
    await q.keyboard.press('Space');
    t.ok(await q.getByLabel('Transparent background').isChecked(), 'the checkbox toggles with the keyboard');
    await q.getByLabel('Transparent background').uncheck();
    await q.getByText('Transparent background').click();
    t.ok(await q.getByLabel('Transparent background').isChecked(), 'a click on the label text checks it');
    const tp = await pixels(q, (await download(q, 'png')).buf);
    t.eq(tp.corner[3], 0, 'transparent: the PNG corner has no alpha');
    t.ok(tp.other > 0.01, 'transparent: the diagram is still drawn');
    const ts = await svgFacts(q, (await download(q, 'svg')).buf.toString('utf8'));
    t.ok(!ts.bg || ts.bg === 'transparent' || /rgba\(0, 0, 0, 0\)/.test(ts.bg), `transparent: the SVG has no background (${ts.bg})`);
    await q.context().close();
  }

  // ---- a phone, and an embedded frame
  {
    const q = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true });
    await open(q, srv.url, targets[targets.length - 1][1]);
    const tog = await q.getByTestId('export-toggle').boundingBox();
    t.ok(!!tog && tog.width >= 44 && tog.height >= 44 && tog.x + tog.width <= 390, 'phone: the Export button is on screen and at least 44 px');
    await openMenu(q);
    for (const b of await q.locator('[data-testid=export] button').all()) {
      const box = await b.boundingBox();
      t.ok(!!box && box.height >= 44 && box.width >= 44 && box.x >= 0 && box.x + box.width <= 390, `phone: a control of the menu is on screen and at least 44 px (${box && Math.round(box.width)}x${box && Math.round(box.height)})`);
    }
    const cb = await q.getByLabel('Transparent background').boundingBox();
    const lb = await q.locator('[data-testid=export] label').boundingBox();
    t.ok(!!cb && cb.width >= 14 && cb.width <= 16 && cb.height >= 14 && cb.height <= 16, `phone: the checkbox is compact (${cb && Math.round(cb.width)}x${cb && Math.round(cb.height)})`);
    t.ok(!!lb && lb.height >= 44 && lb.x >= 0 && lb.x + lb.width <= 390, 'phone: the checkbox label is still a 44 px touch target');
    const cbs = await q.getByLabel('Transparent background').evaluate((e) => { const c = getComputedStyle(e); return { w: parseFloat(c.width), h: parseFloat(c.height) }; });
    t.ok(cbs.w <= 16 && cbs.h <= 16, `phone: the checkbox's computed size is ${cbs.w}x${cbs.h}`);
    await q.touchscreen.tap(lb.x + lb.width - 20, lb.y + lb.height - 4); // the empty end of the 44 px row, away from the box
    t.ok(await q.getByLabel('Transparent background').isChecked(), 'phone: a tap on the row, away from the box, toggles it');
    await q.getByLabel('Transparent background').uncheck();
    t.ok(!!pngSize((await download(q, 'png')).buf), 'phone: PNG downloads');
    await q.context().close();
    const e = await newPage(browser, errors, { viewport: { width: 900, height: 600 } });
    await open(e, srv.url + '?embed=1&data=server', targets[targets.length - 1][1]);
    const em = await download(e, 'svg');
    t.ok(em.name.endsWith('.svg') && em.buf.length > 1000, 'embedded frame: SVG downloads');
    await e.context().close();
  }

  // ---- the menu: closed until asked for, never over the diagram, keyboard, and accessible in the theme on screen
  {
    const q = await newPage(browser, errors);
    await open(q, srv.url, targets[targets.length - 1][1]);
    t.eq(await q.getByTestId('export').count(), 0, 'the menu is closed when the page opens');
    const tog = q.getByTestId('export-toggle');
    t.eq(await tog.textContent(), 'Export', 'the button says "Export"');
    const geo = await q.evaluate(() => {
      const r = (s) => document.querySelector(s).getBoundingClientRect();
      const a = r('.export-toggle'), c = r('.react-flow');
      return { toggleBottom: a.bottom, canvasTop: c.top };
    });
    t.ok(geo.toggleBottom <= geo.canvasTop + 1, 'the Export button is above the canvas, not over the diagram');
    await tog.focus();
    await q.keyboard.press('Enter');
    t.eq(await tog.getAttribute('aria-expanded'), 'true', 'Enter opens the menu');
    await q.keyboard.press('Tab');
    t.eq(await q.evaluate(() => document.activeElement?.getAttribute('data-format')), 'png', 'Tab goes to Download PNG');
    await q.keyboard.press('Tab');
    t.eq(await q.evaluate(() => document.activeElement?.getAttribute('data-format')), 'svg', 'then Download SVG');
    await q.addScriptTag({ path: AXE });
    const viol = await q.evaluate(async () => (await window.axe.run(document, { resultTypes: ['violations'] })).violations.map((v) => `${v.id}[${v.impact}] ${v.nodes[0].target.join(' ')}`));
    t.eq(viol, [], 'axe: no violations with the menu open');
    await q.keyboard.press('Escape');
    t.eq(await q.getByTestId('export').count(), 0, 'Escape closes the menu');
    t.eq(await q.evaluate(() => document.activeElement?.getAttribute('data-testid')), 'export-toggle', 'and focus goes back to the button');
    await tog.click();
    await q.mouse.click(700, 500);
    t.eq(await q.getByTestId('export').count(), 0, 'a click elsewhere closes it');
    await q.context().close();
    // other places the button must not hide the diagram: an embedded frame, narrow
    const e = await newPage(browser, errors, { viewport: { width: 520, height: 600 } });
    await open(e, srv.url + '?embed=1&data=server', targets[targets.length - 1][1]);
    const eg = await e.evaluate(() => ({ a: document.querySelector('.export-toggle').getBoundingClientRect().bottom, c: document.querySelector('.react-flow').getBoundingClientRect().top }));
    t.ok(eg.a <= eg.c + 1, 'embedded, narrow: the Export button is above the canvas too');
    await e.context().close();
  }

  // ---- a failure is a notice; the viewer goes on, and the next export works
  {
    const q = await newPage(browser, errors);
    const [, hash] = targets[targets.length - 1];
    await open(q, srv.url, hash);
    const nodes = await q.locator('.react-flow__node').count();
    const fail = async (what, stub, fmt) => {
      await q.evaluate(stub);
      let got = false;
      q.once('download', () => { got = true; });
      await openMenu(q);
      await q.click(`[data-testid=export] [data-format=${fmt}]`);
      await q.getByTestId('notice').waitFor({ timeout: 20000 });
      const msg = await q.getByTestId('notice').textContent();
      t.ok(/Could not export .+--.+\.(png|svg)/.test(msg) && /Try|Use|reload/i.test(msg), `${what}: a notice that names the file and says what to do: "${msg.replace(/\s+/g, ' ').slice(0, 160)}"`);
      t.ok(!got, `${what}: no file is downloaded`);
      t.eq(await q.locator('.react-flow__node').count(), nodes, `${what}: the diagram is still there`);
      t.ok(await q.evaluate(() => window.__viewer.ready), `${what}: the viewer is ready`);
      t.eq(await q.locator('[data-testid=export] button:disabled').count(), 0, `${what}: the buttons work again`);
      await q.getByTestId('notice').getByRole('button', { name: 'Dismiss' }).click();
    };
    await fail('PNG failure', () => { window.__origToBlob = HTMLCanvasElement.prototype.toBlob; window.__origToUrl = HTMLCanvasElement.prototype.toDataURL;
      HTMLCanvasElement.prototype.toBlob = () => { throw new Error('canvas refused'); }; HTMLCanvasElement.prototype.toDataURL = () => { throw new Error('canvas refused'); }; }, 'png');
    await q.evaluate(() => { HTMLCanvasElement.prototype.toBlob = window.__origToBlob; HTMLCanvasElement.prototype.toDataURL = window.__origToUrl; });
    t.ok(!!pngSize((await download(q, 'png')).buf), 'after a failure the same export works');
    await fail('SVG failure', () => { window.__origSer = XMLSerializer.prototype.serializeToString; XMLSerializer.prototype.serializeToString = () => { throw new Error('serializer refused'); }; }, 'svg');
    await q.evaluate(() => { XMLSerializer.prototype.serializeToString = window.__origSer; });
    t.ok((await download(q, 'svg')).buf.length > 1000, 'after a failure the SVG export works too');
    await q.context().close();
  }

  // the harness collects console errors and page errors of every page: a failed export is handled, not thrown
  t.eq(errors, [], 'no console errors or uncaught exceptions in the export tests');
  return t;
}
