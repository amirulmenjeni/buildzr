// TEST HELPER ONLY: an open viewer of `buildzr serve --watch` in Chromium, for tests/site/test_watch_browser.py.
//   node live_reload_runner.mjs <workspace URL> [screenshot folder]
// Prints "ready" once the page polls. Then reads one command per line from stdin and answers on stdout:
//   reload   wait for the page to reload by itself: "reloaded" (the route kept) or "route-lost", else "timeout"
//   none     watch for 3 s: "none", or "reloaded" when the page reloaded anyway
//   done     "embed-quiet" when an embed fed by its parent page never polled, else "embed-polled"; then exit
// Exits 77 when Playwright or its Chromium is not installed (the test is skipped).
import path from 'node:path';
import readline from 'node:readline';
import { createRequire } from 'node:module';
import { fileURLToPath } from 'node:url';

const ROOT = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..', '..');
let chromium;
try {
  ({ chromium } = createRequire(path.join(ROOT, 'viewer', 'package.json'))('playwright'));
} catch {
  process.exit(77);
}
const [url, shots] = process.argv.slice(2);
let browser;
try {
  browser = await chromium.launch();
} catch {
  process.exit(77);
}
const say = (line) => process.stdout.write(line + '\n');
const until = async (test, ms) => {
  const end = Date.now() + ms;
  while (Date.now() < end) {
    if (test()) return true;
    await new Promise((r) => setTimeout(r, 50));
  }
  return test();
};

const page = await browser.newPage();
let loads = 0;
let polls = 0;
page.on('load', () => { loads += 1; });
let crashed = false;
let last = '';
page.on('crash', () => { crashed = true; });
page.on('request', (r) => { if (r.method() === 'HEAD' && r.url().endsWith('/build.json')) polls += 1; });
page.on('response', (r) => {
  if (r.request().method() === 'HEAD' && r.url().endsWith('/build.json')) last = `${r.status()} ${r.headers()['x-buildzr-build']}`;
});
await page.goto(url);
await page.waitForSelector('#root > *');
const route = await page.evaluate(() => location.hash);
let shot = 0;
const snap = async () => { if (shots) await page.screenshot({ path: path.join(shots, `live-${++shot}.png`) }); };
await snap();

const embed = await browser.newPage();
let embedPolls = 0;
embed.on('request', (r) => { if (r.method() === 'HEAD' && r.url().endsWith('/build.json')) embedPolls += 1; });
await embed.goto(url + '?embed=1');

if (!(await until(() => polls > 0, 10000))) { say('no-poll'); process.exit(1); }
say('ready');

const lines = readline.createInterface({ input: process.stdin });
for await (const command of lines) {
  const before = loads;
  if (command === 'reload') {
    if (!(await until(() => loads > before || crashed, 20000)) || crashed) {
      say(crashed ? 'crashed' : `timeout after ${polls} polls, last ${last}`);
      continue;
    }
    await page.waitForSelector('#root > *');
    await snap();
    say((await page.evaluate(() => location.hash)) === route ? 'reloaded' : 'route-lost');
  } else if (command === 'none') {
    await until(() => loads > before, 3000);
    say(loads > before ? 'reloaded' : 'none');
  } else if (command === 'done') {
    say(embedPolls === 0 ? 'embed-quiet' : 'embed-polled');
    break;
  }
}
lines.close();
await browser.close();
process.exit(0);
