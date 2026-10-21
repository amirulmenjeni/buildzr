---
hide:
  - navigation
  - toc
---

# Try buildzr in your browser

Edit a buildzr model and explore the diagram it draws, side by side (stacked on a phone). Nothing to install and nothing to sign in to: your code runs in this browser tab, and nothing you type is sent to a server.

<div id="buildzr-demo" class="demo" data-demo-samples="demo/samples.json"></div>

<noscript>
The demo needs JavaScript. Without it, try buildzr with <a href="../getting-started/installation/">a local install</a>.
</noscript>

## How it works

- **Write a model.** The editor takes the same Python as a model file. Start from an example, or write your own with `Workspace`, `Person`, `SoftwareSystem` and the other [building blocks](user-guide/core-concepts.md). A fragment without `with Workspace(...)` works too.
- **Run it.** Press **Run** or use <kbd>Ctrl</kbd>+<kbd>Enter</kbd> (<kbd>Cmd</kbd>+<kbd>Enter</kbd> on a Mac). Python runs in a Web Worker, so the page stays responsive, and buildzr builds the workspace as `buildzr build` does.
- **Explore it.** The viewer is the one `buildzr serve` shows: open the model tree with ☰, select elements to see their details, open the views, and use **Open in a new tab** for the full viewer. When you run again, the viewer keeps your place when it can.
- **Choose where it opens.** A comment line such as `# focus: shop/api` or `# focus: view:production` picks what the viewer shows after your first run. See [Viewer links](viewer-hash-routes.md).

Your code is kept in this browser (local storage) so a reload does not lose it. **Reset** goes back to the chosen example.

## Keyboard

| Key | Does |
| --- | --- |
| <kbd>Ctrl</kbd>+<kbd>Enter</kbd> or <kbd>Cmd</kbd>+<kbd>Enter</kbd> in the editor | Runs the code |
| <kbd>Esc</kbd> while code runs | Stops the run (when focus is in the editor or on a button) |
| <kbd>Tab</kbd> | Moves focus on, as on any page. The editor does not capture it, so type spaces to indent |

## Limitations

- **The first run downloads about 6 MB** (Python, from `cdn.jsdelivr.net`, and the viewer from this site) and takes a few seconds. Your browser keeps them, so later runs are fast. **Offline:** you can keep editing, but nothing runs until the files have been downloaded once while online; the demo tells you when it cannot start.
- **A Web Worker is required.** Without one the demo refuses to run, because code on the page itself cannot be stopped.
- **Runs are stopped after 30 seconds.** A loop that never ends ends the run, not your tab. Code is limited to 50,000 characters, and printed output to 20,000.
- **Only the standard library and buildzr are available.** There is no `pip`, no network access you can rely on and no files that outlive the run. PlantUML, SVG and PNG export need Java and are not in the browser; the demo shows the model's Structurizr JSON instead (**Copy model JSON**).
- **Code runs with the permissions of this page.** It is sandboxed by your browser only, like any script on a web page. Run code you wrote or read, not code a stranger asked you to paste. The demo never runs code by itself: not from a link, and not from the draft it restores.
- **It builds one workspace.** If your code creates several, the last one is drawn.
- **Desktop and phone.** The two panes sit side by side on a wide screen and stack on a phone. The editor is plain text with no syntax highlighting or line numbers; an error names its line and a button selects it.
