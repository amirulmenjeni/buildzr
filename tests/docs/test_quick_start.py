"""The Quick Start builds: every step of its model file runs, and the complete example builds into a workspace."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

import pytest

import buildzr.site.cli as cli
from tests.docs.blocks import Block, extract_blocks, no_run, stub_layout_unless_real

PAGE = "getting-started/quick-start.md"


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
    last = steps[-1].text.split("\n", 1)[1] if no_run(steps[-1].text) is not None else steps[-1].text
    assert last == complete.text
    assert no_run(complete.text) is None, "the complete example keeps its Run Code button"


def test_the_complete_example_builds_a_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 tmp_path_factory: pytest.TempPathFactory) -> None:
    stub_layout_unless_real(monkeypatch, tmp_path_factory.mktemp("static"))
    (tmp_path / ".git").mkdir()  # so that the config search stops here
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "hello.py").write_text(model_blocks()[-1].text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 0
    assert (tmp_path / ".buildzr" / "build" / "hello" / "index.html").is_file()
