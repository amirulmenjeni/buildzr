// SPIKE: drive the built docs page in Chromium. Usage (container, site served at $URL):
//   node spike/runcode/browser_check.mjs URL SHOTS_DIR WRAPPED_DIR CPY_DIR
// Prints JSON lines: timings, bytes (cold, warm), checks; writes screenshots; compares the data built in Chromium
// with the data the normal build (CPython + Node) wrote for every wrapped snippet.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(path.resolve('viewer/package.json'));
const { chromium } = require('playwright');
const [url, shots, wrappedDir, cpyDir] = process.argv.slice(2);
const log = (o) => console.log(JSON.stringify(o));

const browser = await chromium.launch();

async function bytesOf(page) {
  const cdp = await page.context().newCDPSession(page);
  await cdp.send('Network.enable');
  const reqs = new Map();
  const tally = { total: 0, byHost: {}, files: [] };
  cdp.on('Network.requestWillBeSent', (e) => reqs.set(e.requestId, e.request.url));
  cdp.on('Network.loadingFinished', (e) => {
    const u = reqs.get(e.requestId) || '';
    const host = u.startsWith(url) ? 'docs' : new URL(u).host;
    tally.total += e.encodedDataLength;
    tally.byHost[host] = (tally.byHost[host] || 0) + e.encodedDataLength;
    if (e.encodedDataLength > 20000) tally.files.push([u.replace(url, '').slice(-60), e.encodedDataLength]);
  });
  return tally;
}

async function runBlock(page, i, fi = i) {
  const btn = page.locator('.interactive-run-button').nth(i);
  const t0 = Date.now();
  await btn.click();
  const frame = page.frameLocator('iframe.runcode-viewer').nth(fi);
  await frame.locator('.react-flow__node').first().waitFor({ timeout: 120000 });
  return Date.now() - t0;
}

// ---- 1. desktop, light, cold cache then warm cache (same context: HTTP cache kept)
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light', reducedMotion: 'reduce' });
  let page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  page.on('console', (m) => { if (m.type() === 'error') errors.push(m.text()); });
  page.on('response', (r) => { if (r.status() >= 400) errors.push(r.status() + ' ' + r.url()); });
  const pageLoad = await bytesOf(page);
  await page.goto(url + 'spike-run-code/');
  await page.waitForLoadState('networkidle');
  log({ step: 'page load (before any click)', bytes: pageLoad.total, byHost: pageLoad.byHost });
  const cold = await bytesOf(page);
  await page.evaluate(() => {
    window.__long = 0; window.__longMax = 0;
    new PerformanceObserver((l) => { for (const e of l.getEntries()) { window.__long += e.duration; window.__longMax = Math.max(window.__longMax, e.duration); } })
      .observe({ type: 'longtask', buffered: false });
  });
  const firstMs = await runBlock(page, 0);
  const secondMs = await runBlock(page, 1);
  const thirdMs = await runBlock(page, 2);
  await page.waitForTimeout(500);
  const t = await page.evaluate(() => ({ timings: window.__runcodeTimings, longTasksMs: Math.round(window.__long), longestTaskMs: Math.round(window.__longMax) }));
  log({ step: 'cold: click to first diagram', ms: firstMs, second_ms: secondMs, third_ms: thirdMs, ...t });
  log({ step: 'cold bytes after the three runs', bytes: cold.total, byHost: cold.byHost, big: cold.files });
  // routes the frames opened on, and what each shows
  for (let i = 0; i < 3; i++) {
    const f = page.frameLocator('iframe.runcode-viewer').nth(i);
    const src = await page.locator('iframe.runcode-viewer').nth(i).getAttribute('src');
    const nodes = await f.locator('.react-flow__node').count();
    const sel = await f.locator('[data-selected-id]').first().getAttribute('data-selected-id').catch(() => null);
    log({ step: 'frame ' + i, src: src.replace(/.*index.html/, ''), nodes, selected: sel });
  }
  for (let i = 0; i < 3; i++) {
    await page.locator('.interactive-output-container').nth(i).screenshot({ path: path.join(shots, `desktop-light-${i + 1}.png`) });
  }
  // the page's history did not grow while clicking in the frame
  const h0 = await page.evaluate(() => history.length);
  const f1 = page.frameLocator('iframe.runcode-viewer').nth(1);
  await f1.locator('.react-flow__node:not(.parent)').last().click({ force: true });
  await page.waitForTimeout(300);
  log({ step: 'history length before/after a click in the viewer', before: h0, after: await page.evaluate(() => history.length) });
  // keyboard: Tab from the Run Code button reaches the frame's content
  await page.locator('.interactive-run-button').nth(0).focus();
  const reached = [];
  for (let k = 0; k < 6; k++) {
    await page.keyboard.press('Tab');
    reached.push(await page.evaluate(() => {
      const a = document.activeElement;
      if (a && a.tagName === 'IFRAME') { const d = a.contentDocument.activeElement; return 'iframe> ' + (d ? d.tagName + (d.getAttribute('aria-label') ? '[' + d.getAttribute('aria-label') + ']' : '') : '?'); }
      return a ? a.tagName + '.' + a.className : '?';
    }));
  }
  log({ step: 'Tab order from the first Run Code button', reached });
  // palette toggle to dark while frames are open: they follow
  await page.locator('label[for="__palette_1"], label.md-header__button[for^="__palette"]').first().click().catch(() => {});
  await page.waitForTimeout(500);
  const themes = [];
  for (const fr of page.frames().filter((f) => f.url().includes('/runcode/viewer/'))) themes.push(await fr.evaluate(() => document.documentElement.dataset.theme));
  log({ step: 'after the docs palette toggle', scheme: await page.evaluate(() => document.body.dataset.mdColorScheme), frameThemes: themes });
  log({ step: 'console errors (desktop)', errors });

  // warm: a new page in the same context
  page = await ctx.newPage();
  const warm = await bytesOf(page);
  await page.goto(url + 'spike-run-code/');
  await page.waitForLoadState('networkidle');
  const warmMs = await runBlock(page, 0);
  log({ step: 'warm: click to first diagram', ms: warmMs, bytes: warm.total, byHost: warm.byHost, timings: await page.evaluate(() => window.__runcodeTimings) });

  // ---- 2. the browser build gives the same files as the normal build (every snippet the Node run built)
  const names = fs.readdirSync(cpyDir);
  let same = 0; const diffs = [];
  for (const name of names) {
    const code = fs.readFileSync(path.join(wrappedDir, name + '.py'), 'utf8');
    const files = await page.evaluate((c) => JSON.parse(pyodideInstance.globals.get('browser_build').run_snippet(c, '/rc/cmp')).files, code);
    const want = {};
    const walk = (d, rel) => { for (const f of fs.readdirSync(d)) { const p = path.join(d, f); if (fs.statSync(p).isDirectory()) walk(p, rel + f + '/'); else want[rel + f] = fs.readFileSync(p, 'utf8'); } };
    walk(path.join(cpyDir, name), '');
    const ok = Object.keys(want).length === Object.keys(files).length && Object.entries(want).every(([k, v]) => files[k] === v);
    if (ok) same++; else diffs.push(name);
  }
  log({ step: 'Chromium build vs normal build (CPython + Node ELK)', identical: same, different: diffs.length, diffs });
  await ctx.close();
}

// ---- 3. dark (docs follow the system scheme), desktop
{
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'dark' });
  const page = await ctx.newPage();
  await page.goto(url + 'spike-run-code/');
  await runBlock(page, 1, 0);
  await page.waitForTimeout(800);
  await page.locator('.interactive-code-wrapper').nth(1).screenshot({ path: path.join(shots, 'desktop-dark-2.png') });
  log({ step: 'dark', scheme: await page.evaluate(() => document.body.dataset.mdColorScheme) });
  await ctx.close();
}

// ---- 4. phone
{
  const ctx = await browser.newContext({ viewport: { width: 390, height: 844 }, isMobile: true, hasTouch: true, deviceScaleFactor: 2, colorScheme: 'light' });
  const page = await ctx.newPage();
  await page.goto(url + 'spike-run-code/');
  await runBlock(page, 1, 0);
  await page.waitForTimeout(800);
  await page.locator('.interactive-code-wrapper').nth(1).screenshot({ path: path.join(shots, 'phone-light-2.png') });
  const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
  const phoneLayout = await page.frameLocator('iframe.runcode-viewer').first().locator('.app.phone').count();
  log({ step: 'phone', horizontalOverflowPx: overflow, viewerUsesPhoneLayout: phoneLayout === 1 });
  await page.screenshot({ path: path.join(shots, 'phone-light-page.png') });
  await ctx.close();
}
await browser.close();
