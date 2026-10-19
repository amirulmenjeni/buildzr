// SPIKE: call elkjs synchronously, so Python (Pyodide) can use it like the Node runner (runner.mjs).
// elk.layout() is async only because the fake worker defers with setTimeout; the dispatcher behind it is
// synchronous. We create a second dispatcher whose postMessage just records the reply.
// Same message as elk.layout(graph): layoutOptions {} (the default), logging and timing off.
function makeElkSync(ELK) {
  const elk = new ELK();
  const warmup = elk.layout({
    id: 'root', layoutOptions: { 'elk.algorithm': 'layered' },
    children: [{ id: 'a', width: 10, height: 10 }, { id: 'b', width: 10, height: 10 }],
    edges: [{ id: 'e', sources: ['a'], targets: ['b'] }],
  });
  const Dispatcher = elk.worker.worker.dispatcher.constructor;
  let reply = null;
  const d = new Dispatcher({ postMessage: (m) => { reply = m; } });
  const layoutOne = (graph) => {
    reply = null;
    d.saveDispatch({ data: { id: 0, cmd: 'layout', graph, layoutOptions: {}, options: { logging: false, measureExecutionTime: false } } });
    if (!reply) throw new Error('ELK gave no reply');
    if (reply.error) throw reply.error;
    return reply.data;
  };
  const elkLayoutSync = (json) => {
    const graphs = JSON.parse(json);
    const res = {};
    for (const [name, g] of Object.entries(graphs)) {
      try {
        const t0 = performance.now();
        const out = layoutOne(g);
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
