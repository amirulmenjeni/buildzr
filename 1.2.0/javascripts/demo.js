// The browser demo (docs/demo.md): an editor for a buildzr model beside the buildzr viewer, all in this page. The code
// runs in the Run Code engine (runcode-client.js: Pyodide in a Web Worker) and the diagram is drawn by the viewer that
// the Run Code buttons embed (docs/runcode/viewer/, embed mode, messages buildzr:*; see docs/ui-settings.md).
//
// Nothing is downloaded before the first press of Run. Code is run only when the reader presses Run: never from a link
// and never from the draft kept in local storage. The page has the markup, this file the behaviour.
(function () {
  'use strict';

  const script = document.currentScript;
  const SAMPLES = new URL('../demo/samples.json', script ? script.src : location.href).href;
  const RUNCODE = RunCodeClient.RUNCODE;
  const MAX_CHARS = 50000; // buildzr.site.browser.MAX_CODE is twice this
  const TIMEOUT_MS = 30000;
  const READY_TIMEOUT_MS = 20000;
  const DRAFT_KEY = 'buildzr-demo:draft';
  const NARROW = '(max-width: 59.9375em)'; // the panes stack (demo.css)

  // Test hooks: timings, the thread, and a shorter time limit (set window.__demoTimeoutMs before the page's scripts run).
  const stats = (window.__demo = { thread: null, setupMs: null, runs: 0 });

  document.addEventListener('DOMContentLoaded', () => {
    const mount = document.getElementById('buildzr-demo');
    if (mount) start(mount);
  });

  function el(tag, cls, text) {
    const e = document.createElement(tag);
    if (cls) e.className = cls;
    if (text !== undefined) e.textContent = text;
    return e;
  }

  const isDark = () => document.body.getAttribute('data-md-color-scheme') === 'slate';
  const reducedMotion = () => matchMedia('(prefers-reduced-motion: reduce)').matches;

  function store(op, key, value) { // local storage can be blocked, full or absent: the demo works without it
    try {
      if (op === 'get') return localStorage.getItem(key);
      if (op === 'set') localStorage.setItem(key, value);
      else localStorage.removeItem(key);
    } catch (err) { /* private window, blocked site data */ }
    return null;
  }

  function start(mount) {
    let samples = [];
    let current = null; // the example last loaded: what Reset goes back to
    let client = null;
    let busy = false;
    let restarting = false; // the worker was stopped: the next run starts Python again
    let frame = null;
    let frameReady = false;
    let pending = null; // {result, resolve}: waiting for the viewer to load a model
    let readyTimer = 0;

    // --- the markup ---------------------------------------------------------------------------------------
    const bar = el('div', 'demo-toolbar');
    bar.setAttribute('role', 'group');
    bar.setAttribute('aria-label', 'Demo controls');
    const pick = el('select', 'demo-pick');
    pick.id = 'demo-pick';
    const pickLabel = el('label', 'demo-pick-label', 'Load an example');
    pickLabel.htmlFor = pick.id;
    const run = el('button', 'demo-run', '▶ Run');
    run.type = 'button';
    run.title = 'Build the model and draw it (Ctrl+Enter)';
    const stop = el('button', 'demo-stop', '■ Stop');
    stop.type = 'button';
    stop.disabled = true;
    stop.title = 'End the run that is going on (Esc)';
    const reset = el('button', 'demo-reset', '↺ Reset');
    reset.type = 'button';
    reset.title = 'Replace the code with the example you loaded last';
    bar.append(el('span', 'demo-pick-wrap'), run, stop, reset);
    bar.firstChild.append(pickLabel, pick);

    const status = el('p', 'demo-status');
    status.setAttribute('role', 'status');
    const offline = el('p', 'demo-offline');
    offline.hidden = true;

    const editor = el('section', 'demo-editor');
    const taLabel = el('label', 'demo-label', 'Model (Python)');
    const ta = el('textarea', 'demo-code');
    ta.id = 'demo-code';
    taLabel.htmlFor = ta.id;
    ta.spellcheck = false;
    ta.autocomplete = 'off';
    ta.setAttribute('autocapitalize', 'off');
    ta.setAttribute('autocorrect', 'off');
    ta.setAttribute('wrap', 'off');
    ta.setAttribute('aria-describedby', 'demo-hint');
    const hint = el('p', 'demo-hint', 'Press Ctrl+Enter (Cmd+Enter on a Mac) to run. Tab moves focus on; type spaces to indent.');
    hint.id = 'demo-hint';
    const problem = el('div', 'demo-problem');
    problem.setAttribute('role', 'alert');
    editor.append(taLabel, ta, hint, problem);

    const viewer = el('section', 'demo-viewer');
    viewer.tabIndex = -1;
    viewer.setAttribute('aria-label', 'Diagram');
    const head = el('div', 'demo-viewer-head');
    const back = el('button', 'demo-back', '↑ Edit the code');
    back.type = 'button';
    head.append(el('span', 'demo-label', 'Diagram'), back);
    const view = el('div', 'demo-view');
    view.append(el('p', 'demo-empty', 'Press Run to draw your model here.'));
    const extras = el('div', 'demo-extras');
    viewer.append(head, view, extras);

    const panes = el('div', 'demo-panes');
    panes.append(editor, viewer);
    mount.replaceChildren(bar, status, offline, panes);

    const say = (text) => { status.textContent = text; };
    const state = (value) => { mount.dataset.state = value; };
    state('idle');

    // --- the code -----------------------------------------------------------------------------------------
    // Replacing the text through the editing commands keeps the browser's undo; the fallback does not.
    function setCode(text) {
      ta.focus();
      ta.select();
      let done = false;
      try { done = document.execCommand('insertText', false, text); } catch (err) { done = false; }
      if (!done || ta.value !== text) ta.value = text;
      ta.setSelectionRange(0, 0);
      ta.scrollTop = 0;
      saveDraft();
    }

    let draftTimer = 0;
    function saveDraft() {
      clearTimeout(draftTimer);
      store('set', DRAFT_KEY, ta.value);
    }
    ta.addEventListener('input', () => {
      clearTimeout(draftTimer);
      draftTimer = setTimeout(saveDraft, 300);
    });

    function loadSample(sample) {
      current = sample;
      setCode(sample.code);
      clearProblem();
      say(`Loaded the example “${sample.title}”. Press Run to draw it.`);
    }

    pick.addEventListener('change', () => {
      const sample = samples.find((s) => s.id === pick.value);
      pick.value = '';
      if (sample) loadSample(sample);
    });
    reset.addEventListener('click', () => {
      const sample = current || samples[0];
      if (!sample) return;
      loadSample(sample);
    });
    back.addEventListener('click', () => ta.focus());

    // --- problems -----------------------------------------------------------------------------------------
    function clearProblem() {
      problem.replaceChildren();
      delete mount.dataset.errorLine;
    }

    function showProblem(lead, message, line, source) {
      const box = el('div', 'demo-error');
      box.append(el('p', 'demo-error-lead', lead));
      if (message) box.append(el('p', 'demo-error-message', message));
      if (source) {
        const pre = el('pre');
        pre.append(el('code', '', source));
        box.append(pre);
      }
      if (line) {
        const go = el('button', 'demo-goto', `Select line ${line}`);
        go.type = 'button';
        go.addEventListener('click', () => selectLine(line));
        box.append(go);
        mount.dataset.errorLine = String(line);
      }
      problem.replaceChildren(box);
      say(lead);
    }

    function selectLine(n) {
      const lines = ta.value.split('\n');
      if (n < 1 || n > lines.length) return;
      const start = lines.slice(0, n - 1).reduce((sum, l) => sum + l.length + 1, 0);
      ta.focus();
      ta.setSelectionRange(start, start + lines[n - 1].length);
      const lineHeight = parseFloat(getComputedStyle(ta).lineHeight) || 20;
      ta.scrollTop = Math.max(0, (n - 3) * lineHeight);
    }

    // --- running ------------------------------------------------------------------------------------------
    function setBusy(on) {
      busy = on;
      run.setAttribute('aria-disabled', String(on)); // stays focusable: the reader's place does not move
      run.textContent = on ? '⏳ Running…' : '▶ Run';
      stop.disabled = !on;
      if (on) viewer.setAttribute('aria-busy', 'true');
      else viewer.removeAttribute('aria-busy');
    }

    async function runCode() {
      if (busy) return;
      const code = ta.value;
      clearProblem();
      if (!code.trim()) { showProblem('There is no code to run.', 'Write a model, or load an example.'); return; }
      if (code.length > MAX_CHARS) {
        showProblem(`The code is ${code.length.toLocaleString('en')} characters long.`, `The demo runs at most ${MAX_CHARS.toLocaleString('en')}.`);
        return;
      }
      setBusy(true);
      state('running');
      const first = !client || restarting;
      restarting = false;
      say(first ? 'Loading Python and the viewer. The first run downloads about 6 MB and takes a few seconds…'
        : 'Running the code…');
      if (!client) {
        const ms = Number(window.__demoTimeoutMs);
        client = RunCodeClient.create({ stats, allowMainThread: false, timeoutMs: ms > 0 ? ms : TIMEOUT_MS });
      }
      try {
        const result = await client.run(code);
        stats.runs++;
        updateOffline();
        if (result.ok) {
          if (!result.drawn) showNothing(result);
          else await showDiagram(result);
        } else if (result.error.stopped) {
          restarting = true;
          state('stopped');
          say('Stopped.');
        } else if (result.error.timedOut) {
          restarting = true;
          state('error');
          showProblem('The run took too long.', result.error.message);
        } else {
          state('error');
          const e = result.error;
          showProblem(e.line ? `Error on line ${e.line}.` : 'The code failed.', e.message, e.line, e.source);
        }
      } catch (err) {
        client = null; // the next press tries again
        state('error');
        const needsWorker = err && err.needsWorker;
        showProblem(needsWorker ? 'The demo cannot run in this browser.' : 'The demo could not start.',
          String((err && err.message) || err),
          null,
          '');
        if (!needsWorker) problem.firstChild.append(el('p', '', 'Check your connection (Python is loaded from cdn.jsdelivr.net) and press Run again. You can keep editing meanwhile.'));
      } finally {
        setBusy(false);
      }
    }

    run.addEventListener('click', runCode);
    stop.addEventListener('click', () => { if (client) client.stop(); });
    ta.addEventListener('keydown', (e) => {
      if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); runCode(); }
    });
    mount.addEventListener('keydown', (e) => {
      if (e.key === 'Escape' && busy && client && client.stop()) e.preventDefault();
    });

    // --- showing the result -------------------------------------------------------------------------------
    function post(message) {
      frame.contentWindow.postMessage(message, location.origin);
    }

    function showDiagram(result) {
      return new Promise((resolve) => {
        if (pending) pending.resolve();
        pending = { result, resolve };
        if (!frame) {
          frame = el('iframe', 'demo-frame');
          frame.title = 'Diagram of your model (interactive viewer)';
          frameReady = false;
          frame.src = RUNCODE + 'viewer/index.html?embed=1&theme=' + (isDark() ? 'dark' : 'light') + result.focus.route;
          readyTimer = setTimeout(() => viewerFailed('The viewer did not start.'), READY_TIMEOUT_MS);
          view.replaceChildren(frame);
        } else if (frameReady) {
          sendModel();
        }
        showExtras(result);
      });
    }

    // The first model opens where the code's `# focus:` line (or buildzr) says; later ones keep the reader's place.
    let firstModel = true;
    function sendModel() {
      const { result } = pending;
      post({ type: 'buildzr:load', files: result.files, route: firstModel ? result.focus.route : null, title: 'Your model' });
      firstModel = false;
    }

    addEventListener('message', (e) => {
      if (e.origin !== location.origin || !frame || e.source !== frame.contentWindow || !e.data || typeof e.data.type !== 'string') return;
      if (e.data.type === 'buildzr:ready') {
        frameReady = true;
        clearTimeout(readyTimer);
        if (pending) sendModel();
      } else if (e.data.type === 'buildzr:loaded' && pending) {
        const { resolve } = pending;
        pending = null;
        if (e.data.status === 'error') {
          viewerFailed('The viewer could not show this model: ' + (e.data.error || 'unknown error'));
        } else {
          say('Diagram ready.');
          state('drawn');
          if (matchMedia(NARROW).matches) viewer.scrollIntoView({ block: 'start', behavior: reducedMotion() ? 'auto' : 'smooth' });
        }
        resolve();
      }
    });

    function viewerFailed(message) {
      if (frame) frame.remove();
      frame = null;
      frameReady = false;
      firstModel = true;
      clearTimeout(readyTimer);
      view.replaceChildren(el('p', 'demo-empty', message));
      state('error');
      showProblem(message);
      if (pending) { pending.resolve(); pending = null; }
    }

    function showNothing(result) {
      state('nothing');
      say('The code ran; there is nothing to draw.');
      showProblem('The code ran, but its model has nothing to draw.', 'Add a Person, a SoftwareSystem, a Container or a Component.');
      showExtras(result);
    }

    // The docs' light/dark toggle: the viewer follows.
    new MutationObserver(() => {
      if (frame && frameReady) post({ type: 'buildzr:theme', theme: isDark() ? 'dark' : 'light' });
    }).observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });

    function showExtras(result) {
      const json = el('details', 'demo-json');
      json.append(el('summary', '', 'Show model JSON'));
      const pre = el('pre');
      pre.append(el('code', '', result.workspaceJson));
      json.append(pre);
      const copy = el('button', 'demo-copy-json', 'Copy model JSON');
      copy.type = 'button';
      copy.title = 'Copy the Structurizr JSON of this model to the clipboard';
      copy.addEventListener('click', async () => {
        try {
          await navigator.clipboard.writeText(result.workspaceJson);
          copy.textContent = 'Copied!';
          say('Model JSON copied to the clipboard.');
        } catch (err) {
          copy.textContent = 'Copy failed';
          say('Could not copy. Open "Show model JSON" and select the text instead.');
        }
        setTimeout(() => { copy.textContent = 'Copy model JSON'; }, 2000);
      });
      const row = el('div', 'demo-extras-row');
      row.append(json, copy);
      extras.replaceChildren(row);
      if (result.stdout) {
        const printed = el('details', 'demo-printed');
        printed.append(el('summary', '', 'Show printed output'));
        const out = el('pre');
        out.append(el('code', '', result.stdout));
        printed.append(out);
        extras.append(printed);
      }
    }

    // --- offline ------------------------------------------------------------------------------------------
    function updateOffline() {
      const needsDownload = !stats.thread;
      offline.hidden = navigator.onLine !== false || !needsDownload;
      if (!offline.hidden) {
        offline.textContent = 'You are offline. You can keep editing. Run needs a connection the first time, to download Python; your browser keeps it afterwards.';
      }
    }
    addEventListener('online', updateOffline);
    addEventListener('offline', updateOffline);
    updateOffline();

    // --- start --------------------------------------------------------------------------------------------
    const draft = store('get', DRAFT_KEY);
    ta.value = draft && draft.trim() ? draft : '';
    fetch(SAMPLES).then((r) => (r.ok ? r.json() : Promise.reject(new Error('HTTP ' + r.status)))).then((list) => {
      samples = Array.isArray(list) ? list.filter((s) => s && typeof s.id === 'string' && typeof s.title === 'string' && typeof s.code === 'string') : [];
    }).catch(() => {
      samples = [];
    }).then(() => {
      pick.append(Object.assign(el('option', '', 'Choose…'), { value: '' }));
      for (const s of samples) pick.append(Object.assign(el('option', '', s.title), { value: s.id }));
      pick.value = '';
      pickLabel.parentNode.hidden = samples.length === 0;
      reset.disabled = samples.length === 0;
      if (!ta.value && samples.length) {
        current = samples[0];
        ta.value = current.code;
      } else if (!ta.value) {
        ta.placeholder = 'Write a buildzr model here, for example:\nperson = Person("User")\nsystem = SoftwareSystem("System")\nperson >> "Uses" >> system';
      }
      mount.dataset.ready = 'true';
    });
  }
})();
