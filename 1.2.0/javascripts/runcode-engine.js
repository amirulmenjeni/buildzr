// Run Code engine: Pyodide, the slim buildzr wheel and the synchronous elkjs; builds a code block's workspace in
// memory (buildzr.site.browser.run_snippet). interactive-code.js loads it on the first press of Run Code, as a Web
// Worker (the page stays responsive while Python starts) or, where a worker cannot start, on the page itself.
//
// Worker protocol (same origin only; the page creates the worker from this file):
//   page -> worker  {type: 'start', base: '<absolute URL of docs/runcode/>'}
//                   {type: 'run', id: <n>, code: '<the code block>'}
//   worker -> page  {type: 'started', ms: <setup time>}  |  {type: 'start-failed', message: '...'}
//                   {type: 'result', id: <n>, result: <run_snippet's JSON, parsed>}
// On the page itself: RunCodeEngine.start(base) -> Promise<{ms, run(code) -> result}>.
(function (scope) {
  'use strict';
  const inWorker = typeof WorkerGlobalScope !== 'undefined' && scope instanceof WorkerGlobalScope;

  function load(src) {
    if (inWorker) {
      scope.importScripts(src);
      return Promise.resolve();
    }
    return new Promise((resolve, reject) => {
      const s = document.createElement('script');
      s.src = src;
      s.onload = resolve;
      s.onerror = () => reject(new Error('could not load ' + src));
      document.head.appendChild(s);
    });
  }

  async function fetchOk(url) {
    const r = await fetch(url);
    if (!r.ok) throw new Error(`could not load ${url} (HTTP ${r.status})`);
    return r;
  }

  async function start(base) {
    const t0 = performance.now();
    const manifest = await (await fetchOk(base + 'manifest.json')).json();
    // The file's hash in the URL: a new docs deploy is never mixed with files the browser cached before.
    const url = (path) => base + path + '?v=' + manifest.files[path].slice(0, 12);
    const cdn = `https://cdn.jsdelivr.net/pyodide/v${manifest.pyodide}/full/`;

    // In a worker, elk.bundled.js thinks it is ELK's own worker and takes over self.onmessage, unless it sees a
    // document while it loads and while ELK starts (makeElkSync creates the ELK instance at once).
    let elkReady;
    if (inWorker) scope.document = {};
    try {
      await load(url('elk.bundled.js'));
      await load(url('browser_elk.js'));
      elkReady = scope.makeElkSync(scope.ELK);
    } finally {
      if (inWorker) delete scope.document;
    }
    await load(cdn + 'pyodide.js');
    const [pyodide, wheels, elkLayoutSync] = await Promise.all([
      scope.loadPyodide({ indexURL: cdn }).then(async (py) => {
        await py.loadPackage(['typing-extensions'], { messageCallback: () => {} });
        return py;
      }),
      Promise.all(manifest.wheels.map((w) => fetchOk(url(w)).then((r) => r.arrayBuffer()))),
      elkReady,
    ]);
    scope.elkLayoutSync = elkLayoutSync; // buildzr.site.browser.JsElkRunner calls it through Pyodide's `js`
    for (const w of wheels) pyodide.unpackArchive(new Uint8Array(w), 'wheel');
    const runSnippet = pyodide.pyimport('buildzr.site.browser').run_snippet;
    return { ms: Math.round(performance.now() - t0), run: (code) => JSON.parse(runSnippet(code)) };
  }

  if (!inWorker) {
    scope.RunCodeEngine = { start };
    return;
  }
  let engine = null;
  scope.onmessage = async (e) => {
    const m = e.data || {};
    if (m.type === 'start') {
      engine = engine || start(m.base);
      try {
        scope.postMessage({ type: 'started', ms: (await engine).ms });
      } catch (err) {
        engine = null;
        scope.postMessage({ type: 'start-failed', message: String((err && err.message) || err) });
      }
    } else if (m.type === 'run') {
      let result;
      try {
        result = (await engine).run(m.code);
      } catch (err) {
        result = { ok: false, error: { message: 'Run Code failed: ' + String((err && err.message) || err), line: null, source: '' } };
      }
      scope.postMessage({ type: 'result', id: m.id, result });
    }
  };
})(self);
