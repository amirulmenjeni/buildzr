"""Every python block of the docs runs as its Run Code button runs it, unless it opts out with a reason.

Every page of the docs folder is read (and ``README.md``, whose parts make the home page). A python block runs the way
``docs/javascripts/interactive-code.js`` runs it in the browser (``blocks.run_code_source``): wrapped in a workspace
when it has none, with the imports when it has none, and saved as ``workspace.json``, which Run Code shows. A block
whose first line is ``# no-run: <reason>`` gets no Run Code button; it must still compile, and the reasons are
printed by ``test_opt_outs_name_a_reason``. The pages of ``WRONG_ON_PURPOSE`` show a typo and the error it gives;
their blocks with the typo must fail with that error.
"""

from __future__ import annotations

import json
import os
import re
import traceback
from pathlib import Path

import pytest

from tests.docs.blocks import (DOCS, ROOT, RUN_CODE_JS, Block, build_and_check_views, doc_pages, extract_blocks,
                               no_run, run_code_imports, run_code_source)

#: Fences that the docs build would not give a Run Code button, so they would escape this test.
OTHER_PYTHON = {"py", "python3", "pycon"}

#: Pages that show a typo on purpose: the misspelt name, and the error that Run Code shows for it.
WRONG_ON_PURPOSE = {
    "config.md": ("databse", "NameError: name 'databse' is not defined"),
    "serve-workspaces.md": ("databse", "NameError: name 'databse' is not defined"),
}


def snippet_pages() -> list[tuple[str, str]]:
    """``(page, root)`` of every page with python blocks shown in the docs."""
    return [(p, DOCS) for p in doc_pages()] + [("README.md", ROOT)]


def python_blocks() -> list[tuple[Block, int]]:
    """Every python block, with its number on its page (1 for the first python block)."""
    out = []
    for page, root in snippet_pages():
        for n, b in enumerate((b for b in extract_blocks(page, root) if b.lang == "python"), 1):
            out.append((b, n))
    return out


BLOCKS = python_blocks()
RUNNABLE = [(b, n) for b, n in BLOCKS if no_run(b.text) is None]
OPTED_OUT = [(b, n) for b, n in BLOCKS if no_run(b.text) is not None]


def page_line(block: Block, added: int, lineno: int) -> int:
    """The page line of line ``lineno`` of the program that Run Code made of ``block``."""
    return block.line + lineno - added


@pytest.mark.parametrize("block,n", RUNNABLE, ids=[b.id for b, _ in RUNNABLE])
def test_snippet_runs_like_run_code(block: Block, n: int, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    source, added = run_code_source(block.text)
    monkeypatch.chdir(tmp_path)
    where = f"{block.page}, python block {n} (line {block.line})"
    typo, error = WRONG_ON_PURPOSE.get(block.page, ("", ""))
    failure = None
    try:
        exec(compile(source, block.id, "exec"), {"__name__": "__main__"})
    except Exception as e:
        if typo and typo in block.text and f"{type(e).__name__}: {e}" == error:
            return
        frames = [f for f in traceback.extract_tb(e.__traceback__) if f.filename == block.id]
        at = f", page line {page_line(block, added, frames[-1].lineno or 0)}" if frames else ""
        failure = f"{where}{at}: {type(e).__name__}: {e}"
    if failure:
        pytest.fail(failure, pytrace=False)  # outside the except: the page, the block and the error, no traceback
    assert not (typo and typo in block.text), f"{where}: the typo on purpose no longer fails with {error}"
    saved = tmp_path / "workspace.json"
    assert saved.is_file(), f"{where}: Run Code finds no workspace.json"
    with open(saved, encoding="utf-8") as f:
        assert isinstance(json.load(f), dict), f"{where}: workspace.json is not a workspace"


VIEWS_TO_BUILD = re.compile(r"\b(?:DeploymentView|DynamicView)\(")
BUILT = [(b, n) for b, n in RUNNABLE if VIEWS_TO_BUILD.search(b.text) and b.page not in WRONG_ON_PURPOSE
         and "buildzr.models" not in b.text]  # the Models API page builds no DSL workspace


@pytest.mark.parametrize("block,n", BUILT, ids=[b.id for b, _ in BUILT])
def test_deployment_and_dynamic_view_snippets_build(block: Block, n: int, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     tmp_path_factory: pytest.TempPathFactory) -> None:
    """``buildzr build`` builds and draws them: deployment nodes in a deployment view, steps in a dynamic view."""
    written = build_and_check_views(run_code_source(block.text)[0], block.id, tmp_path, monkeypatch,
                                    tmp_path_factory)
    assert {"deploymentViews", "dynamicViews"} & set(written), f"{block.id}: no deployment or dynamic view is built"


def test_deployment_and_dynamic_views_are_shown() -> None:
    pages = {b.page for b, _ in BUILT}
    assert {"user-guide/views.md", "user-guide/deployment.md", "user-guide/models.md", "user-guide/themes.md"} <= pages


#: What Run Code cannot do in the browser: Pyodide has no Java for PlantUML, and the test runs without the network.
NEEDS_JAVA_OR_NETWORK = re.compile(r"format=['\"](?:plantuml|svg|png)['\"]|\.to_(?:plantuml|svg)\(|\.as_inline\(|"
                                   r"extend=['\"]https?:")


def test_runnable_snippets_need_no_java_and_no_network() -> None:
    """These would pass here (the devcontainer has Java) and fail on the page; they opt out."""
    found = [b.id for b, _ in RUNNABLE if NEEDS_JAVA_OR_NETWORK.search(b.text)]
    assert not found, found


@pytest.mark.parametrize("block,n", OPTED_OUT, ids=[b.id for b, _ in OPTED_OUT])
def test_opted_out_snippet_compiles(block: Block, n: int) -> None:
    compile(block.text, block.id, "exec")


def test_opt_outs_name_a_reason(capsys: pytest.CaptureFixture[str]) -> None:
    with capsys.disabled():
        for b, n in OPTED_OUT:
            print(f"\nno-run {b.id} (block {n}): {no_run(b.text)}")
    missing = [b.id for b, _ in OPTED_OUT if not re.match(r"# no-run: \S", b.text.lstrip())]
    assert not missing, f"start the block with '# no-run: <reason>': {missing}"


def test_every_page_is_read() -> None:
    """New pages are read too: the pages are found on disk, not listed."""
    on_disk = {os.path.relpath(os.path.join(d, f), DOCS).replace(os.sep, "/")
               for d, _, files in os.walk(DOCS) for f in files if f.endswith(".md")}
    assert on_disk == set(doc_pages())
    assert len(RUNNABLE) >= 80


@pytest.mark.parametrize("page,root", snippet_pages(), ids=[p for p, _ in snippet_pages()])
def test_python_blocks_are_fenced_as_python(page: str, root: str) -> None:
    """A ``py`` fence gets no Run Code button and no test; write ``python``."""
    other = [b.id for b in extract_blocks(page, root) if b.lang in OTHER_PYTHON]
    assert not other, other


def test_the_wrapping_is_the_one_of_run_code() -> None:
    """``run_code_source`` copies the rules of ``interactive-code.js``; this fails when the script changes them."""
    with open(RUN_CODE_JS, encoding="utf-8") as f:
        js = f.read()
    for rule in (r"/with\s+Workspace\s*\([^)]*\)\s+as\s+\w+\s*:/i", r"/from\s+buildzr\.dsl\s+import/i",
                 r"/\.save\s*\(/i", "codeToRun = imports + `with Workspace('w') as w:",
                 ".map(line => '    ' + line).join('\\n')}\n    w.save(path='workspace.json')`;",
                 "code.startsWith('# no-run') || code.startsWith('# norun')",
                 "pyodide.FS.readFile('workspace.json'"):
        assert rule in js, f"interactive-code.js changed: {rule!r}; update tests/docs/blocks.run_code_source"
    assert "Workspace," in run_code_imports()
