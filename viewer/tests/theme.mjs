// Theme: system / light / dark, the settings control, persistence, no flash of the wrong theme, and the contrast of what
// is really drawn (chrome by axe; box text, frame names, arrows and their labels measured from the DOM) in both themes.
// Run: node tests/run.mjs --only theme --data <dir>
import { createRequire } from 'node:module';
import { newPage, open, act, mouseClick, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const KEY = 'buildzr-ui:settings';
const themeOf = (p) => p.evaluate(() => [document.documentElement.dataset.theme, window.__viewer?.theme]);

/** axe, 0 violations. `chromeOnly`: the canvas is left out (under a search, what does not match is dimmed on purpose). */
async function axe0(p, label, t, chromeOnly = false) {
  await p.addScriptTag({ path: AXE });
  const res = await p.evaluate(async (c) => (await window.axe.run(c ? { exclude: [['.react-flow__nodes']] } : document, { resultTypes: ['violations'] })).violations.map((v) => `${v.id}[${v.impact}] ${v.nodes[0].target.join(' ')}`), chromeOnly);
  t.eq(res, [], `axe ${label}: violations`);
}

/** Contrast of what is drawn: computed colours from the DOM, blended by this test's own code (not theme.ts). */
const measure = (p) => p.evaluate(() => {
  const rgb = (s) => { const m = /rgba?\(([\d.]+),\s*([\d.]+),\s*([\d.]+)(?:,\s*([\d.]+))?/.exec(s); return m ? [+m[1], +m[2], +m[3], m[4] === undefined ? 1 : +m[4]] : null; };
  const hexRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
  const col = (s) => (s.startsWith('#') ? [...hexRgb(s.length === 4 ? '#' + [...s.slice(1)].map((c) => c + c).join('') : s), 1] : rgb(s));
  const over = (top, bottom, a = top[3]) => [0, 1, 2].map((i) => bottom[i] + (top[i] - bottom[i]) * a);
  const L = (c) => { const v = c.slice(0, 3).map((x) => x / 255).map((x) => (x <= 0.03928 ? x / 12.92 : ((x + 0.055) / 1.055) ** 2.4)); return 0.2126 * v[0] + 0.7152 * v[1] + 0.0722 * v[2]; };
  const cr = (a, b) => { const [x, y] = [L(a), L(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const canvas = rgb(getComputedStyle(document.querySelector('.center')).backgroundColor);
  // what is behind a node: the canvas with every expanded frame it sits in (their fill at their fill-opacity) on top
  const behind = (el) => {
    let bg = canvas;
    const frames = [];
    for (let n = el.parentElement?.closest('.react-flow__node'); n; n = n.parentElement?.closest('.react-flow__node')) frames.unshift(n);
    // React Flow renders nodes flat; parents come from data-id prefixes
    const id = el.dataset.id;
    for (const f of document.querySelectorAll('.react-flow__node')) {
      const fid = f.dataset.id;
      if (fid !== id && id.startsWith(fid + '/') && f.querySelector('[data-expanded=true]')) frames.push(f);
    }
    frames.sort((a, b) => a.dataset.id.length - b.dataset.id.length);
    for (const f of frames) {
      const shape = f.querySelector('svg rect, svg path');
      if (shape) bg = over(col(shape.getAttribute('fill')), bg, +(shape.getAttribute('fill-opacity') ?? 1));
    }
    return bg;
  };
  const out = { text: [], frames: [], boxes: [], arrows: [], labels: [] };
  for (const n of document.querySelectorAll('.react-flow__node')) {
    const box = n.querySelector('.c4el, .c4b');
    if (!box || parseFloat(box.style.opacity || '1') < 0.99) continue; // dimmed context is not judged
    const bg = behind(n);
    const label = box.querySelector('[data-tier="0"]')?.parentElement;
    const color = label ? rgb(getComputedStyle(label).color) : null;
    if (box.dataset.expanded === 'true') {
      const shape = box.querySelector('svg rect, svg path');
      const fbg = shape ? over(col(shape.getAttribute('fill')), bg, +(shape.getAttribute('fill-opacity') ?? 1)) : bg;
      if (color && label.parentElement && parseFloat(getComputedStyle(label).opacity) > 0.99) out.frames.push([n.dataset.id, cr(color, fbg)]);
      if (shape) out.boxes.push([n.dataset.id + ' (frame border)', cr(col(shape.getAttribute('stroke')), fbg)]);
    } else if (box.classList.contains('c4b')) {
      const b = box.querySelector('.boundary-box');
      const fill = rgb(getComputedStyle(b).backgroundColor);
      if (color) out.text.push([n.dataset.id, cr(color, over(fill, bg))]);
      out.boxes.push([n.dataset.id + ' (boundary border)', cr(rgb(getComputedStyle(b).borderTopColor), bg)]);
    } else {
      const shape = box.querySelector('svg rect, svg path');
      if (!shape) continue;
      const fill = col(shape.getAttribute('fill'));
      if (color) out.text.push([n.dataset.id, cr(color, fill)]);
      out.boxes.push([n.dataset.id, Math.max(cr(fill, bg), cr(col(shape.getAttribute('stroke')), bg))]);
    }
  }
  for (const g of document.querySelectorAll('g[data-edge]')) {
    if (parseFloat(g.style.opacity || '1') < 0.99) continue;
    const path = g.querySelector('path.react-flow__edge-path');
    if (path) out.arrows.push([g.dataset.edge, cr(rgb(getComputedStyle(path).stroke), canvas)]);
  }
  for (const l of document.querySelectorAll('.edge-label')) {
    if (parseFloat(l.style.opacity || '1') < 0.99) continue;
    const bg = over(rgb(getComputedStyle(l).backgroundColor), canvas);
    out.labels.push([l.dataset.edge, cr(rgb(getComputedStyle(l).color), bg)]);
  }
  return out;
});

function judge(t, m, label) {
  const worst = (xs) => xs.reduce((a, x) => (x[1] < a[1] ? x : a), ['-', Infinity]);
  for (const [k, min] of [['text', 4.5], ['frames', 4.5], ['labels', 4.5], ['boxes', 3], ['arrows', 3]]) {
    const bad = m[k].filter((x) => x[1] < min);
    t.eq(bad.map((x) => `${x[0]} ${x[1].toFixed(2)}`), [], `${label}: ${k} below ${min}:1`);
  }
  return Object.fromEntries(Object.entries(m).map(([k, xs]) => [k, xs.length ? `${xs.length}, min ${worst(xs)[1].toFixed(2)}` : '0']));
}

export default async function theme(browser, srv, F, name) {
  const t = new T(`theme:${name}`);
  const errors = [];
  const rows = [];

  // ---- system: follows prefers-color-scheme, live
  {
    const p = await newPage(browser, errors, { colorScheme: 'light' });
    await open(p, srv.url, '#/m');
    t.eq(await themeOf(p), ['light', 'light'], 'system + light device: light');
    await p.emulateMedia({ colorScheme: 'dark' });
    await p.waitForFunction(() => document.documentElement.dataset.theme === 'dark');
    t.eq(await themeOf(p), ['dark', 'dark'], 'the device turns dark: the viewer follows without a reload');
    t.eq(await p.evaluate(() => getComputedStyle(document.body).backgroundColor), 'rgb(15, 17, 21)', 'dark page background');
    await p.context().close();
  }

  // ---- the settings control: radio group, stored, reload, back to system
  {
    const p = await newPage(browser, errors, { colorScheme: 'light' });
    await open(p, srv.url, '#/m');
    await p.locator('button.gear').click();
    const group = p.locator('fieldset[data-setting=theme]');
    t.eq(await group.locator('legend').textContent(), 'Theme', 'Theme control in the settings panel');
    t.eq(await group.locator('input[type=radio]').count(), 3, 'three choices: system, light, dark');
    t.eq(await group.locator('input:checked').getAttribute('value'), 'system', 'default: system');
    await group.locator('input[value=dark]').check();
    t.eq(await themeOf(p), ['dark', 'dark'], 'Dark: dark at once');
    t.eq(JSON.parse(await p.evaluate((k) => localStorage.getItem(k), KEY)).theme, 'dark', 'stored with the other settings');
    await axe0(p, 'dark, settings open', t);
    // keyboard: arrows move within the radio group
    await group.locator('input[value=dark]').focus();
    await p.keyboard.press('ArrowLeft');
    t.eq(await themeOf(p), ['light', 'light'], 'keyboard: arrow key picks Light');
    await p.keyboard.press('ArrowRight');
    await p.keyboard.press('Escape');
    await p.reload(); await p.waitForFunction(() => window.__viewer?.ready === true);
    t.eq(await themeOf(p), ['dark', 'dark'], 'reload keeps Dark');
    await p.locator('button.gear').click();
    await p.locator('fieldset[data-setting=theme] input[value=system]').check();
    t.eq(await themeOf(p), ['light', 'light'], 'System on a light device: light');
    await p.context().close();
  }

  // ---- no flash: the theme is on <html> before the viewer's script runs
  {
    const p = await newPage(browser, errors, { colorScheme: 'light' });
    await p.addInitScript((k) => localStorage.setItem(k, '{"theme":"dark"}'), KEY);
    let release;
    const held = new Promise((r) => { release = r; });
    await p.route('**/assets/*.js', async (r) => { await held; await r.continue(); });
    await p.goto(srv.url + '#/m', { waitUntil: 'commit' }); // the module script is held: DOMContentLoaded waits for it
    await p.waitForFunction(() => document.body && [...document.styleSheets].some((s) => { try { return s.cssRules.length > 0; } catch { return false; } }));
    const early = await p.evaluate(() => [document.documentElement.dataset.theme, getComputedStyle(document.body).backgroundColor, !!window.__viewer]);
    t.eq(early, ['dark', 'rgb(15, 17, 21)', false], 'before the script: already dark (stored Dark on a light device)');
    release();
    await p.waitForFunction(() => window.__viewer?.ready === true, null, { timeout: 20000 });
    t.eq(await themeOf(p), ['dark', 'dark'], 'after the script: still dark');
    await p.context().close();
  }

  // ---- contrast of the drawing, both themes: landscape, every expandable element expanded, each authored view; axe on the chrome
  for (const scheme of ['light', 'dark']) {
    const at = async (hash, where, fn) => {
      const p = await newPage(browser, errors, { colorScheme: scheme });
      await open(p, srv.url, hash);
      rows.push({ theme: scheme, where, ...judge(t, await measure(p), `${scheme} ${where}`) });
      if (fn) await fn(p);
      await p.context().close();
    };
    await at('#/m', 'landscape', (p) => axe0(p, `${scheme} landscape`, t));
    for (const id of F.expandable) await at('#/m/' + id, id);
    for (const v of F.model.views.slice(0, 6)) await at('#/v/' + encodeURIComponent(v.key), 'view ' + v.key);
    // the inspector open after a click, and a search with matches
    const first = F.els[0];
    await at('#/m', 'after a click', async (p) => { await act(p, () => mouseClick(p, first.id)).catch(() => undefined); await axe0(p, `${scheme} after a click`, t); });
    await at('#/m?q=' + encodeURIComponent(first.name.split(' ')[0]), 'search', (p) => axe0(p, `${scheme} search (chrome; the dimmed canvas is excluded)`, t, true));
  }
  console.table(rows);
  t.eq(errors, [], 'no console errors in theme tests');
  console.log(`  theme ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
