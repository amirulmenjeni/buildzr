// Structurizr themes, icons and branding: the themed and overridden styles are drawn, icons and the logo come from the
// data folder (nothing from another site), the labels are set in the branding font and fit their boxes, and a missing
// or damaged branding file leaves a working viewer. A data set without branding is checked to look as before.
// Run: node tests/run.mjs --only branding --data ../tests/site/fixtures/branded
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { act, mouseClick, newPage, open, serve, T } from './lib.mjs';

const node = (id) => `.react-flow__node[data-id="${id}"]`;
const loadJson = (dir, f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const hex = (rgb) => '#' + rgb.match(/\d+/g).slice(0, 3).map((v) => Number(v).toString(16).padStart(2, '0')).join('');

/** A copy of the data folder `dir` with `edit(branding)` applied to its branding file (null: the file is left out). */
function variant(dir, index, edit) {
  const out = fs.mkdtempSync(path.join(os.tmpdir(), 'buildzr-branding-'));
  fs.cpSync(dir, out, { recursive: true });
  const f = path.join(out, index.branding.file);
  const b = edit(JSON.parse(fs.readFileSync(f, 'utf8')));
  if (b === null) fs.rmSync(f); else fs.writeFileSync(f, JSON.stringify(b));
  return out;
}

/** What the page shows of a node: the fill and stroke of its shape, its text colour and font, its icon. */
const look = (p, id) => p.evaluate((sel) => {
  const el = document.querySelector(sel);
  if (!el) return null;
  const shape = el.querySelector('svg rect, svg path, .boundary-box');
  const cs = shape && getComputedStyle(shape);
  const label = el.querySelector('[data-tier="0"]');
  const img = el.querySelector('img[data-role="icon"]');
  const box = el.getBoundingClientRect();
  const lines = [...el.querySelectorAll('[data-tier]')].map((d) => {
    const r = document.createRange(); r.selectNodeContents(d); const w = r.getBoundingClientRect().width; return w;
  });
  return {
    fill: shape?.tagName === 'DIV' ? cs.backgroundColor : shape?.getAttribute('fill'), stroke: shape?.getAttribute('stroke'),
    color: label && getComputedStyle(label).color, font: label && getComputedStyle(label).fontFamily,
    fit: el.querySelector('[data-fit]')?.dataset.fit ?? null, boxW: box.width, lines,
    icon: img && { src: img.getAttribute('src'), w: img.naturalWidth, shown: img.style.display !== 'none' && img.getBoundingClientRect().width > 0,
                   inline: !!img.closest('[data-tier="0"]'), above: img.getBoundingClientRect().bottom <= (label?.getBoundingClientRect().top ?? 0) + 0.5 },
  };
}, node(id));

async function unbranded(browser, srv, t, errors) {
  const p = await newPage(browser, errors);
  await open(p, srv.url, '#/m');
  const r = await p.evaluate(() => ({
    icons: document.querySelectorAll('img[data-role="icon"]').length, logo: !!document.querySelector('[data-testid="brand-logo"]'),
    fit: document.querySelectorAll('[data-fit]').length, font: getComputedStyle(document.querySelector('.react-flow__node [data-tier="0"]')).fontFamily,
  }));
  t.eq(r, { icons: 0, logo: false, fit: 0, font: 'Inter, sans-serif' }, 'no branding: no icon, no logo, labels in Inter at their size');
  t.ok(!srv.requests.some((q) => q.includes('branding.')), 'no branding: no branding file is asked for');
  await p.context().close();
}

export default async function branding(browser, srv, F, name) {
  const t = new T(`branding:${name}`);
  const errors = [];
  if (!F.index.branding) { await unbranded(browser, srv, t, errors); t.eq(errors, [], 'no console errors or warnings'); return t; }
  const b = loadJson(srv.dir, F.index.branding.file);
  const scene = (key) => loadJson(srv.dir, F.index.scenes[key].file);
  const iconOf = (key, id) => b.images[scene(key).nodes.find((n) => n.id === id).style.icon];
  const origin = new URL(srv.url).origin;

  // 1. the model canvas: icons above leaf labels and before frame names, all from the branding file; the logo; the font
  const p = await newPage(browser, errors);
  const elsewhere = [];
  p.on('request', (r) => { if (!r.url().startsWith(origin) && !r.url().startsWith('data:')) elsewhere.push(r.url()); });
  await open(p, srv.url, '#/m');
  const customer = await look(p, 'customer');
  t.ok(customer.icon?.src === iconOf('landscape', 'customer') && customer.icon.w > 0 && customer.icon.shown, 'customer: its icon is drawn from the branding file');
  t.ok(customer.icon?.inline, 'customer (a person): the icon is before the name');
  for (const id of ['customer', 'shop', 'payments']) {
    const r = await p.evaluate((sel) => { const el = document.querySelector(sel); const b = el.getBoundingClientRect();
      return [...el.querySelectorAll('[data-tier]')].every((d) => { const x = d.getBoundingClientRect(); return x.bottom <= b.bottom + 0.5 && x.top >= b.top - 0.5; }); }, node(id));
    t.ok(r, `${id}: every label line is inside the box`);
  }
  const shop = await look(p, 'shop');
  t.ok(shop.icon?.inline && shop.icon.w > 0 && shop.icon.src === iconOf('landscape', 'shop'), 'shop (a frame): the icon is drawn before its name');
  t.ok((await look(p, 'payments')).icon === null, 'payments: no icon');
  const logo = await p.evaluate(() => { const l = document.querySelector('[data-testid="brand-logo"]'); return l && { src: l.getAttribute('src'), w: l.naturalWidth, alt: l.alt }; });
  t.eq(logo && { ...logo, w: logo.w > 0 }, { src: b.images[b.logo], w: true, alt: `${F.model.workspace.name} logo` }, 'the logo is drawn, with its alt text');
  t.ok(customer.font.includes(b.font.name.split(',')[0].trim()), `labels are set in the branding font: ${customer.font}`);
  t.eq(await p.evaluate(() => getComputedStyle(document.querySelector('.toolbar, header, button') ?? document.body).fontFamily.startsWith('Inter')), true, 'the page chrome stays in Inter');
  t.ok(await p.evaluate(() => document.fonts.status === 'loaded'), 'the fonts were ready when the diagram was drawn');
  for (const id of ['customer', 'payments']) {
    const l = await look(p, id);
    t.ok(l.lines.every((w) => w <= l.boxW + 0.5), `${id}: every label line fits its box (${l.lines.map((w) => w.toFixed(1)).join(', ')} <= ${l.boxW.toFixed(1)}, fit ${l.fit ?? 1})`);
  }

  // 2. inside the shop: the theme's stroke and text colour, the workspace's override of the theme, the relationship style
  await act(p, () => mouseClick(p, 'shop'));
  const api = await look(p, 'shop/api'), gateway = await look(p, 'shop/gateway');
  t.eq([api.stroke, hex(api.color)], ['#3d6fdd', '#3d6fdd'], 'shop/api: the Kubernetes theme sets its stroke and text colour');
  t.eq(api.icon, null, 'shop/api: the theme icon is on another site, so none is drawn');
  t.eq([gateway.fill, hex(gateway.color), gateway.stroke], ['#e8f5e9', '#1b5e20', '#3d6fdd'], 'shop/gateway: the workspace background and text colour win over the theme, the theme stroke stays');
  t.ok(gateway.icon?.src === iconOf('e/shop', 'shop/gateway') && gateway.icon.w > 0, 'shop/gateway: the workspace icon is drawn');
  const charge = await p.evaluate(() => {
    const e = [...document.querySelectorAll('[data-edge]')].find((g) => g.tagName === 'g' && g.dataset.edge.includes('payments'));
    const path_ = e?.querySelector('path.react-flow__edge-path'); return path_ && { stroke: path_.style.stroke, dash: path_.style.strokeDasharray };
  });
  t.ok(charge && hex(charge.stroke) === '#b23c17' && charge.dash !== '', `the relationship style is drawn: ${JSON.stringify(charge)}`);
  t.eq(elsewhere, [], 'nothing is asked of another site');

  // 3. an SVG downloaded from the viewer has the icons in it (the logo is not part of the drawing)
  const toggle = p.getByTestId('export-toggle');
  if ((await toggle.getAttribute('aria-expanded')) !== 'true') await toggle.click();
  const [dl] = await Promise.all([p.waitForEvent('download', { timeout: 30000 }), p.click('[data-testid=export] [data-format=svg]')]);
  const file = path.join(os.tmpdir(), `buildzr-branding-${Date.now()}.svg`);
  await dl.saveAs(file);
  const svg = fs.readFileSync(file, 'utf8');
  fs.rmSync(file, { force: true });
  const icons = (svg.match(/<img\b[^>]*>/g) ?? []).filter((tag) => tag.includes('data-role="icon"'));
  t.ok(icons.length >= 2 && icons.every((tag) => /\ssrc="data:image\//.test(tag)), `the SVG holds the icons as data URIs (${icons.length})`);
  t.ok(!svg.includes('brand-logo'), 'the SVG does not hold the logo');
  await p.context().close();

  // 4. a missing branding file: the diagrams are drawn without icons, logo and font, and the console says why
  const fallbacks = [
    ['missing branding file', (x) => null, /could not be read/],
    ['damaged image', (x) => ({ ...x, images: Object.fromEntries(Object.entries(x.images).map(([k]) => [k, 'data:image/png;base64,AAAA'])) }), /could not be drawn/],
    ['font the computer does not have', (x) => ({ ...x, font: { name: 'Nope Sans', family: '"Nope Sans", "Inter", sans-serif' } }), null],
  ];
  for (const [what, edit, warning] of fallbacks) {
    const dir = variant(srv.dir, F.index, edit);
    const s2 = await serve(dir);
    const errs = [];
    const q = await newPage(browser, errs);
    await open(q, s2.url, '#/m');
    const c = await look(q, 'customer');
    t.ok(c && c.boxW > 0, `${what}: the diagram is drawn`);
    if (what === 'font the computer does not have') t.ok(c.fit === null && c.font.includes('Nope Sans'), `${what}: Inter is used at full size (fit ${c.fit})`);
    else t.ok(!c.icon || !c.icon.shown, `${what}: no broken icon is shown`);
    t.ok(warning ? errs.length > 0 && errs.every((e) => warning.test(e) || /Failed to load resource/.test(e)) : errs.length === 0,
         `${what}: ${warning ? 'the console says why' : 'no warning'} (${errs.join(' | ')})`);
    await q.context().close();
    s2.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
  t.eq(errors, [], 'no console errors or warnings');
  return t;
}
