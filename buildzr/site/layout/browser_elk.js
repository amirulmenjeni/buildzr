// Synchronous elkjs for the browser: the "Run Code" button of the docs (buildzr/site/browser.py) and nothing else.
//
// In the browser there is no Node process to run runner.mjs, and Python under Pyodide cannot wait for a Promise in
// the middle of the layout. elk.layout() is async only because elkjs's fake worker defers its reply with
// setTimeout; the dispatcher behind it is synchronous. makeElkSync() makes a second dispatcher whose postMessage
// just keeps the reply, so a layout returns at once. Same request as elk.layout(graph) (layoutOptions {}, logging
// and timing off), so the positions are the ones runner.mjs gives (tests/site/test_browser.py checks it).
// This reads elkjs internals: it is written for the vendored elkjs 0.12.0 (vendor/elk.bundled.js, sha256 pinned).
//
//   const elkLayoutSync = await makeElkSync(ELK);   // ELK: the constructor of elk.bundled.js
//   elkLayoutSync('{"name": <ELK graph>, ...}')     // -> '{"name": {"graph": <laid out>, "ms": n} | {"error": "..."}}'
function makeElkSync(ELK) {
  const elk = new ELK();
  const warmup = elk.layout({
    id: 'root', layoutOptions: { 'elk.algorithm': 'layered' },
    children: [{ id: 'a', width: 10, height: 10 }, { id: 'b', width: 10, height: 10 }],
    edges: [{ id: 'e', sources: ['a'], targets: ['b'] }],
  });
  const Dispatcher = elk.worker.worker.dispatcher.constructor;
  let reply = null;
  const dispatcher = new Dispatcher({ postMessage: (m) => { reply = m; } });
  const layoutOne = (graph) => {
    reply = null;
    dispatcher.saveDispatch({
      data: { id: 0, cmd: 'layout', graph, layoutOptions: {}, options: { logging: false, measureExecutionTime: false } },
    });
    if (!reply) throw new Error('ELK gave no reply');
    if (reply.error) throw reply.error;
    return reply.data;
  };
  const elkLayoutSync = (json) => {
    const res = {};
    for (const [name, graph] of Object.entries(JSON.parse(json))) {
      try {
        const t0 = performance.now();
        const out = layoutOne(graph);
        res[name] = { graph: out, ms: performance.now() - t0 };
      } catch (e) {
        res[name] = { error: String(e && e.message ? e.message : e) };
      }
    }
    return JSON.stringify(res);
  };
  return warmup.then(() => elkLayoutSync);
}
if (typeof module !== 'undefined') module.exports = { makeElkSync };
