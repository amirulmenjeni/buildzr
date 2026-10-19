// Drive the built docs in Chromium (Playwright of viewer/node_modules, as the viewer tests do) and press Run Code.
// Called by tests/docs/browser.py; prints one JSON object per line.
//
//   node tests/docs/runcode_browser.mjs blocks URL PAGE...   every Run Code block of each page (PAGE: 'user-guide/views/')
//   node tests/docs/runcode_browser.mjs smoke URL PAGE        the smoke checks of test_runcode_browser.py on PAGE
//   node tests/docs/runcode_browser.mjs measure URL PAGE      first press, next block, repeat visit, bytes, long tasks
//
// URL serves the built docs (mkdocs build output) at its root. Pyodide comes from cdn.jsdelivr.net.
import path from 'node:path';
import { createRequire } from 'node:module';
import { pathToFileURL } from 'node:url';

const require = createRequire(path.resolve(import.meta.dirname, '../../viewer/package.json'));
const { chromium } = require('playwright');
const log = (o) => console.log(JSON.stringify(o));
const TIMEOUT = 120000;
// The copy button mkdocs-material puts on a code block (9.7: in a nav; older: .md-clipboard).
const COPY_CODE = '.md-code__button[data-md-type="copy"], .md-clipboard';

/** Press block `i`'s Run Code and wait until it has finished; returns its state and what it shows. */
export async function runBlock(page, i) {
  const wrapper = page.locator('.runcode').nth(i);
  const t0 = Date.now();
  await wrapper.locator('.runcode-run').click();
  await page.waitForFunction((i) => {
    const w = document.querySelectorAll('.runcode')[i];
    return w.dataset.state && w.dataset.state !== 'running';
  }, i, { timeout: TIMEOUT, polling: 50 });
  const ms = Date.now() - t0;
  const info = await wrapper.evaluate((w) => ({
    state: w.dataset.state,
    errorLine: w.dataset.errorLine ? Number(w.dataset.errorLine) : null,
    error: w.querySelector('.runcode-error') ? w.querySelector('.runcode-error').innerText : null,
    firstLine: w.querySelector('pre code').innerText.split('\n').find((l) => l.trim()) || '',
  }));
  let nodes = 0;
  if (info.state === 'drawn') {
    const frame = page.frameLocator('.runcode-frame').nth(await frameIndex(page, i));
    await frame.locator('.react-flow__node').first().waitFor({ timeout: TIMEOUT });
    nodes = await frame.locator('.react-flow__node').count();
  }
  return { block: i, ms, nodes, ...info };
}

async function frameIndex(page, i) {
  return page.evaluate((i) => {
    const frames = [...document.querySelectorAll('.runcode-frame')];
    return frames.indexOf(document.querySelectorAll('.runcode')[i].querySelector('.runcode-frame'));
  }, i);
}

/** Every Run Code block of `pageUrl`, one after the other. */
export async function runPageBlocks(browser, pageUrl) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  await page.goto(pageUrl);
  const count = await page.locator('.runcode').count();
  const results = [];
  for (let i = 0; i < count; i++) results.push(await runBlock(page, i));
  await ctx.close();
  return { results, errors };
}

function watchRequests(page, base) {
  const seen = { runcode: [], cdn: [], bytes: 0, byHost: {} };
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('cdn.jsdelivr.net')) seen.cdn.push(u);
    if (u.startsWith(base + 'runcode/') || u.includes('/javascripts/runcode-engine.js')) seen.runcode.push(u.slice(base.length));
  });
  return seen;
}

/** Bytes over the network (encoded, with headers) of the page and its workers, per host; served from the
 * browser cache: 0. */
function countBytes(page, base) {
  const tally = { total: 0, byHost: {}, requests: 0 };
  page.context().on('requestfinished', async (req) => {
    const u = req.url();
    if (!u.startsWith('http')) return;
    const res = await req.response();
    if (!res) return;
    const s = await req.sizes().catch(() => null);
    const n = s ? s.responseBodySize + s.responseHeadersSize : 0;
    const host = u.startsWith(base) ? 'docs' : new URL(u).host;
    tally.total += n;
    tally.requests++;
    tally.byHost[host] = (tally.byHost[host] || 0) + n;
  });
  return tally;
}

const where = (page, i) => page.evaluate((i) => {
  const h = document.querySelector('.md-header').getBoundingClientRect().bottom;
  const r = document.querySelectorAll('.runcode-output')[i].getBoundingClientRect();
  return { headerBottom: Math.round(h), top: Math.round(r.top), bottom: Math.round(r.bottom), innerHeight,
    topInView: r.height > 0 && r.top >= h - 1 && r.top < innerHeight,
    atPageEnd: Math.ceil(scrollY + innerHeight) >= document.documentElement.scrollHeight - 1 };
}, i);

async function smoke(browser, base, pagePath) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, colorScheme: 'light', reducedMotion: 'reduce' });
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(base).origin });
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const seen = watchRequests(page, base);
  await page.goto(base + pagePath);
  await page.waitForLoadState('networkidle');
  log({ check: 'before the first press', runcode: seen.runcode, cdn: seen.cdn.length, blocks: await page.locator('.runcode').count() });

  // labels: the code's copy button and ours say what they copy
  const labels = await page.evaluate((COPY_CODE) => {
    const w = document.querySelector('.runcode');
    const md = w.querySelector(COPY_CODE);
    return { materialCopyTitle: md && md.getAttribute('title'), run: w.querySelector('.runcode-run').textContent,
      runTitle: w.querySelector('.runcode-run').title };
  }, COPY_CODE);
  // the copy button of the code copies what is shown (no hidden # focus: line)
  await page.locator('.runcode').first().locator('pre').hover();
  await page.locator('.runcode').first().locator(COPY_CODE).click();
  const copiedCode = await page.evaluate(() => navigator.clipboard.readText());
  // what is shown: the source without its hidden lines
  const shownCode = await page.evaluate(() => [...document.querySelector('.runcode pre code').querySelectorAll(':scope > span[id^="__span"]')]
    .filter((s) => getComputedStyle(s).display !== 'none').map((s) => s.textContent.replace(/\n$/, '')).join('\n'));
  log({ check: 'code copy', ...labels, copiedHasFocus: /#\s*focus:/.test(copiedCode), copiedIsShown: copiedCode.trimEnd() === shownCode.trimEnd(),
    sourceHasFocus: await page.evaluate(() => /#\s*focus:/.test(document.querySelector('.runcode pre code').textContent)) });

  await page.evaluate(() => window.scrollTo({ top: 0, behavior: 'instant' }));
  const first = await runBlock(page, 0);
  const firstWhere = await where(page, 0);
  const focus = await page.evaluate(() => {
    const a = document.activeElement;
    return { tag: a.tagName, cls: a.className, label: a.getAttribute('aria-label') };
  });
  const frameSrc = await page.locator('.runcode-frame').first().getAttribute('src');
  log({ check: 'first block', ...first, where: firstWhere, focus, frameSrc: frameSrc.replace(/^.*viewer\//, ''),
    thread: await page.evaluate(() => window.__runcode.thread), runcodeRequests: seen.runcode.length, cdnRequests: seen.cdn.length });

  const copy = await page.evaluate(() => {
    const w = document.querySelectorAll('.runcode')[0];
    const b = w.querySelector('.runcode-copy-json');
    const d = w.querySelector('.runcode-json');
    return { text: b.textContent, title: b.title, jsonOpen: d.open, summary: d.querySelector('summary').textContent,
      status: w.querySelector('.runcode-status').getAttribute('role'), toggle: w.querySelector('.runcode-toggle').textContent };
  });
  await page.locator('.runcode-copy-json').first().click();
  const copiedJson = await page.evaluate(() => navigator.clipboard.readText());
  log({ check: 'model JSON control', ...copy, after: await page.locator('.runcode-copy-json').first().textContent(),
    copiedIsJson: (() => { try { return !!JSON.parse(copiedJson).model; } catch { return false; } })() });

  const count = await page.locator('.runcode').count();
  for (let i = 1; i < count; i++) {
    const r = await runBlock(page, i);
    const errorLineText = r.errorLine ? await page.locator('.runcode').nth(i).locator('.runcode-error-line').innerText().catch(() => null) : null;
    log({ check: 'block', ...r, errorLineText, where: await where(page, i) });
  }

  // "Open in a new tab" (the viewer's button, embed contract section 5): the full viewer with the docs page's data
  const button = page.frameLocator('.runcode-frame').first().locator('[data-testid="open-new-tab"]');
  const newTab = { button: await button.count(), label: await button.getAttribute('title').catch(() => null) };
  if (newTab.button) {
    const [tab] = await Promise.all([ctx.waitForEvent('page'), button.click()]);
    await tab.locator('.react-flow__node').first().waitFor({ timeout: 30000 });
    Object.assign(newTab, { url: tab.url().replace(/^.*viewer\//, ''), nodes: await tab.locator('.react-flow__node').count() });
    await tab.close();
    // a tab whose opener page is gone says what to do
    const orphan = await ctx.newPage();
    await orphan.goto(base + 'runcode/viewer/index.html?handoff=0123456789abcdef0123456789abcdef#/m');
    const alert = orphan.getByText('Go back to that page', { exact: false });
    await alert.first().waitFor({ timeout: 15000 }).catch(() => {});
    newTab.openerGoneMessage = (await alert.count()) ? await alert.first().innerText() : null;
    await orphan.close();
  }
  log({ check: 'new tab', ...newTab });

  // the docs palette toggle: every diagram follows
  await page.locator('label[for^="__palette"]').first().click();
  await page.waitForTimeout(500);
  const themes = [];
  for (const f of page.frames().filter((f) => f.url().includes('/runcode/viewer/'))) {
    themes.push(await f.evaluate(() => document.documentElement.dataset.theme));
  }
  log({ check: 'theme', scheme: await page.evaluate(() => document.body.dataset.mdColorScheme), frameThemes: themes });
  log({ check: 'page errors', errors });
  await ctx.close();
}

async function measure(browser, base, pagePath, mainThread) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  let page = await ctx.newPage();
  const cold = countBytes(page, base);
  await page.goto(base + pagePath);
  await page.waitForLoadState('networkidle');
  const pageLoad = { ...cold, byHost: { ...cold.byHost } };
  await page.evaluate((main) => {
    window.__runcodeForceMainThread = main;
    window.__long = []; // long tasks on the page's main thread
    new PerformanceObserver((l) => { for (const e of l.getEntries()) window.__long.push(Math.round(e.duration)); }).observe({ type: 'longtask' });
  }, mainThread);
  const a = await runBlock(page, 0);
  const b = await runBlock(page, 1);
  await page.waitForTimeout(300);
  const long = await page.evaluate(() => window.__long);
  const stats = await page.evaluate(() => window.__runcode);
  log({ measure: mainThread ? 'main thread' : 'worker', thread: stats.thread, setupMs: stats.setupMs, firstPressMs: a.ms, nextBlockMs: b.ms,
    longTasks: { count: long.length, totalMs: long.reduce((x, y) => x + y, 0), maxMs: Math.max(0, ...long) },
    pageLoadBytes: pageLoad.total, runCodeBytes: cold.total - pageLoad.total,
    runCodeByHost: Object.fromEntries(Object.entries(cold.byHost).map(([h, n]) => [h, n - (pageLoad.byHost[h] || 0)]).filter(([, n]) => n > 0)) });
  await ctx.close();
}

/** A second visit in the same browser (HTTP cache kept): what Run Code costs then. */
async function measureRepeat(browser, base, pagePath, mainThread) {
  const ctx = await browser.newContext({ viewport: { width: 1280, height: 900 }, reducedMotion: 'reduce' });
  let page = await ctx.newPage();
  await page.goto(base + pagePath);
  await page.evaluate((main) => { window.__runcodeForceMainThread = main; }, mainThread);
  await runBlock(page, 0);
  await page.close();
  page = await ctx.newPage();
  const warm = countBytes(page, base);
  await page.goto(base + pagePath);
  await page.waitForLoadState('networkidle');
  await page.evaluate((main) => { window.__runcodeForceMainThread = main; }, mainThread);
  const w = await runBlock(page, 0);
  log({ measure: (mainThread ? 'main thread' : 'worker') + ', repeat visit', firstPressMs: w.ms, runCodeBytes: warm.total, byHost: warm.byHost });
  await ctx.close();
}

const [mode, base, ...pages] = process.argv.slice(2);
if (import.meta.url === pathToFileURL(process.argv[1]).href) {
  const browser = await chromium.launch();
  try {
    if (mode === 'blocks') {
      for (const p of pages) log({ page: p, ...(await runPageBlocks(browser, base + p)) });
    } else if (mode === 'smoke') {
      await smoke(browser, base, pages[0]);
    } else if (mode === 'measure') {
      for (const main of [false, true]) {
        await measure(browser, base, pages[0], main);
        await measureRepeat(browser, base, pages[0], main);
      }
    } else {
      throw new Error('unknown mode ' + mode);
    }
  } finally {
    await browser.close();
  }
}
