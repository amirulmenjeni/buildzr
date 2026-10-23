// Drive the browser demo (docs/demo.md) in Chromium on a built copy of the docs; prints one JSON object per line.
// Called by tests/docs/test_demo_browser.py:  node tests/docs/demo_browser.mjs demo URL
// URL serves the built docs at its root. Playwright and axe-core are those of viewer/node_modules; Pyodide comes from
// cdn.jsdelivr.net.
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(path.resolve(import.meta.dirname, '../../viewer/package.json'));
const { chromium } = require('playwright');
const AXE = fs.readFileSync(require.resolve('axe-core/axe.min.js'), 'utf8');
const log = (o) => console.log(JSON.stringify(o));
const TIMEOUT = 120000;
const PAGE = 'demo/';

const SHOP = `from buildzr.dsl import Workspace, Person, SoftwareSystem, Container

with Workspace('w') as w:
    user = Person('User')
    with SoftwareSystem('Shop') as shop:
        web = Container('Web')
        db = Container('Database')
    user >> 'uses' >> web
    web >> 'reads' >> db
`;

async function open(browser, base, { viewport = { width: 1280, height: 900 }, init, offline = false } = {}) {
  const ctx = await browser.newContext({ viewport, colorScheme: 'light', reducedMotion: 'reduce' });
  if (init) await ctx.addInitScript(init);
  const page = await ctx.newPage();
  const errors = [];
  page.on('pageerror', (e) => errors.push(String(e)));
  const seen = { runcode: [], cdn: [] };
  page.on('request', (r) => {
    const u = r.url();
    if (u.includes('cdn.jsdelivr.net')) seen.cdn.push(u);
    if (u.startsWith(base + 'runcode/') || u.includes('/javascripts/runcode-engine.js')) seen.runcode.push(u.slice(base.length));
  });
  await page.goto(base + PAGE);
  await page.waitForSelector('#buildzr-demo[data-ready="true"]');
  if (offline) await ctx.setOffline(true);
  return { ctx, page, errors, seen };
}

const state = (page) => page.locator('#buildzr-demo').getAttribute('data-state');
const waitState = (page, ...states) => page.waitForFunction((s) => s.includes(document.getElementById('buildzr-demo').dataset.state),
  states, { timeout: TIMEOUT, polling: 50 });
const frame = (page) => page.frameLocator('.demo-frame');
const nodeTexts = async (page) => {
  const nodes = frame(page).locator('.react-flow__node');
  await nodes.first().waitFor({ timeout: TIMEOUT });
  return (await nodes.allInnerTexts()).join(' | ');
};
const setCode = async (page, code) => { await page.locator('#demo-code').fill(code); };
const press = async (page) => { await page.locator('.demo-run').click(); };

async function wide(browser, base) {
  const { ctx, page, errors, seen } = await open(browser, base);
  const code = page.locator('#demo-code');
  // 1. nothing is loaded before the first press, and the first example is in the editor
  const before = await page.evaluate(() => ({
    label: document.querySelector('label[for="demo-code"]').textContent,
    described: document.getElementById('demo-code').getAttribute('aria-describedby'),
    value: document.getElementById('demo-code').value,
    options: [...document.querySelectorAll('#demo-pick option')].map((o) => o.textContent),
    status: document.querySelector('.demo-status').getAttribute('role'),
    stopDisabled: document.querySelector('.demo-stop').disabled,
  }));
  log({ check: 'before the first press', runcode: seen.runcode, cdn: seen.cdn.length, ...before });

  // 2. Ctrl+Enter runs; the focus stays in the editor; the viewer opens where the example says
  await code.click();
  await code.press('Control+Enter');
  await waitState(page, 'drawn', 'error');
  const first = {
    state: await state(page), nodes: (await nodeTexts(page)).length > 0,
    status: await page.locator('.demo-status').innerText(),
    focus: await page.evaluate(() => document.activeElement.id),
    frameSrc: (await page.locator('.demo-frame').getAttribute('src')).replace(/^.*viewer\//, ''),
    thread: await page.evaluate(() => window.__demo.thread),
    busy: await page.locator('.demo-viewer').getAttribute('aria-busy'),
    json: await page.locator('.demo-json summary').innerText(),
  };
  log({ check: 'first run', ...first, runcodeRequests: seen.runcode.length });

  // 3. editing and running again keeps the same viewer (and its place)
  const frameBefore = await page.locator('.demo-frame').elementHandle();
  await setCode(page, SHOP.replace("Person('User')", "Person('Shopper')"));
  await press(page);
  await waitState(page, 'drawn', 'error');
  await page.waitForFunction(async () => true);
  const texts = await (async () => { for (let i = 0; i < 100; i++) { const t = await nodeTexts(page); if (t.includes('Shopper')) return t; await page.waitForTimeout(100); } return await nodeTexts(page); })();
  log({ check: 'second run', state: await state(page), updated: texts.includes('Shopper'), sameFrame: await frameBefore.evaluate((f, n) => f === document.querySelector('.demo-frame'), 0),
    frameCount: await page.locator('.demo-frame').count(), route: await page.locator('.demo-frame').evaluate((f) => f.contentWindow.location.hash) });

  // 4. an error names its line, and the button selects it
  await setCode(page, "user = Person('User')\nsystem = SoftwareSystem('S')\nuser >> 'uses' >> sytem\n");
  await press(page);
  await waitState(page, 'error');
  const errText = await page.locator('.demo-problem').innerText();
  await page.locator('.demo-goto').click();
  log({ check: 'error', text: errText, line: await page.locator('#buildzr-demo').getAttribute('data-error-line'),
    selected: await page.evaluate(() => { const t = document.getElementById('demo-code'); return t.value.slice(t.selectionStart, t.selectionEnd); }),
    focus: await page.evaluate(() => document.activeElement.id), role: await page.locator('.demo-problem').getAttribute('role'),
    diagramKept: (await page.locator('.demo-frame').count()) === 1 });

  // 5. a nothing-to-draw model, and a model with no code
  await setCode(page, "from buildzr.dsl import Workspace\nwith Workspace('empty') as w:\n    pass\n");
  await press(page);
  await waitState(page, 'nothing');
  const nothing = await page.locator('.demo-problem').innerText();
  await setCode(page, '   ');
  await press(page);
  log({ check: 'nothing and empty', nothing, empty: await page.locator('.demo-problem').innerText() });

  // 6. the printed output, and "Copy model JSON"
  await ctx.grantPermissions(['clipboard-read', 'clipboard-write'], { origin: new URL(base).origin });
  await setCode(page, SHOP + "print('hello from the model')\n");
  await press(page);
  await waitState(page, 'drawn');
  await page.locator('.demo-copy-json').click();
  const copied = await page.evaluate(() => navigator.clipboard.readText());
  log({ check: 'extras', printed: await page.locator('.demo-printed summary').innerText(), copiedIsJson: (() => { try { return !!JSON.parse(copied).model; } catch { return false; } })() });

  // 7. examples and Reset
  await page.selectOption('#demo-pick', { label: 'The smallest model' });
  const hello = await code.inputValue();
  await setCode(page, 'x = 1');
  await page.locator('.demo-reset').click();
  log({ check: 'examples', loaded: hello.includes('Web Application'), reset: (await code.inputValue()) === hello, pickBack: await page.inputValue('#demo-pick') });

  // 8. the docs palette toggle: the viewer follows
  await page.locator('label[for^="__palette"]').first().click();
  await page.waitForTimeout(500);
  log({ check: 'theme', scheme: await page.evaluate(() => document.body.dataset.mdColorScheme),
    frameTheme: await page.locator('.demo-frame').evaluate((f) => f.contentDocument.documentElement.dataset.theme) });

  // 9. the draft survives a reload and is not run by itself
  await setCode(page, 'draft = 1\n# a draft of mine');
  await page.waitForTimeout(500);
  const requestsBefore = seen.runcode.length;
  await page.reload();
  await page.waitForSelector('#buildzr-demo[data-ready="true"]');
  await page.waitForTimeout(500);
  log({ check: 'draft', restored: await code.inputValue(), state: await state(page), newRunCodeRequests: seen.runcode.length - requestsBefore,
    frames: await page.locator('.demo-frame').count() });

  // 10. accessibility of the demo (axe-core, WCAG 2 A and AA rules), with a diagram on screen
  await setCode(page, SHOP);
  await press(page);
  await waitState(page, 'drawn');
  await page.addScriptTag({ content: AXE });
  const axe = await page.evaluate(() => axe.run('#buildzr-demo', { runOnly: ['wcag2a', 'wcag2aa', 'wcag21a', 'wcag21aa'] }));
  log({ check: 'axe', violations: axe.violations.map((v) => ({ id: v.id, nodes: v.nodes.map((n) => n.target.join(' ')) })) });
  log({ check: 'page errors wide', errors });
  await ctx.close();
}

async function endlessLoop(browser, base) {
  const { ctx, page, errors } = await open(browser, base, { init: 'window.__demoTimeoutMs = 4000;' });
  await setCode(page, 'while True:\n    pass\n');
  await press(page);
  await waitState(page, 'error');
  const timedOut = await page.locator('.demo-problem').innerText();
  const stillResponsive = await page.evaluate(() => 1 + 1);
  // the demo recovers: a good model runs next
  await setCode(page, SHOP);
  await press(page);
  await waitState(page, 'drawn');
  log({ check: 'time limit', timedOut, stillResponsive, afterwards: await state(page), runIsEnabled: await page.locator('.demo-run').getAttribute('aria-disabled') });

  // Stop, and Esc
  for (const how of ['button', 'escape']) {
    await setCode(page, 'import time\nwhile True:\n    time.sleep(0.05)\n');
    await press(page);
    await page.waitForFunction(() => !document.querySelector('.demo-stop').disabled);
    await page.waitForTimeout(500);
    if (how === 'button') await page.locator('.demo-stop').click();
    else { await page.locator('#demo-code').focus(); await page.keyboard.press('Escape'); }
    await waitState(page, 'stopped');
    const afterStop = { how, status: await page.locator('.demo-status').innerText(), stopDisabled: await page.locator('.demo-stop').isDisabled(), problem: await page.locator('.demo-problem').innerText() };
    await setCode(page, SHOP);
    await press(page);
    await waitState(page, 'drawn');
    log({ check: 'stop', ...afterStop, thenDrawn: await state(page) });
  }
  log({ check: 'page errors loop', errors });
  await ctx.close();
}

async function phone(browser, base) {
  const { ctx, page, errors } = await open(browser, base, { viewport: { width: 390, height: 844 } });
  const layout = await page.evaluate(() => {
    const ed = document.querySelector('.demo-editor').getBoundingClientRect();
    const vw = document.querySelector('.demo-viewer').getBoundingClientRect();
    const t = document.getElementById('demo-code');
    const small = [...document.querySelectorAll('.demo button, .demo select')].filter((b) => b.getBoundingClientRect().height < 40 && getComputedStyle(b).display !== 'none').map((b) => b.className);
    return { stacked: vw.top >= ed.bottom - 1, editorWidth: Math.round(ed.width), fontSize: getComputedStyle(t).fontSize,
      overflowX: document.documentElement.scrollWidth > innerWidth, small };
  });
  await press(page);
  await waitState(page, 'drawn');
  await page.waitForTimeout(300);
  const after = await page.evaluate(() => {
    const r = document.querySelector('.demo-viewer').getBoundingClientRect();
    return { viewerTop: Math.round(r.top), viewerInView: r.top < innerHeight && r.bottom > 0, overflowX: document.documentElement.scrollWidth > innerWidth,
      backShown: getComputedStyle(document.querySelector('.demo-back')).display !== 'none' };
  });
  await page.locator('.demo-back').click();
  log({ check: 'phone', ...layout, after, backFocus: await page.evaluate(() => document.activeElement.id), nodes: (await nodeTexts(page)).length > 0 });
  log({ check: 'page errors phone', errors });
  await ctx.close();
}

async function offline(browser, base) {
  const { ctx, page, errors } = await open(browser, base, { offline: true });
  await page.evaluate(() => window.dispatchEvent(new Event('offline')));
  const note = await page.locator('.demo-offline').isVisible() ? await page.locator('.demo-offline').innerText() : null;
  await press(page);
  await waitState(page, 'error');
  const failed = await page.locator('.demo-problem').innerText();
  const editable = await page.locator('#demo-code').isEditable();
  await ctx.setOffline(false);
  await press(page);
  await waitState(page, 'drawn');
  log({ check: 'offline', note, failed, editable, afterwards: await state(page), noteGone: !(await page.locator('.demo-offline').isVisible()) });
  log({ check: 'page errors offline', errors });
  await ctx.close();
}

async function noWorker(browser, base) {
  const { ctx, page } = await open(browser, base, { init: 'delete window.Worker;' });
  await press(page);
  await waitState(page, 'error');
  log({ check: 'no worker', text: await page.locator('.demo-problem').innerText() });
  await ctx.close();
}

const [mode, base] = process.argv.slice(2);
if (mode !== 'demo') throw new Error('unknown mode ' + mode);
const browser = await chromium.launch();
try {
  await wide(browser, base);
  await endlessLoop(browser, base);
  await phone(browser, base);
  await offline(browser, base);
  await noWorker(browser, base);
} finally {
  await browser.close();
}
