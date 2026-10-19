"""Run Code in a real browser: build the docs, serve them, and press Run Code in Chromium.

Uses the Playwright and Chromium of the viewer tests (``viewer/node_modules``, ``npx playwright install chromium``)
through ``runcode_browser.mjs``, and Pyodide from cdn.jsdelivr.net as the published docs do.

For a test of a page's code blocks::

    from tests.docs.browser import browser_problem, run_page_blocks

    @pytest.mark.skipif(browser_problem() is not None, reason=str(browser_problem()))
    def test_views_page_runs() -> None:
        for r in run_page_blocks(["user-guide/views.md"])["user-guide/views.md"]:
            assert r["state"] in ("drawn", "nothing"), r

``state`` is ``drawn`` (the viewer drew it; ``nodes`` boxes on screen), ``nothing`` (the code ran but has nothing
to draw), or ``error`` (``error`` is the message box's text, ``errorLine`` the line as the page shows it).
"""

from __future__ import annotations

import functools
import http.server
import json
import os
import shutil
import subprocess
import sys
import tempfile
import threading
import urllib.request
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator, Optional

from tests.docs.blocks import DOCS, ROOT

SCRIPT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "runcode_browser.mjs")
PLAYWRIGHT = os.path.join(ROOT, "viewer", "node_modules", "playwright")
PYODIDE_PROBE = "https://cdn.jsdelivr.net/pyodide/v{}/full/pyodide.js"

Json = dict[str, Any]


@functools.lru_cache(maxsize=None)
def browser_problem() -> Optional[str]:
    """Why Run Code cannot be tested in a browser here, or ``None``."""
    node = shutil.which("node")
    if not node:
        return "node is not installed"
    if not os.path.isdir(PLAYWRIGHT):
        return "Playwright is not installed (npm ci in viewer/)"
    probe = subprocess.run([node, "-e", "const fs=require('fs');const p=require(process.argv[1]).chromium.executablePath();"
                            "process.exit(fs.existsSync(p)?0:1)", PLAYWRIGHT], capture_output=True)
    if probe.returncode != 0:
        return "Chromium is not installed (npx playwright install chromium in viewer/)"
    manifest = os.path.join(DOCS, "runcode", "manifest.json")
    if not os.path.isfile(manifest):
        return "the Run Code assets are not built (uv run python scripts/build_docs_assets.py)"
    with open(manifest, encoding="utf-8") as f:
        pyodide = json.load(f)["pyodide"]
    try:
        urllib.request.urlopen(urllib.request.Request(PYODIDE_PROBE.format(pyodide), method="HEAD"), timeout=10)
    except OSError as e:
        return f"cdn.jsdelivr.net cannot be reached ({e}): Pyodide comes from there"
    return None


def build_docs(out: Path, extra_pages: Optional[dict[str, str]] = None) -> Path:
    """``mkdocs build --strict`` of a copy of the docs (plus ``extra_pages``: name -> markdown) into ``out/site``."""
    docs = out / "docs"
    shutil.copytree(DOCS, docs)
    for name, text in (extra_pages or {}).items():
        (docs / name).write_text(text, encoding="utf-8")
    with open(os.path.join(ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        config = f.read()
    config = (config.replace("custom_dir: overrides", f"custom_dir: {ROOT}/overrides")
              .replace("- scripts/mkdocs_hooks.py", f"- {ROOT}/scripts/mkdocs_hooks.py"))
    (out / "mkdocs.yml").write_text(f"docs_dir: {docs}\nsite_dir: {out / 'site'}\n" + config, encoding="utf-8")
    done = subprocess.run([sys.executable, "-m", "mkdocs", "build", "--strict", "-q", "-f", str(out / "mkdocs.yml")],
                          capture_output=True, text=True, cwd=ROOT)
    if done.returncode != 0:
        raise RuntimeError("mkdocs build failed:\n" + done.stdout + done.stderr)
    return out / "site"


class _Quiet(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:
        pass


@contextmanager
def serve(folder: Path) -> Iterator[str]:
    """Serve ``folder`` on localhost; yields its URL (ending with ``/``)."""
    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), functools.partial(_Quiet, directory=str(folder)))
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_address[1]}/"
    finally:
        server.shutdown()
        server.server_close()


def run_node(mode: str, url: str, pages: list[str], timeout: float = 600) -> list[Json]:
    """Run ``runcode_browser.mjs MODE URL PAGES...``; its JSON lines."""
    node = shutil.which("node")
    assert node, "node is not installed"
    done = subprocess.run([node, SCRIPT, mode, url, *pages], capture_output=True, text=True, timeout=timeout, cwd=ROOT)
    if done.returncode != 0:
        raise RuntimeError(f"runcode_browser.mjs {mode} failed:\n{done.stdout}\n{done.stderr}")
    return [json.loads(line) for line in done.stdout.splitlines() if line.startswith("{")]


def page_url(page: str) -> str:
    """``user-guide/views.md`` -> ``user-guide/views/`` (mkdocs' directory URLs)."""
    stem = page[:-3] if page.endswith(".md") else page
    if stem == "index":
        return ""
    return (stem[:-len("/index")] if stem.endswith("/index") else stem) + "/"


def run_page_blocks(pages: list[str]) -> dict[str, list[Json]]:
    """Press Run Code on every block of each docs page (``getting-started/quick-start.md``), in Chromium, one after
    the other; page -> one result per block (see the module docstring). Builds the docs into a temporary folder."""
    with tempfile.TemporaryDirectory() as tmp:
        site = build_docs(Path(tmp))
        with serve(site) as url:
            lines = run_node("blocks", url, [page_url(p) for p in pages])
    by_url = {line["page"]: line for line in lines}
    out: dict[str, list[Json]] = {}
    for p in pages:
        line = by_url[page_url(p)]
        if line["errors"]:
            raise RuntimeError(f"{p}: errors on the page: {line['errors']}")
        out[p] = line["results"]
    return out
