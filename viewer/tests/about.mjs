// Bundled Inter (no network), the About dialog and its third-party notices: desktop, phone, embed, light and dark.
// Run: node tests/run.mjs --only about --data <dir>   (with --theme dark for the dark pass)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';
import { newPage, open, STATIC, T } from './lib.mjs';

const require = createRequire(import.meta.url);
const AXE = require.resolve('axe-core/axe.min.js');
const about = (p) => p.locator('[role=dialog][data-testid=about-dialog]');
const button = (p) => p.locator('[data-testid=about-button]');
const active = (p) => p.evaluate(() => ({ cls: document.activeElement?.className ?? '', label: document.activeElement?.getAttribute('aria-label') ?? '', inside: !!document.activeElement?.closest('[data-testid=about-dialog]') }));

async function axe0(p, label, t) {
  await p.addScriptTag({ path: AXE });
  const res = await p.evaluate(async () => {
    const r = await window.axe.run(document, { resultTypes: ['violations'] });
    return r.violations.map((v) => `${v.id}[${v.impact}] ${v.nodes[0].target.join(' ')}`);
  });
  t.eq(res, [], `axe ${label}: violations`);
}

export default async function aboutTests(browser, srv, F, name) {
  const t = new T(`about:${name}`);
  const errors = [];
  const origin = new URL(srv.url).origin;

  // ---- offline fonts: everything comes from the page's own origin, and Inter is what the page is set in
  {
    const foreign = [];
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await p.context().route('**/*', (route) => {
      const u = route.request().url();
      if (u.startsWith(origin) || u.startsWith('data:') || u.startsWith('blob:')) return route.continue();
      foreign.push(u);
      return route.abort();
    });
    const requested = [];
    p.on('request', (r) => requested.push(new URL(r.url()).pathname));
    await open(p, srv.url, '#/m');
    await p.evaluate(() => document.fonts.load('400 14px Inter').then(() => document.fonts.load('700 14px Inter')));
    const f = await p.evaluate(() => ({
      faces: [...document.fonts].filter((x) => x.family.replace(/"/g, '') === 'Inter').map((x) => `${x.weight}:${x.status}`).sort(),
      check: [document.fonts.check('400 14px Inter'), document.fonts.check('700 14px Inter')],
      body: getComputedStyle(document.body).fontFamily,
      button: getComputedStyle(document.querySelector('button.gear')).fontFamily,
      node: getComputedStyle(document.querySelector('.react-flow__node') ?? document.body).fontFamily,
    }));
    t.eq(f.faces, ['400:loaded', '700:loaded'], 'Inter regular and bold are loaded');
    t.eq(f.check, [true, true], 'document.fonts.check Inter 400 and 700');
    // a workspace with a branding font sets its diagrams in it (branding.mjs); the page and its controls stay in Inter
    const brandFont = F.index.branding ? JSON.parse(fs.readFileSync(path.join(srv.dir, F.index.branding.file), 'utf8')).font : null;
    const nodeFont = brandFont ? f.node === brandFont.family : /^"?Inter"?,/.test(f.node);
    t.ok(/^"?Inter"?,/.test(f.body) && /^"?Inter"?,/.test(f.button) && nodeFont, `Inter is the default for the page, controls and nodes (${f.body}; ${f.button}; ${f.node})`);
    t.eq(foreign, [], 'no request leaves the page origin');
    t.eq(requested.filter((r) => r.endsWith('.woff2')).map((r) => r.replace(/^.*\/(inter-latin-\d+-normal)-[\w-]+\.woff2$/, '$1')).sort(), ['inter-latin-400-normal', 'inter-latin-700-normal'], 'both woff2 files are served from the bundle');
    const css = fs.readdirSync(path.join(STATIC, 'assets')).filter((n) => n.endsWith('.css')).map((n) => fs.readFileSync(path.join(STATIC, 'assets', n), 'utf8')).join('\n');
    t.eq(css.match(/@import|url\(\s*["']?(https?:)?\/\//g), null, 'the bundled CSS imports and references nothing remote');
    const html = fs.readFileSync(path.join(STATIC, 'index.html'), 'utf8');
    t.eq(html.match(/(?:src|href)=["'](?:https?:)?\/\//g), null, 'index.html references nothing remote');
    await p.context().close();
  }

  // ---- desktop: button, dialog, notices, keyboard, close
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    t.eq(await button(p).count(), 1, 'one About button');
    t.eq((await button(p).textContent())?.trim(), 'About', 'the About button has a visible name');
    t.eq(await button(p).getAttribute('aria-expanded'), 'false', 'aria-expanded false when closed');
    const nb = await p.locator('nav.left').boundingBox(), ab = await button(p).boundingBox(), gb = await p.locator('button.gear').boundingBox();
    t.ok(ab.x < nb.x + nb.width / 2 && gb.x > nb.x + nb.width / 2, 'About is bottom-left and the gear stays bottom-right');
    t.ok(Math.abs(ab.y + ab.height / 2 - (gb.y + gb.height / 2)) <= 4, 'About and the gear share a row');
    t.eq(await p.locator('.legal').count(), 0, 'the old font licence link is gone');

    await button(p).focus();
    await p.keyboard.press('Enter');
    t.eq(await about(p).count(), 1, 'Enter on the button opens the dialog');
    t.eq(await button(p).getAttribute('aria-expanded'), 'true', 'aria-expanded true when open');
    const d = about(p);
    t.eq(await d.getAttribute('aria-modal'), 'true', 'the dialog is modal');
    const id = await d.getAttribute('aria-labelledby');
    t.eq(await p.locator('#' + id).textContent(), 'About the buildzr viewer', 'the dialog is named by its heading');
    t.eq((await active(p)).label, 'Close About', 'focus moves into the dialog, to the close button');
    await p.locator('[data-testid=about-notices]').waitFor();
    const text = await p.locator('[data-testid=about-notices]').textContent();
    t.ok(text.includes('SIL OPEN FONT LICENSE Version 1.1') && text.includes('Copyright 2016 The Inter Project Authors'), 'the notices show the Inter licence and copyright');
    t.ok(/@xyflow\/react \d+\.\d+\.\d+/.test(text) && /\nreact 19\./.test(text.replace(/^ +/gm, '')) && text.includes('Eclipse Public License'), 'the notices list the bundled packages');
    const href = await d.locator('a').first().getAttribute('href');
    const r = await p.evaluate((h) => fetch(h).then(async (x) => ({ ok: x.ok, ct: x.headers.get('content-type'), same: new URL(h, location.href).origin === location.origin, body: await x.text() })), href);
    t.ok(r.ok && r.same && r.body === text, 'the plain text link is the same local file the dialog shows');
    t.eq(await p.locator('[data-testid=about-notices]').getAttribute('tabindex'), '0', 'the long notices scroll area is keyboard-focusable');
    t.ok(await p.evaluate(() => getComputedStyle(document.querySelector('[data-testid=about-notices]')).fontFamily.startsWith('ui-monospace')), 'the notices keep the monospace font');
    const box = await d.boundingBox(), vp = p.viewportSize();
    t.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= vp.width && box.y + box.height <= vp.height, 'the dialog fits the viewport');
    await axe0(p, 'desktop/open', t);

    // Tab stays inside: 8 presses forward and 8 back
    let inside = true;
    for (let i = 0; i < 8; i++) { await p.keyboard.press('Tab'); inside &&= (await active(p)).inside; }
    for (let i = 0; i < 8; i++) { await p.keyboard.press('Shift+Tab'); inside &&= (await active(p)).inside; }
    t.ok(inside, 'Tab and Shift+Tab stay inside the dialog');

    await p.keyboard.press('Escape');
    t.eq(await about(p).count(), 0, 'Esc closes the dialog');
    t.eq((await active(p)).cls.includes('about-btn'), true, 'Esc returns focus to the About button');
    t.eq(await p.evaluate(() => location.hash), '#/m', 'opening and closing About leaves the route alone');
    await button(p).click();
    await p.locator('.about-close').click();
    t.eq(await about(p).count(), 0, 'the close button closes it');
    await button(p).click();
    await p.mouse.click(5, 5);
    t.eq(await about(p).count(), 0, 'a click on the backdrop closes it');
    // settings still work next to it
    await p.locator('button.gear').click();
    t.eq(await p.locator('[data-testid=settings-panel]').count(), 1, 'the settings gear still opens its panel');
    await p.context().close();
  }

  // ---- phone: drawer, 44 px targets, the dialog fits, Esc closes only the dialog
  {
    const p = await newPage(browser, errors, { viewport: { width: 390, height: 844 }, hasTouch: true, reducedMotion: 'no-preference' });
    await open(p, srv.url, '#/m');
    await p.locator('button[aria-label="Open model navigation"]').click();
    await p.waitForTimeout(350);
    const ab = await button(p).boundingBox();
    t.ok(ab.width >= 44 && ab.height >= 44, `phone: About is ${ab.width}x${ab.height} (>= 44)`);
    await button(p).tap();
    t.eq(await about(p).count(), 1, 'phone: tap opens the dialog');
    const box = await about(p).boundingBox(), cb = await p.locator('.about-close').boundingBox(), vp = p.viewportSize();
    t.ok(box.x >= 0 && box.y >= 0 && box.x + box.width <= vp.width && box.y + box.height <= vp.height, 'phone: the dialog fits the screen');
    t.ok(cb.width >= 44 && cb.height >= 44, `phone: close is ${cb.width}x${cb.height} (>= 44)`);
    await p.locator('[data-testid=about-notices]').waitFor();
    await axe0(p, 'phone/open', t);
    await p.keyboard.press('Escape');
    t.eq(await about(p).count(), 0, 'phone: Esc closes the dialog');
    t.eq(await p.locator('nav.left[data-open=true]').count(), 1, 'phone: Esc closed only the dialog, not the drawer');
    await p.context().close();
  }

  // ---- embed: reachable through the navigation drawer; same dialog
  {
    const p = await newPage(browser, errors, { reducedMotion: 'no-preference' });
    await p.goto(srv.url + '?embed=1&data=server#/m');
    await p.waitForSelector('[data-testid=live]');
    await p.locator('button[aria-label="Open model navigation"]').click();
    await button(p).click();
    t.eq(await about(p).count(), 1, 'embed: the dialog opens from the drawer');
    await p.locator('[data-testid=about-notices]').waitFor();
    await axe0(p, 'embed/open', t);
    await p.keyboard.press('Escape');
    t.eq(await about(p).count(), 0, 'embed: Esc closes the dialog');
    await p.context().close();
  }

  t.eq(errors, [], 'no console errors in about tests');
  console.log(`  about ${name}: ${t.checks} checks, ${t.fails} failed`);
  return t;
}
