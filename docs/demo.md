---
hide:
  - navigation
  - toc
---

# Try buildzr in your browser

Edit the Python model and press **Run**.

<div id="buildzr-demo" class="demo"></div>

<noscript>
The demo needs JavaScript. Without it, try buildzr with <a href="../getting-started/installation/">a local install</a>.
</noscript>

## Good to know

- **Your code runs in this browser tab.** Nothing you type is sent to a server. It runs with the permissions of this page, so run code you wrote or read, never code a stranger asked you to paste. The demo never runs code on its own.
- **A run ends after 30 seconds.** Press **Stop** (or <kbd>Esc</kbd>) to end it sooner. Press <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on a Mac) to run.
- **You get the viewer and the model JSON, not Java-based exports.** PlantUML, SVG and PNG export need Java, so use **Copy model JSON** here and [export locally](user-guide/export.md) for the rest.
- **Python has only the standard library and buildzr.** If your code creates several workspaces, the last one is drawn.

??? note "How it works"

    - Python runs in a Web Worker through Pyodide, so the page stays responsive. buildzr builds the workspace as `buildzr build` does, and the viewer is the one `buildzr serve` shows. Without a Web Worker the demo does not run, because it could not stop a runaway loop.
    - The first run downloads about 6 MB (Python from `cdn.jsdelivr.net`, the viewer from this site). Your browser keeps them, so later runs are fast. Offline, you can keep editing, but you need one online run first.
    - Your code is kept in this browser's local storage, so a reload does not lose it. **Reset** returns to the example you loaded last.
    - When you run again, the viewer keeps your place. A line such as `# focus: shop/api` or `# focus: view:production` picks where it opens the first time; see [Viewer links](viewer-hash-routes.md).
    - Code is limited to 50,000 characters and printed output to 20,000. The editor is plain text, so type spaces to indent and press <kbd>Tab</kbd> to move on.
