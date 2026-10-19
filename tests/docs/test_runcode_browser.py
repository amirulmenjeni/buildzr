"""Run Code in Chromium on a built copy of the docs with a test page (``pages/runcode-smoke.md``): nothing is
loaded before the first press, the diagram is drawn and scrolled to, errors name the line the reader sees, and the
copy controls say what they copy. Skipped (with the reason) where no browser, Node or network is available."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any, Iterator

import pytest

from tests.docs.blocks import DOCS
from tests.docs.browser import browser_problem, build_docs, run_node, serve

PAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "pages", "runcode-smoke.md")

pytestmark = pytest.mark.skipif(browser_problem() is not None, reason=f"Run Code browser test: {browser_problem()}")

Json = dict[str, Any]


@pytest.fixture(scope="module")
def smoke(tmp_path_factory: pytest.TempPathFactory) -> Iterator[list[Json]]:
    with open(PAGE, encoding="utf-8") as f:
        site = build_docs(tmp_path_factory.mktemp("docs"), {"runcode-smoke.md": f.read()})
    with serve(site) as url:
        yield run_node("smoke", url, ["runcode-smoke/"])


def check(lines: list[Json], name: str) -> list[Json]:
    found = [x for x in lines if x.get("check") == name]
    assert found, f"no {name!r} in {lines}"
    return found


def test_nothing_is_loaded_before_the_first_press(smoke: list[Json]) -> None:
    before = check(smoke, "before the first press")[0]
    assert before["runcode"] == [] and before["cdn"] == 0
    assert before["blocks"] == 3  # the `# no-run` block has no button


def test_first_block_draws_and_scrolls(smoke: list[Json]) -> None:
    first = check(smoke, "first block")[0]
    assert first["state"] == "drawn" and first["nodes"] >= 1, first
    assert first["where"]["topInView"] or first["where"]["atPageEnd"], first["where"]
    assert first["frameSrc"].startswith("index.html?embed=1&theme=light#/m/shop?sel=shop/database"), first["frameSrc"]
    assert first["focus"]["cls"] == "runcode-output", "focus moves to the diagram region"
    assert first["thread"] in ("worker", "main")
    assert first["cdnRequests"] > 0 and first["runcodeRequests"] > 0


def test_second_block_draws_a_fragment(smoke: list[Json]) -> None:
    second = check(smoke, "block")[0]
    assert second["state"] == "drawn" and second["nodes"] >= 2, second


def test_error_names_the_line_the_reader_sees(smoke: list[Json]) -> None:
    broken = check(smoke, "block")[1]
    # line 6 of the source; the hidden `# focus:` line above it is not shown, so the reader sees it as line 5
    assert broken["state"] == "error" and broken["errorLine"] == 5, broken
    assert "line 5" in broken["error"] and "NameError: name 'sytem' is not defined" in broken["error"]
    assert "Traceback" not in broken["error"]
    assert broken["errorLineText"].strip() == "user >> 'uses' >> sytem"


def test_copy_controls_say_what_they_copy(smoke: list[Json]) -> None:
    code = check(smoke, "code copy")[0]
    assert code["materialCopyTitle"] == "Copy this code"
    assert code["sourceHasFocus"] and not code["copiedHasFocus"] and code["copiedIsShown"], code
    model = check(smoke, "model JSON control")[0]
    assert model["text"] == "Copy model JSON" and "Structurizr JSON" in model["title"]
    assert model["after"] == "Copied!" and model["copiedIsJson"]
    assert not model["jsonOpen"] and model["summary"] == "Show model JSON"
    assert model["toggle"] == "Hide diagram" and model["status"] == "status"


def test_diagrams_follow_the_docs_theme(smoke: list[Json]) -> None:
    theme = check(smoke, "theme")[0]
    assert theme["scheme"] == "slate" and theme["frameThemes"] and set(theme["frameThemes"]) == {"dark"}, theme


def test_open_in_a_new_tab(smoke: list[Json]) -> None:
    tab = check(smoke, "new tab")[0]
    assert tab["button"] == 1 and "new browser tab" in tab["label"], tab
    assert "handoff=" in tab["url"] and "embed=1" not in tab["url"] and tab["nodes"] >= 1, tab
    assert tab["openerGoneMessage"] and "Go back to that page" in tab["openerGoneMessage"], tab


def test_no_page_errors(smoke: list[Json]) -> None:
    assert check(smoke, "page errors")[0]["errors"] == []


def test_build_docs_needs_no_repo_changes(tmp_path: Path) -> None:
    """The helper builds a copy: the docs folder of the repository is left alone."""
    before = sorted(os.listdir(DOCS))
    build_docs(tmp_path, {"extra.md": "# Extra\n"})
    assert (tmp_path / "site" / "extra" / "index.html").is_file()
    assert sorted(os.listdir(DOCS)) == before


def test_quick_start_examples_draw() -> None:
    """A real docs page through the helper other doc tests use: every Run Code block draws."""
    from tests.docs.browser import run_page_blocks

    results = run_page_blocks(["getting-started/quick-start.md"])["getting-started/quick-start.md"]
    assert results, "no Run Code blocks on the Quick Start page"
    for r in results:
        assert r["state"] == "drawn" and r["nodes"] >= 1, r
