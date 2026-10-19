// SPIKE (Question A): run docs snippets under Pyodide in Node, build the viewer data, write it to OUT/<name>/.
//   node spike/runcode/node_run.mjs OUT SNIPPET.py...
// env: PYODIDE (path of the pyodide npm package), WHEELS (dir with the slim buildzr wheel and the pyhumps wheel)
import fs from 'node:fs';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const here = path.dirname(new URL(import.meta.url).pathname);
const { loadPyodide } = require(path.join(process.env.PYODIDE, 'pyodide.js'));
const { makeElkSync } = require(path.join(here, 'elk_sync.js'));
const ELK = require(path.join(here, '../../buildzr/site/layout/vendor/elk.bundled.js'));
const { wrapSnippet } = require(path.join(here, 'wrap.js'));

const [out, ...snippets] = process.argv.slice(2);
const t = { start: performance.now() };
const py = await loadPyodide({ indexURL: process.env.PYODIDE + '/' });
t.pyodide = performance.now();
await py.loadPackage(['typing-extensions'], { messageCallback: () => {} });
for (const w of fs.readdirSync(process.env.WHEELS).filter((f) => f.endsWith('.whl'))) {
  py.unpackArchive(new Uint8Array(fs.readFileSync(path.join(process.env.WHEELS, w))), "wheel");
}
py.FS.mkdirTree('/rc');
py.FS.writeFile('/rc/browser_build.py', fs.readFileSync(path.join(here, 'browser_build.py')));
globalThis.elkLayoutSync = await makeElkSync(ELK);
t.ready = performance.now();
py.runPython("import sys; sys.path.insert(0, '/rc'); import browser_build");
t.imported = performance.now();
console.log(JSON.stringify({ setup_ms: {
  loadPyodide: Math.round(t.pyodide - t.start), packages_and_wheels: Math.round(t.ready - t.pyodide),
  import_buildzr: Math.round(t.imported - t.ready) } }));
const run = py.globals.get('browser_build').run_snippet;
for (const s of snippets) {
  const name = path.basename(s, '.py');
  const code = wrapSnippet(fs.readFileSync(s, 'utf8'));
  const t0 = performance.now();
  let res;
  try {
    res = JSON.parse(run(code, '/rc/out/' + name));
  } catch (e) {
    console.log(JSON.stringify({ snippet: name, error: String(e.message).split('\n').slice(-3).join(' | ') }));
    continue;
  }
  const wall = Math.round(performance.now() - t0);
  for (const [rel, text] of Object.entries(res.files)) {
    const p = path.join(out, name, rel);
    fs.mkdirSync(path.dirname(p), { recursive: true });
    fs.writeFileSync(p, text);
  }
  console.log(JSON.stringify({ snippet: name, wall_ms: wall, ms: res.ms, focus: res.focus, scenes: res.scenes, views: res.views }));
}
