"""The Quick Start builds: every step of its model file runs, and the complete example builds into a workspace."""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import buildzr.site.cli as cli
from buildzr.site.build import STATIC_DIR
from tests.docs.blocks import Block, extract_blocks
from tests.site.stub_layout import stub_layout
from tests.site.test_cli import make_static

PAGE = "getting-started/quick-start.md"
REAL = bool(shutil.which("node") or os.environ.get("BUILDZR_NODE")) and os.path.isfile(
    os.path.join(STATIC_DIR, "index.html")) and not os.environ.get("BUILDZR_DOCTEST_STUB")


def model_blocks() -> list[Block]:
    """The blocks the page tells the reader to save as ``workspaces/hello.py``, in page order."""
    return [b for b in extract_blocks(PAGE) if b.directive == ("file", "workspaces/hello.py")]


def test_the_page_has_the_steps_and_the_complete_example() -> None:
    assert len(model_blocks()) >= 2


@pytest.mark.parametrize("block", model_blocks(), ids=lambda b: b.id)
def test_every_step_runs(block: Block, tmp_path: Path) -> None:
    (tmp_path / "hello.py").write_text(block.text, encoding="utf-8")
    done = subprocess.run([sys.executable, "hello.py"], cwd=tmp_path, capture_output=True, text=True, timeout=120)
    assert done.returncode == 0, done.stderr
    assert sorted(p.name for p in tmp_path.iterdir()) == ["hello.py"], "a step must not write files"


def test_the_last_step_is_the_complete_example() -> None:
    *steps, complete = model_blocks()
    last = steps[-1].text.split("\n", 1)[1] if steps[-1].text.startswith("# norun\n") else steps[-1].text
    assert last == complete.text
    assert not complete.text.startswith("# norun"), "the complete example keeps its Run Code button"


def test_the_complete_example_builds_a_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path_factory: pytest.TempPathFactory) -> None:
    if not REAL:  # without Node, lay out with the stub, as the other doc tests do
        static = make_static(tmp_path_factory.mktemp("static"))
        real = cli.build_all

        def stub_build_all(path: str, out: str, *a: Any, **kw: Any) -> Any:
            return real(path, out, *a, **{**kw, "layout_fn": stub_layout, "static_dir": str(static)})

        monkeypatch.setattr(cli, "build_all", stub_build_all)
    (tmp_path / ".git").mkdir()  # so that the config search stops here
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "hello.py").write_text(model_blocks()[-1].text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 0
    assert (tmp_path / ".buildzr" / "build" / "hello" / "index.html").is_file()
