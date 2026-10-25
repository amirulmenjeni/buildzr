"""``buildzr serve --watch`` in a real browser: an open viewer reloads after a rebuild, and only then.

Needs Node and Playwright's Chromium (``cd viewer && npm ci && npx playwright install chromium``); skipped without.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import pytest

from buildzr.site.build import STATIC_DIR, build_all
from tests.site.test_broken import out_dir
from tests.site.test_cli import ROOT, WS_TEXT, project, stubbed  # noqa: F401  (fixture)
from tests.site.test_serve import Server

RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "live_reload_runner.mjs")
NODE = os.environ.get("BUILDZR_NODE") or shutil.which("node")

pytestmark = [
    pytest.mark.skipif(NODE is None, reason="node is not installed"),
    pytest.mark.skipif(not os.path.isdir(os.path.join(ROOT, "viewer", "node_modules", "playwright")),
                       reason="the viewer's npm packages (Playwright) are not installed"),
    pytest.mark.skipif(not os.path.isfile(os.path.join(STATIC_DIR, "index.html")), reason="the viewer is not built"),
]


@pytest.mark.usefixtures("stubbed")
def test_an_open_viewer_reloads_after_a_rebuild_and_not_after_a_failed_one(tmp_path: Path) -> None:
    root = project(tmp_path, ws=False)
    model = root / "workspaces" / "small.py"
    model.parent.mkdir()
    model.write_text(WS_TEXT)

    def rebuild(text: str) -> None:
        model.write_text(text)
        build_all(str(model.parent), str(out_dir(root)), only_stale=True, keep_good=True)
    rebuild(WS_TEXT)
    srv = Server(out_dir(root), live=True)
    assert NODE is not None
    shots = os.environ.get("BUILDZR_SHOTS")
    proc = subprocess.Popen([NODE, RUNNER, srv.base + "/small-fixture/", *([shots] if shots else [])],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    assert proc.stdin is not None and proc.stdout is not None

    def ask(command: str) -> str:
        assert proc.stdin is not None and proc.stdout is not None
        proc.stdin.write(command + "\n")
        proc.stdin.flush()
        return str(proc.stdout.readline()).strip()
    try:
        first = proc.stdout.readline().strip()
        if first == "" and proc.wait(60) == 77:
            pytest.skip("Playwright's Chromium is not installed")
        assert first == "ready"
        rebuild(WS_TEXT + "# an edit\n")
        assert ask("reload") == "reloaded"
        rebuild(WS_TEXT + "raise RuntimeError('boom')\n")  # kept: the last good build stays on screen
        assert ask("none") == "none"
        rebuild(WS_TEXT + "# fixed\n")
        assert ask("reload") == "reloaded"
        assert ask("none") == "none"  # one reload per rebuild, not a loop
        assert ask("done") == "embed-quiet"
        assert proc.wait(60) == 0
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()
        srv.close()
