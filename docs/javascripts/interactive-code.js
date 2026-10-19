// Global Pyodide instance
let pyodideInstance = null;
let pyodideLoading = false;

document.addEventListener('DOMContentLoaded', function() {
    console.log('[Interactive Code] Script loaded');

    // Add interactive buttons to Python code blocks
    // MkDocs Material uses: <div class="language-python highlight"><pre><code>...
    const codeBlocks = document.querySelectorAll('.language-python.highlight pre code, pre code.language-python');

    console.log('[Interactive Code] Found', codeBlocks.length, 'Python code blocks');

    codeBlocks.forEach((codeBlock, index) => {
        const pre = codeBlock.parentElement;
        const container = pre.parentElement;

        // Check if this code block should be interactive
        const shouldBeInteractive = checkIfInteractive(pre, container);

        console.log('[Interactive Code] Block', index, 'interactive?', shouldBeInteractive);

        if (shouldBeInteractive) {
            makeInteractive(pre, codeBlock, index);
            console.log('[Interactive Code] Made block', index, 'interactive');
        }
    });

    console.log('[Interactive Code] Initialization complete');
});

function checkIfInteractive(pre, container) {
    // Get the code content
    const codeBlock = pre.querySelector('code');
    if (!codeBlock) return false;

    const code = codeBlock.textContent.trim();

    // Check if code starts with # no-run or # norun comment
    if (code.startsWith('# no-run') || code.startsWith('# norun')) {
        // Hide the first line with CSS instead of removing it
        // This preserves syntax highlighting
        const firstLine = codeBlock.querySelector('.linenumber:first-child')?.parentElement ||
                         codeBlock.firstChild;

        if (firstLine && firstLine.nodeType === Node.ELEMENT_NODE) {
            firstLine.style.display = 'none';
        } else {
            // Fallback: wrap first line in a hidden span
            const lines = codeBlock.innerHTML.split('\n');
            if (lines.length > 0) {
                lines[0] = '<span style="display: none;">' + lines[0] + '</span>';
                codeBlock.innerHTML = lines.join('\n');
            }
        }

        return false;
    }

    // SPIKE: a '# focus: ...' line says where the viewer opens; readers do not need it.
    for (const span of codeBlock.querySelectorAll('span[id^="__span"]')) {
        if (/^\s*#\s*focus:/.test(span.textContent)) span.style.display = 'none';
    }
    // Make all other Python code blocks interactive
    return true;
}

function makeInteractive(pre, codeBlock, index) {
    const code = codeBlock.textContent;

    // Create wrapper div
    const wrapper = document.createElement('div');
    wrapper.className = 'interactive-code-wrapper';

    // Create button container
    const buttonContainer = document.createElement('div');
    buttonContainer.className = 'interactive-code-buttons';

    // Create RUN button (in-browser execution)
    const runButton = document.createElement('button');
    runButton.className = 'interactive-run-button';
    runButton.innerHTML = '▶ Run Code';
    runButton.onclick = () => runCodeInBrowser(code, index, runButton);

    buttonContainer.appendChild(runButton);

    // Create output area container
    const outputContainer = document.createElement('div');
    outputContainer.className = 'interactive-output-container';
    outputContainer.id = `output-container-${index}`;
    outputContainer.style.display = 'none';

    // Create output header with toggle button and copy button
    const outputHeader = document.createElement('div');
    outputHeader.className = 'interactive-output-header';

    const headerTitle = document.createElement('span');
    headerTitle.innerHTML = '📊 Diagram';
    headerTitle.style.fontWeight = '600';

    const buttonGroup = document.createElement('div');
    buttonGroup.style.display = 'flex';
    buttonGroup.style.gap = '0.5em';

    const copyButton = document.createElement('button');
    copyButton.className = 'interactive-copy-output-button';
    copyButton.innerHTML = '📋 Copy';
    copyButton.onclick = () => copyOutput(index, copyButton);

    const toggleButton = document.createElement('button');
    toggleButton.className = 'interactive-toggle-button';
    toggleButton.innerHTML = '▼ Hide';
    toggleButton.onclick = () => toggleOutput(index, toggleButton);

    buttonGroup.appendChild(copyButton);
    buttonGroup.appendChild(toggleButton);

    outputHeader.appendChild(headerTitle);
    outputHeader.appendChild(buttonGroup);

    // Create output area (JSON)
    const outputArea = document.createElement('div');
    outputArea.className = 'interactive-output';
    outputArea.id = `output-${index}`;

    outputContainer.appendChild(outputHeader);
    outputContainer.appendChild(outputArea);

    // Insert before the pre element
    pre.parentNode.insertBefore(wrapper, pre);
    wrapper.appendChild(buttonContainer);
    wrapper.appendChild(pre);
    wrapper.appendChild(outputContainer);
}

// SPIKE: everything Run Code needs is loaded on the first click, never with the page.
const PYODIDE_URL = 'https://cdn.jsdelivr.net/pyodide/v0.28.3/full/';
// docs/runcode/ (staged by spike/runcode/stage_docs.sh), found from this script's own URL so it works at any depth.
const RUNCODE_BASE = new URL('../runcode/', document.currentScript ? document.currentScript.src : location.href).href;

function loadScript(src) {
    return new Promise((resolve, reject) => {
        const s = document.createElement('script');
        s.src = src;
        s.onload = resolve;
        s.onerror = () => reject(new Error('could not load ' + src));
        document.head.appendChild(s);
    });
}

async function initPyodide() {
    if (!pyodideLoading) {
        pyodideLoading = (async () => {
            const t0 = performance.now();
            await loadScript(PYODIDE_URL + 'pyodide.js');
            const [pyodide, manifest] = await Promise.all([
                loadPyodide({ indexURL: PYODIDE_URL }),
                fetch(RUNCODE_BASE + 'manifest.json').then((r) => r.json()),
                loadScript(RUNCODE_BASE + 'elk.bundled.js').then(() => loadScript(RUNCODE_BASE + 'elk_sync.js')),
                loadScript(RUNCODE_BASE + 'wrap.js'),
            ]);
            const [wheels, buildPy, elkSync] = await Promise.all([
                Promise.all(manifest.wheels.map((w) => fetch(RUNCODE_BASE + 'wheels/' + w).then((r) => r.arrayBuffer()))),
                fetch(RUNCODE_BASE + 'browser_build.py').then((r) => r.text()),
                makeElkSync(window.ELK),
                pyodide.loadPackage(['typing-extensions'], { messageCallback: () => {} }),
            ]);
            for (const w of wheels) pyodide.unpackArchive(new Uint8Array(w), 'wheel');
            window.elkLayoutSync = elkSync;
            pyodide.FS.mkdirTree('/rc');
            pyodide.FS.writeFile('/rc/browser_build.py', buildPy);
            pyodide.runPython("import sys; sys.path.insert(0, '/rc'); import browser_build");
            window.__runcodeTimings = { setup_ms: Math.round(performance.now() - t0) };
            pyodideInstance = pyodide;
            return pyodide;
        })();
        pyodideLoading.catch(() => { pyodideLoading = null; });
    }
    return pyodideLoading;
}

const isDark = () => document.body.getAttribute('data-md-color-scheme') === 'slate';
const frames = new Set();
// The docs palette toggle changes body[data-md-color-scheme]; every viewer follows.
new MutationObserver(() => {
    for (const f of frames) f.contentWindow && f.contentWindow.postMessage({ type: 'runcode-theme', dark: isDark() }, '*');
}).observe(document.body, { attributes: true, attributeFilter: ['data-md-color-scheme'] });

function showViewer(outputArea, result, index) {
    const frame = document.createElement('iframe');
    frame.className = 'runcode-viewer';
    frame.title = 'Diagram of the code above (interactive viewer)';
    frame.src = RUNCODE_BASE + 'viewer/index.html' + result.focus.route;
    const onMessage = (e) => {
        if (e.source !== frame.contentWindow || !e.data || e.data.type !== 'runcode-ready') return;
        frame.contentWindow.postMessage({ type: 'runcode-data', files: result.files, dark: isDark() }, '*');
    };
    addEventListener('message', onMessage);
    frames.add(frame);
    const json = document.createElement('details');
    json.className = 'runcode-json';
    json.innerHTML = '<summary>Structurizr JSON</summary><pre></pre>';
    json.querySelector('pre').textContent = result.workspace_json;
    outputArea.replaceChildren(frame, json);
}

function copyOutput(index, button) {
    const outputArea = document.getElementById(`output-${index}`);

    // Extract just the text content from the pre element
    const preElement = outputArea.querySelector('pre');
    if (!preElement) {
        console.error('No output to copy');
        return;
    }

    const textToCopy = preElement.textContent;

    // Copy to clipboard
    navigator.clipboard.writeText(textToCopy).then(() => {
        // Show success feedback
        const originalText = button.innerHTML;
        button.innerHTML = '✓ Copied!';
        button.style.backgroundColor = '#4caf50';

        setTimeout(() => {
            button.innerHTML = originalText;
            button.style.backgroundColor = '';
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        const originalText = button.innerHTML;
        button.innerHTML = '✗ Failed';

        setTimeout(() => {
            button.innerHTML = originalText;
        }, 2000);
    });
}

function toggleOutput(index, button) {
    const outputArea = document.getElementById(`output-${index}`);

    if (outputArea.style.display !== 'none') {
        outputArea.style.display = 'none';
        button.innerHTML = '▶ Show';
    } else {
        outputArea.style.display = 'block';
        button.innerHTML = '▼ Hide';
    }
}


async function runCodeInBrowser(code, index, button) {
    const outputContainer = document.getElementById(`output-container-${index}`);
    const outputArea = document.getElementById(`output-${index}`);
    outputContainer.style.display = 'block';
    outputArea.style.display = 'block';
    outputArea.innerHTML = '<div class="loading" role="status">⏳ Loading Python and the viewer (the first time takes a few seconds)…</div>';
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '⏳ Running…';
    try {
        const pyodide = await initPyodide();
        const t0 = performance.now();
        const run = pyodide.globals.get('browser_build').run_snippet;
        const result = JSON.parse(run(wrapSnippet(code), '/rc/out/' + index));
        run.destroy();
        window.__runcodeTimings[index] = { run_ms: Math.round(performance.now() - t0), ms: result.ms, focus: result.focus };
        showViewer(outputArea, result, index);
    } catch (error) {
        const msg = String(error.message || error).split('\n').filter((l) => l.trim()).slice(-3).join('\n');
        outputArea.innerHTML = `<div class="output-error" role="alert"><strong>Error:</strong>\n${escapeHtml(msg)}</div>`;
    } finally {
        button.disabled = false;
        button.innerHTML = originalText;
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
