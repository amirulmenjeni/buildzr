// Opens a deployed site through an element's viewerUrl and reports whether the viewer selected it.
// Usage: node tests/opendeployed.mjs <full viewerUrl> <element id>   (prints one JSON line; used by the Python e2e test)
import { launch, newPage, settle } from './lib.mjs';

const [url, id] = process.argv.slice(2);
const browser = await launch();
const errors = [];
try {
  const p = await newPage(browser, errors);
  await p.goto(url);
  await settle(p);
  const selected = await p.locator(`[data-selected-id="${id}"]`).count();
  const onCanvas = await p.locator(`[data-id="${id}"][data-selected="true"]`).count();
  console.log(JSON.stringify({ selected, onCanvas, errors }));
} finally {
  await browser.close();
}
