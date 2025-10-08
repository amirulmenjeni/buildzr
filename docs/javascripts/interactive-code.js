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
    headerTitle.innerHTML = '📄 Output';
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

async function initPyodide() {
    if (pyodideInstance) {
        return pyodideInstance;
    }

    if (pyodideLoading) {
        // Wait for existing load to complete
        while (pyodideLoading) {
            await new Promise(resolve => setTimeout(resolve, 100));
        }
        return pyodideInstance;
    }

    pyodideLoading = true;

    try {
        // loadPyodide is provided by the CDN script in mkdocs.yml
        pyodideInstance = await loadPyodide({
            indexURL: "https://cdn.jsdelivr.net/pyodide/v0.28.3/full/"
        });
        pyodideLoading = false;
        return pyodideInstance;
    } catch (error) {
        pyodideLoading = false;
        throw error;
    }
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

    console.log('[Interactive Code] Running code in browser for block', index);

    const outputContainer = document.getElementById(`output-container-${index}`);
    const outputArea = document.getElementById(`output-${index}`);

    // Show output container and area
    outputContainer.style.display = 'block';
    outputArea.style.display = 'block';
    outputArea.innerHTML = '<div class="loading">⏳ Loading Python environment (first time may take 10-30 seconds)...</div>';

    // Disable button
    const originalText = button.innerHTML;
    button.disabled = true;
    button.innerHTML = '⏳ Loading...';

    try {
        // Load Pyodide
        const pyodide = await initPyodide();

        console.log('[Interactive Code] Pyodide loaded');

        outputArea.innerHTML = '<div class="loading">📦 Installing buildzr package...</div>';

        // Try to install buildzr from PyPI
        try {
            await pyodide.loadPackage('micropip');
            const micropip = pyodide.pyimport('micropip');
            await micropip.install('buildzr');
            await micropip.install('typing-extensions')
            outputArea.innerHTML = '<div class="loading">✓ Package installed. Running code...</div>';
        } catch (installError) {
            outputArea.innerHTML = '<div class="loading">⚠️ Could not install buildzr. Running code anyway...</div>';
            await new Promise(resolve => setTimeout(resolve, 1000));
        }

        // Check if code already has Workspace context
        const hasWorkspaceContext = /with\s+Workspace\s*\([^)]*\)\s+as\s+\w+\s*:/i.test(code);

        // Check if code already has imports
        const hasImports = /from\s+buildzr\.dsl\s+import/i.test(code);

        // Prepare imports
        const imports = `from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    desc,
    Group,
    DeploymentEnvironment,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance,
    DeploymentGroup,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
)

`;

        let codeToRun = code;
        if (!hasWorkspaceContext) {
            // Wrap code with Workspace context and imports
            codeToRun = imports + `with Workspace('w') as w:
${code.split('\n').map(line => '    ' + line).join('\n')}
    w.to_json('workspace.json')`;
        } else {
            // Has Workspace context - prepend imports if missing and ensure to_json is called
            const hasToJson = /\.to_json\s*\(/i.test(code);

            if (!hasImports) {
                codeToRun = imports + code;
            }

            if (!hasToJson) {
                // Extract workspace variable name from "with Workspace(...) as var_name:"
                const workspaceVarMatch = code.match(/with\s+Workspace\s*\([^)]*\)\s+as\s+(\w+)\s*:/i);
                const workspaceVar = workspaceVarMatch ? workspaceVarMatch[1] : 'w';
                codeToRun = codeToRun + `\n${workspaceVar}.to_json('workspace.json')`;
            }
        }

        console.log('[Interactive Code] Code to run:\n', codeToRun);

        // Run the user's code
        try {
            await pyodide.runPythonAsync(codeToRun);

            let output = '';

            // Always try to read from workspace.json
            try {
                const jsonContent = pyodide.FS.readFile('workspace.json', { encoding: 'utf8' });
                // Pretty-format the JSON output
                const prettyJson = JSON.stringify(JSON.parse(jsonContent), null, 2);
                output = `<div class="output-stdout"><strong>Output (workspace.json):</strong>\n<pre>${escapeHtml(prettyJson)}</pre></div>`;
            } catch (fsError) {
                // workspace.json not found - throw error
                output = `<div class="output-error"><strong>Error:</strong>\nNo workspace.json file found.</div>`;
            }

            outputArea.innerHTML = output;

        } catch (execError) {
            outputArea.innerHTML = `<div class="output-error"><strong>Error:</strong>\n${escapeHtml(execError.message)}</div>`;
        }

    } catch (error) {
        outputArea.innerHTML = `<div class="output-error"><strong>Failed to load Python:</strong>\n${escapeHtml(error.message)}</div>`;
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
