// The page side of the Run Code engine (runcode-engine.js): starts it as a Web Worker (the page stays responsive while
// Python starts and runs) or, where a worker cannot start and the caller allows it, on the page itself. Shared by the
// Run Code buttons (interactive-code.js) and the browser demo (demo.js). Nothing is downloaded until the first run.
//
//   const client = RunCodeClient.create({ stats, allowMainThread, timeoutMs, forceMainThread });
//   client.run(code) -> Promise<result>    run_snippet's parsed JSON; rejects when the engine cannot start
//   client.stop()                          ends a run that is going on (a worker only): it resolves as
//                                          {ok: false, error: {stopped: true, ...}}; the next run starts a new worker
//   client.thread()                        'worker', 'main' or null (not started)
//
// `timeoutMs` (worker only): a run that lasts longer is ended like stop() and resolves with error.timedOut. A page
// that only reads (the buttons of the docs) leaves it off. `allowMainThread: false` refuses the fallback, because
// Python on the page cannot be interrupted: `run` then rejects with error.needsWorker.
(function (scope) {
  'use strict';

  const script = document.currentScript;
  // docs/runcode/ (scripts/build_docs_assets.py) and the engine, found from this script's URL: works at any depth.
  const RUNCODE = new URL('../runcode/', script ? script.src : location.href).href;
  const ENGINE = new URL('runcode-engine.js', script ? script.src : location.href).href;

  const failure = (message, extra) => ({ ok: false, error: { message, line: null, source: '', ...extra } });

  function create(options) {
    const opts = options || {};
    const stats = opts.stats || {};
    let engine = null; // Promise<{run(code) -> Promise<result>, canStop}>
    let running = null; // {abort(result)} of the run in flight
    let kill = null; // ends the worker, whether it is still starting or running

    function getEngine() {
      if (!engine) {
        const force = opts.forceMainThread && opts.forceMainThread();
        if (force || typeof Worker === 'undefined') engine = mainThreadEngine();
        else {
          // A worker that could not even load its script (a lost connection, a policy) is run on the page, where the
          // caller allows it; otherwise the reader hears why.
          engine = workerEngine().catch((err) => (err && err.workerBroken && opts.allowMainThread !== false
            ? mainThreadEngine() : Promise.reject(err)));
        }
        engine.catch(() => {});
      }
      return engine;
    }

    function workerEngine() {
      return new Promise((resolve, reject) => {
        let worker;
        try {
          worker = new Worker(ENGINE);
        } catch (err) {
          reject(Object.assign(new Error('This browser cannot start the Web Worker that runs your code (' + String(err) + ').'), { workerBroken: true, needsWorker: true }));
          return;
        }
        const waiting = new Map();
        let id = 0;
        let ended = false;
        const end = (reason) => { // the worker is gone: whoever waits for it hears so
          if (ended) return;
          ended = true;
          worker.terminate();
          engine = null;
          reject(Object.assign(new Error(reason), { stopped: true })); // no effect once started
          for (const done of waiting.values()) done(null);
          waiting.clear();
        };
        worker.onerror = (e) => { // the script did not even start (blocked by a policy, a syntax the browser lacks)
          e.preventDefault();
          reject(Object.assign(new Error(e.message || 'the worker script could not be loaded'), { workerBroken: true }));
        };
        worker.onmessage = (e) => {
          const m = e.data || {};
          if (m.type === 'started') {
            stats.thread = 'worker';
            stats.setupMs = m.ms;
            resolve({
              run: (code) => new Promise((done) => { waiting.set(++id, done); worker.postMessage({ type: 'run', id, code }); }),
              canStop: true,
            });
          } else if (m.type === 'start-failed') {
            worker.terminate();
            reject(new Error(m.message));
          } else if (m.type === 'result' && waiting.has(m.id)) {
            waiting.get(m.id)(m.result);
            waiting.delete(m.id);
          }
        };
        kill = () => end('stopped');
        worker.postMessage({ type: 'start', base: RUNCODE });
      });
    }
    async function mainThreadEngine() {
      if (opts.allowMainThread === false) {
        throw Object.assign(new Error('This browser cannot start the Web Worker that runs your code.'), { needsWorker: true });
      }
      if (!scope.RunCodeEngine) {
        await new Promise((resolve, reject) => {
          const s = document.createElement('script');
          s.src = ENGINE;
          s.onload = resolve;
          s.onerror = () => reject(new Error('could not load ' + ENGINE));
          document.head.appendChild(s);
        });
      }
      const eng = await scope.RunCodeEngine.start(RUNCODE);
      stats.thread = 'main';
      stats.setupMs = eng.ms;
      return { run: async (code) => eng.run(code), canStop: false };
    }

    async function run(code) {
      let timer = 0;
      let stopped = null;
      const aborted = new Promise((resolve) => {
        running = { abort: (result) => { stopped = result; resolve(result); } };
      });
      try {
        const eng = await Promise.race([getEngine(), aborted.then(() => null)]);
        if (!eng) return stopped;
        if (opts.timeoutMs && eng.canStop) {
          timer = setTimeout(() => {
            const s = Math.round(opts.timeoutMs / 1000);
            running.abort(failure(`The code ran for more than ${s} seconds and was stopped. Look for a loop that never ends.`, { timedOut: true }));
            if (kill) kill();
          }, opts.timeoutMs);
        }
        const result = await Promise.race([eng.run(code), aborted]);
        return result === null ? stopped : result;
      } catch (err) {
        if (err && err.stopped) return stopped || failure('Stopped.', { stopped: true });
        throw err;
      } finally {
        clearTimeout(timer);
        running = null;
      }
    }

    function stop() {
      if (!running) return false;
      running.abort(failure('Stopped.', { stopped: true }));
      if (kill) kill();
      return true;
    }

    return { run, stop, thread: () => stats.thread || null };
  }

  scope.RunCodeClient = { create, RUNCODE };
})(window);
