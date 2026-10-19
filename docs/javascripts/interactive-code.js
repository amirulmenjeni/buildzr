// Run Code: a button on every Python code block of the docs. Pressing it runs the code in the reader's browser
// (Pyodide, see runcode-engine.js) and draws its workspace in the buildzr viewer, embedded in an iframe under the
// code. Nothing is downloaded before the first press.
//
// For authors:
//   - `# no-run` (or `# norun`) as the first line: no button; the line is hidden.
//   - `# focus: <element id>` or `# focus: view:<key>` anywhere: where the viewer opens; the line is hidden (it is
//     neither shown nor copied). Without it: a deployment or dynamic view the code defines, else the landscape with
//     the last-created element that has children expanded, else the whole landscape (buildzr/site/browser.py).
// The viewer's embed mode (?embed=1, messages buildzr:*) is described in the viewer docs.
(function () {
  'use strict';

  const script = document.currentScript;
  // docs/runcode/ (scripts/build_docs_assets.py) and this folder, found from this script's URL: works at any depth.
  const RUNCODE = new URL('../runcode/', script ? script.src : location.href).href;
  const ENGINE = new URL('runcode-engine.js', script ? script.src : location.href).href;
  const NO_RUN = /^\s*#\s*no-?run\b/;
  const FOCUS = /^[ \t]*#[ \t]*focus:/;
  const READY_TIMEOUT_MS = 20000;

  // Test hook: timings and the thread the engine runs on. Set window.__runcodeForceMainThread before the first press
  // to measure the main-thread path.
  const stats = (window.__runcode = { thread: null, setupMs: null, runs: [] });
  const blocks = [];
  let engine = null; // Promise<{run(code) -> Promise<result>}>

  document.addEventListener('DOMContentLoaded', () => {
    document.querySelectorAll('.language-python.highlight > pre > code, div.highlight > pre > code.language-python')
      .forEach((code) => setUp(code));
  });

  // --- the code block -------------------------------------------------------------------------------------

  function lineSpans(code) {
    const spans = code.querySelectorAll(':scope > span[id^="__span"]');
    return spans.length ? Array.from(spans) : null;
  }

  function setUp(code) {
    const source = code.textContent;
    const spans = lineSpans(code);
    const lines = source.split('\n');
    if (NO_RUN.test(lines.find((l) => l.trim()) || '')) {
      if (spans) spans.find((s) => s.textContent.trim()).classList.add('runcode-hidden-line');
      return;
    }
    // Hidden lines (1-based): not displayed, and not copied (the copy button copies what is displayed).
    const hidden = [];
    lines.forEach((l, i) => { if (FOCUS.test(l)) hidden.push(i + 1); });
    if (hidden.length && !spans) return; // cannot hide the line without line spans: no button rather than a wrong page
    for (const n of hidden) spans[n - 1].classList.add('runcode-hidden-line');

    const highlight = code.closest('.highlight');
    const n = blocks.length;
    const b = { n, source, hidden, spans, highlight, frame: null, frameReady: false, pending: null, busy: false };
    blocks.push(b);
    b.title = 'Diagram of the example' + (nearestHeading(highlight) ? ': ' + nearestHeading(highlight) : '');

    const wrapper = (b.wrapper = el('div', 'runcode'));
    const bar = el('div', 'runcode-bar');
    b.run = el('button', 'runcode-run', '▶ Run Code');
    b.run.type = 'button';
    b.run.title = 'Run this code in your browser and draw its diagram below';
    b.run.addEventListener('click', () => runBlock(b));
    bar.append(b.run);

    b.output = el('section', 'runcode-output');
    b.output.hidden = true;
    b.output.tabIndex = -1;
    b.output.setAttribute('aria-label', b.title);
    const head = el('div', 'runcode-head');
    b.status = el('p', 'runcode-status');
    b.status.setAttribute('role', 'status');
    b.toggle = el('button', 'runcode-toggle', 'Hide diagram');
    b.toggle.type = 'button';
    b.toggle.setAttribute('aria-expanded', 'true');
    b.toggle.setAttribute('aria-controls', `runcode-body-${n}`);
    b.toggle.addEventListener('click', () => expand(b, b.body.hidden));
    head.append(el('span', 'runcode-label', 'Diagram'), b.status, b.toggle);
    b.body = el('div', 'runcode-body');
    b.body.id = `runcode-body-${n}`;
    b.view = el('div', 'runcode-view');
    b.extras = el('div', 'runcode-extras');
    b.body.append(b.view, b.extras);
    b.output.append(head, b.body);

    highlight.parentNode.insertBefore(wrapper, highlight);
    wrapper.append(bar, highlight, b.output);
  }

  function nearestHeading(node) {
    for (let n = node; n && n !== document.body; n = n.parentElement) {
      for (let p = n.previousElementSibling; p; p = p.previousElementSibling) {
        if (/^H[1-6]$/.test(p.tagName)) return p.textContent.replace(/¶$/, '').trim();
      }
    }
    return '';
  }

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  function expand(b, open) {
    b.body.hidden = !open;
    b.toggle.textContent = open ? 'Hide diagram' : 'Show diagram';
    b.toggle.setAttribute('aria-expanded', String(open));
  }

  function say(b, text) {
    b.status.textContent = text;
  }

  // data-state of the wrapper: running, drawn, nothing (ran, nothing to draw) or error; data-error-line: the line.
  function state(b, value, line) {
    b.wrapper.dataset.state = value;
    if (line) b.wrapper.dataset.errorLine = String(line);
    else delete b.wrapper.dataset.errorLine;
  }

  // --- running ------------------------------------------------------------------------------------------

  async function runBlock(b) {
    if (b.busy) return;
    b.busy = true;
    const first = !engine;
    b.run.disabled = true;
    b.run.textContent = '⏳ Running…';
    b.output.hidden = false;
    b.output.setAttribute('aria-busy', 'true');
    expand(b, true);
    clearErrorLine(b);
    state(b, 'running');
    if (!b.frame) {
      // As tall as the diagram will be: the page does not grow under the reader when the diagram arrives.
      b.view.replaceChildren(el('div', 'runcode-placeholder', ''));
    }
    say(b, first ? 'Loading Python and the viewer. The first run downloads about 6 MB and takes a few seconds…'
      : 'Running the code…');
    scrollToDiagram(b.output, false);
    const t0 = performance.now();
    try {
      const result = await (await getEngine()).run(b.source);
      stats.runs.push({ block: b.n, ms: Math.round(performance.now() - t0), first });
      if (!result.ok) showError(b, result.error);
      else if (!result.drawn) showNothing(b, result);
      else await showDiagram(b, result);
    } catch (err) {
      engine = null; // the next press tries again
      showError(b, { message: String((err && err.message) || err), line: null, source: '', setup: true });
    } finally {
      b.busy = false;
      b.run.disabled = false;
      b.run.textContent = '▶ Run Code';
      b.output.removeAttribute('aria-busy');
    }
  }

  function getEngine() {
    if (!engine) {
      engine = (window.__runcodeForceMainThread || typeof Worker === 'undefined') ? mainThreadEngine() : workerEngine()
        .catch((err) => (err && err.workerBroken ? mainThreadEngine() : Promise.reject(err)));
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
        reject(Object.assign(new Error(String(err)), { workerBroken: true }));
        return;
      }
      const waiting = new Map();
      let id = 0;
      worker.onerror = (e) => { // the script did not even start (blocked by a policy, a syntax the browser lacks)
        e.preventDefault();
        reject(Object.assign(new Error(e.message || 'the worker failed'), { workerBroken: true }));
      };
      worker.onmessage = (e) => {
        const m = e.data || {};
        if (m.type === 'started') {
          stats.thread = 'worker';
          stats.setupMs = m.ms;
          resolve({ run: (code) => new Promise((done) => { waiting.set(++id, done); worker.postMessage({ type: 'run', id, code }); }) });
        } else if (m.type === 'start-failed') {
          worker.terminate();
          reject(new Error(m.message));
        } else if (m.type === 'result' && waiting.has(m.id)) {
          waiting.get(m.id)(m.result);
          waiting.delete(m.id);
        }
      };
      worker.postMessage({ type: 'start', base: RUNCODE });
    });
  }

  async function mainThreadEngine() {
    if (!window.RunCodeEngine) {
      await new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = ENGINE;
        s.onload = resolve;
        s.onerror = () => reject(new Error('could not load ' + ENGINE));
        document.head.appendChild(s);
      });
    }
    const eng = await window.RunCodeEngine.start(RUNCODE);
    stats.thread = 'main';
    stats.setupMs = eng.ms;
    return { run: async (code) => eng.run(code) };
  }

  // --- showing the result -------------------------------------------------------------------------------

  const isDark = () => document.body.getAttribute('data-md-color-scheme') === 'slate';

  function showDiagram(b, result) {
    return new Promise((resolve) => {
      b.pending = { result, resolve };
      if (!b.frame) {
        b.frame = el('iframe', 'runcode-frame');
        b.frame.title = b.title + ' (interactive viewer)';
        b.frame.src = RUNCODE + 'viewer/index.html?embed=1&theme=' + (isDark() ? 'dark' : 'light') + result.focus.route;
        b.frameReady = false;
        b.timer = setTimeout(() => viewerFailed(b, 'The viewer did not start.'), READY_TIMEOUT_MS);
        b.view.replaceChildren(b.frame);
      } else if (b.frameReady) {
        post(b, { type: 'buildzr:load', files: result.files, route: result.focus.route, title: b.title });
      }
      showExtras(b, result);
    });
  }

  function post(b, message) {
    b.frame.contentWindow.postMessage(message, location.origin);
  }

  addEventListener('message', (e) => {
    if (e.origin !== location.origin || !e.data || typeof e.data.type !== 'string') return;
    const b = blocks.find((x) => x.frame && x.frame.contentWindow === e.source);
    if (!b) return;
    if (e.data.type === 'buildzr:ready') {
      b.frameReady = true;
      clearTimeout(b.timer);
      if (b.pending) post(b, { type: 'buildzr:load', files: b.pending.result.files, route: b.pending.result.focus.route, title: b.title });
    } else if (e.data.type === 'buildzr:loaded' && b.pending) {
      const { resolve } = b.pending;
      b.pending = null;
      if (e.data.status === 'error') {
        viewerFailed(b, 'The viewer could not show this model: ' + (e.data.error || 'unknown error'));
      } else {
        say(b, 'Diagram ready.');
        state(b, 'drawn');
        scrollToDiagram(b.output, true);
        b.output.focus({ preventScroll: true });
      }
      resolve();
    }
  });

  function viewerFailed(b, message) {
    if (b.frame) b.frame.remove();
    b.frame = null;
    b.view.replaceChildren(errorBox(message));
    say(b, message);
    state(b, 'error');
    if (b.pending) { b.pending.resolve(); b.pending = null; }
  }

  // The docs' light/dark toggle: every diagram follows.
  new MutationObserver(() => {
    for (const b of blocks) if (b.frame && b.frameReady) post(b, { type: 'buildzr:theme', theme: isDark() ? 'dark' : 'light' });
  }).observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });

  function showExtras(b, result) {
    const json = el('details', 'runcode-json');
    json.append(el('summary', '', 'Show model JSON'));
    const pre = el('pre');
    pre.append(el('code', '', result.workspaceJson));
    json.append(pre);
    const copy = el('button', 'runcode-copy-json', 'Copy model JSON');
    copy.type = 'button';
    copy.title = 'Copy the Structurizr JSON of this model to the clipboard';
    copy.addEventListener('click', () => copyJson(b, copy, result.workspaceJson));
    const row = el('div', 'runcode-extras-row');
    row.append(json, copy);
    b.extras.replaceChildren(row);
    if (result.stdout) {
      const printed = el('details', 'runcode-printed');
      printed.append(el('summary', '', 'Show printed output'));
      const out = el('pre');
      out.append(el('code', '', result.stdout));
      printed.append(out);
      b.extras.append(printed);
    }
  }

  async function copyJson(b, button, text) {
    try {
      await navigator.clipboard.writeText(text);
      button.textContent = 'Copied!';
      say(b, 'Model JSON copied to the clipboard.');
    } catch (err) {
      button.textContent = 'Copy failed';
      say(b, 'Could not copy. Open "Show model JSON" and select the text instead.');
    }
    setTimeout(() => { button.textContent = 'Copy model JSON'; }, 2000);
  }

  function showNothing(b, result) {
    if (b.frame) b.frame.remove();
    b.frame = null;
    b.view.replaceChildren(el('p', 'runcode-note', 'The code ran, but its model has nothing to draw (no people, software systems, containers or components).'));
    say(b, 'The code ran; nothing to draw.');
    state(b, 'nothing');
    showExtras(b, result);
  }

  // --- errors -------------------------------------------------------------------------------------------

  // The line the reader sees: the hidden lines above it are not counted.
  function shownLine(b, line) {
    if (!line) return null;
    if (b.hidden.includes(line)) return { hiddenMarker: true };
    return { n: line - b.hidden.filter((h) => h < line).length, span: b.spans ? b.spans[line - 1] : null };
  }

  function showError(b, error) {
    if (b.frame) b.frame.remove();
    b.frame = null;
    b.extras.replaceChildren();
    const where = shownLine(b, error.line);
    let lead;
    if (error.setup) lead = 'Run Code could not start.';
    else if (!where) lead = 'The code failed.';
    else if (where.hiddenMarker) lead = 'The hidden "# focus:" line of this example is wrong.';
    else lead = `Error on line ${where.n} of the code above.`;
    const box = errorBox(lead, error.message, where && where.n && error.source ? error.source : '');
    if (error.setup) box.append(el('p', '', 'Check your connection (Python is loaded from cdn.jsdelivr.net) and press Run Code again.'));
    b.view.replaceChildren(box);
    if (where && where.span) where.span.classList.add('runcode-error-line');
    say(b, lead);
    state(b, 'error', where && where.n);
  }

  function errorBox(lead, message, source) {
    const box = el('div', 'runcode-error');
    box.setAttribute('role', 'alert');
    box.append(el('p', 'runcode-error-lead', lead));
    if (message) box.append(el('p', 'runcode-error-message', message));
    if (source) {
      const pre = el('pre');
      pre.append(el('code', '', source));
      box.append(pre);
    }
    return box;
  }

  function clearErrorLine(b) {
    if (b.spans) for (const s of b.spans) s.classList.remove('runcode-error-line');
  }

  // --- scrolling ----------------------------------------------------------------------------------------

  // Bring the diagram area into view, its top just below the sticky header. Nothing happens when it is already
  // fully visible; with `onlyIfMoved`, only when its top has left the view.
  function scrollToDiagram(target, onlyIfMoved) {
    const header = document.querySelector('.md-header');
    const headerBottom = header ? Math.max(0, header.getBoundingClientRect().bottom) : 0;
    const r = target.getBoundingClientRect();
    const fullyVisible = r.top >= headerBottom && r.bottom <= window.innerHeight;
    const topVisible = r.top >= headerBottom && r.top < window.innerHeight;
    if (fullyVisible || (onlyIfMoved && topVisible)) return;
    const reduce = matchMedia('(prefers-reduced-motion: reduce)').matches;
    window.scrollTo({ top: window.scrollY + r.top - headerBottom - 8, behavior: reduce ? 'auto' : 'smooth' });
  }
})();
