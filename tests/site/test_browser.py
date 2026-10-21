"""The in-memory build of the docs' Run Code (``buildzr.site.browser``), run under CPython.

The browser runs the same module under Pyodide with the synchronous elkjs of ``browser_elk.js``. Here that JS runs
on Node (``browser_elk_runner.mjs``), so the comparison with the normal build covers the browser's ELK call too.
"""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Iterator

import pytest

from buildzr.dsl.factory import GenerateId
from buildzr.site.browser import (SnippetError, Wrapped, build_files, build_snippet, focus_for, run_code,
                                  run_workspaces, unique_name, wrap_snippet)
from buildzr.site.export import load_workspaces
from buildzr.site.layout import elk
from buildzr.site.layout.elk import ElkEnvironmentError, ElkRunner
from buildzr.site.layout.passes import Layouter
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model
from buildzr.site.scene import write_workspace
from tests.docs.blocks import DOCS, extract_blocks

needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")
SYNC_RUNNER = os.path.join(os.path.dirname(os.path.abspath(__file__)), "browser_elk_runner.mjs")
#: Docs snippets the spike proved identical (2026-10-19); fixing broken snippets only raises the count.
MIN_IDENTICAL = 61

Json = dict[str, Any]


class SyncElkRunner(ElkRunner):
    """The browser's synchronous elkjs (``browser_elk.js``), on Node, with the protocol of ``runner.mjs``."""

    def start(self) -> None:
        self._proc = subprocess.Popen([elk.find_node(), SYNC_RUNNER, self.bundle], stdin=subprocess.PIPE,
                                      stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        if not self._read().get("ready"):
            raise ElkEnvironmentError("the browser ELK runner did not start")


# --- wrapping and errors -------------------------------------------------------------------------------------


def test_fragment_goes_inside_a_workspace() -> None:
    w = wrap_snippet("a = Person('A')\nb = SoftwareSystem('B')\n")
    assert w == Wrapped("from buildzr.dsl import *\nwith Workspace('w') as w:\n    a = Person('A')\n"
                        "    b = SoftwareSystem('B')\n    \n", 2)


def test_import_added_only_when_missing() -> None:
    code = "with Workspace('x') as w:\n    Person('A')\n"
    assert wrap_snippet(code) == Wrapped("from buildzr.dsl import *\n" + code, 1)
    full = "from buildzr.dsl import Workspace, Person\n" + code
    assert wrap_snippet(full) == Wrapped(full, 0)


@pytest.mark.parametrize("code, line, message", [
    # fragment (offset 2), with a workspace but no import (offset 1), complete (offset 0)
    ("a = Person('A')\nb = Persn('B')\n", 2, "NameError: name 'Persn' is not defined"),
    ("with Workspace('x') as w:\n    a = Person('A')\n    a >> 'uses' >> missing\n", 3,
     "NameError: name 'missing' is not defined"),
    ("from buildzr.dsl import *\n\nwith Workspace('x') as w:\n    Person('A', fontSize=3)\n", 4, "TypeError"),
    ("from buildzr.dsl import *\nwith Workspace('x') as w:\n    Person('A'\n", 3, "SyntaxError"),
    ("a = Person('A')\nb = Person('B'\n", 2, "SyntaxError"),
])
def test_errors_name_the_line_of_the_snippet(code: str, line: int, message: str) -> None:
    with pytest.raises(SnippetError) as e:
        run_code(code)
    assert e.value.line == line, e.value.to_json()
    assert e.value.message.startswith(message)
    assert "Traceback" not in e.value.message


def test_error_inside_buildzr_points_at_the_snippet_line() -> None:
    code = "with Workspace('x') as w:\n    s = SoftwareSystem('S')\n    SystemContextView(software_system_selector=s, key='k')\n"
    with pytest.raises(SnippetError) as e:
        run_code(code)
    assert e.value.line == 3 and e.value.source.startswith("SystemContextView(")


def test_no_workspace_is_an_error_without_a_line() -> None:
    with pytest.raises(SnippetError, match="no Workspace") as e:
        run_code("def later():\n    with Workspace('x') as w:\n        pass\n")
    assert e.value.line is None


def test_ids_start_again_for_every_snippet() -> None:
    code = "with Workspace('x') as w:\n    Person('A')\n"
    GenerateId.for_element()
    first, _ = run_code(code)
    second, _ = run_code(code)
    assert export_model(first)["elements"][0]["modelId"] == export_model(second)["elements"][0]["modelId"] == "1"


def test_printed_text_is_kept() -> None:
    _, printed = run_code("with Workspace('x') as w:\n    print('hello')\n")
    assert printed == "hello\n"


# --- several workspaces in one snippet (the viewer's switcher) ---------------------------------------------


TWO = """\
with Workspace('Shop') as shop:
    SoftwareSystem('Store')
with Workspace('Billing') as billing:
    SoftwareSystem('Ledger')
"""


def test_every_workspace_of_a_snippet_is_run() -> None:
    created, _ = run_workspaces(TWO)
    assert len(created) == 2
    last, _ = run_code(TWO)
    assert export_model(last)["workspace"]["name"] == "Billing"  # run_code is still "the last one"
    assert len(run_workspaces("with Workspace('x') as w:\n    Person('P')\n")[0]) == 1


@pytest.mark.parametrize("names, want", [
    (["Shop", "Billing"], ["Shop", "Billing"]),
    (["w", "w", "w"], ["w", "w (2)", "w (3)"]),
    (["a", "a (2)", "a"], ["a", "a (2)", "a (3)"]),
])
def test_workspaces_of_a_snippet_get_distinct_names(names: list[str], want: list[str]) -> None:
    seen: set[str] = set()
    assert [unique_name(n, seen) for n in names] == want


@needs_node
def test_a_snippet_with_several_workspaces_builds_all_and_opens_the_last(runners: tuple[ElkRunner, ElkRunner]) -> None:
    result = build_snippet(TWO, runners[1])
    assert [w["name"] for w in result["workspaces"]] == ["Shop", "Billing"] and result["active"] == "Billing"
    for w in result["workspaces"]:
        assert set(w) == {"name", "files", "focus", "workspaceJson"} and "index.json" in w["files"]
    shop, billing = result["workspaces"]
    assert shop["files"] != billing["files"] and '"Shop"' in shop["workspaceJson"]
    # the keys of a one-workspace snippet are those of the last: the page that ignores "workspaces" works as before
    assert result["files"] == billing["files"] and result["workspaceJson"] == billing["workspaceJson"]
    assert result["focus"] == billing["focus"] and result["drawn"] > 0


@needs_node
def test_one_workspace_adds_no_list_and_a_marker_names_the_last(runners: tuple[ElkRunner, ElkRunner]) -> None:
    single = build_snippet(SHOP, runners[1])
    assert "workspaces" not in single and "active" not in single
    # "# focus:" is about the workspace the page shows; the others open on their defaults and cannot fail on it
    result = build_snippet(TWO + "# focus: ledger\n", runners[1])
    assert result["focus"]["route"] == "#/m?sel=ledger"
    assert result["workspaces"][0]["focus"]["why"] in ("landscape", "last element with children")


def test_a_workspace_that_cannot_be_drawn_stops_the_snippet() -> None:
    with pytest.raises(SnippetError, match="could not be drawn: RuntimeError: elk exploded"):
        build_snippet(TWO, _FailingRunner())


class _FailingRunner:
    total_ms = 0.0
    calls = 0

    def layout(self, graphs: Json) -> Json:
        raise RuntimeError("elk exploded")


# --- focus -------------------------------------------------------------------------------------------------


def _model(code: str) -> Json:
    workspace, _ = run_code(code)
    return export_model(workspace)


SHOP = """\
with Workspace('w') as w:
    user = Person('User')
    with SoftwareSystem('Shop') as shop:
        api = Container('API')
        db = Container('Database')
    with SoftwareSystem('Mail') as mail:
        Container('SMTP')
    user >> 'uses' >> shop
"""


def test_focus_marker_wins() -> None:
    model = _model(SHOP)
    assert focus_for(SHOP + "# focus: shop/database\n", model) == {"route": "#/m/shop?sel=shop/database",
                                                                   "why": "marker"}
    assert focus_for("# focus: shop\n" + SHOP, model)["route"] == "#/m/shop?sel=shop"
    assert focus_for("#focus: user\n" + SHOP, model)["route"] == "#/m?sel=user"


def test_focus_marker_must_name_something() -> None:
    model = _model(SHOP)
    with pytest.raises(SnippetError, match="no element 'shop/db'") as e:
        focus_for(SHOP + "# focus: shop/db\n", model)
    assert e.value.line == SHOP.count("\n") + 1
    with pytest.raises(SnippetError, match="no view 'nope'"):
        focus_for("# focus: view:nope\n" + SHOP, model)


def test_focus_last_element_with_children_then_landscape() -> None:
    assert focus_for(SHOP, _model(SHOP)) == {"route": "#/m/mail", "why": "last element with children"}
    flat = "with Workspace('w') as w:\n    Person('A') >> 'uses' >> SoftwareSystem('B')\n"
    assert focus_for(flat, _model(flat)) == {"route": "#/m", "why": "landscape"}


def test_focus_deployment_or_dynamic_view() -> None:
    code = SHOP + """\
    with DeploymentEnvironment('Live') as live:
        with DeploymentNode('Server'):
            ContainerInstance(api)
    DeploymentView(software_system_selector=shop, environment=live, key='live', description='Live')
"""
    assert focus_for(code, _model(code)) == {"route": "#/v/live", "why": "deployment view"}
    assert focus_for("# focus: view:live\n" + code, _model(code))["route"] == "#/v/live"


# --- the same files as the normal build ---------------------------------------------------------------------


def docs_snippets() -> list[tuple[str, str]]:
    """``(page:line, code)`` of every python block of the docs that has a Run Code button (no ``# no-run``)."""
    out: list[tuple[str, str]] = []
    for path in sorted(glob.glob(os.path.join(DOCS, "**", "*.md"), recursive=True)):
        page = os.path.relpath(path, DOCS)
        for b in extract_blocks(page):
            first = next((ln.strip() for ln in b.text.splitlines() if ln.strip()), "")
            if b.lang == "python" and not first.startswith(("# no-run", "# norun")):
                out.append((b.id, b.text))
    return out


@pytest.fixture(scope="module")
def runners() -> Iterator[tuple[ElkRunner, ElkRunner]]:
    with ElkRunner() as normal, SyncElkRunner() as sync:
        yield normal, sync


def _normal_build(code: str, folder: Path, runner: ElkRunner) -> dict[str, str]:
    """The stages of ``buildzr build`` (``load_workspaces``, ``export_model``, ``build_levels``, then what
    ``layout_workspace`` does) on the snippet as Run Code wraps it, in a fresh id space."""
    src = folder / "snippet.py"
    src.write_text(wrap_snippet(code).code, encoding="utf-8")
    GenerateId.reset()
    workspace = load_workspaces(str(src))[-1]
    model = export_model(workspace)
    levels = build_levels(workspace, model, text_color="wcag")
    lay = Layouter(levels, runner, k=4.0)
    lay.layout_generated()
    lay.layout_views()
    out = folder / "data"
    write_workspace(str(out), model, levels, lay.placed)
    return {p.relative_to(out).as_posix(): p.read_text(encoding="utf-8") for p in out.rglob("*") if p.is_file()}


@needs_node
def test_browser_build_equals_normal_build_for_every_docs_snippet(
        runners: tuple[ElkRunner, ElkRunner], tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    normal_runner, sync_runner = runners
    # As in the browser, no jpype: a snippet that exports to PlantUML fails in both builds. (Starting the JVM in
    # this process would also make later tests that recurse deeply crash.)
    monkeypatch.setitem(sys.modules, "jpype", None)
    identical: list[str] = []
    different: list[str] = []
    only_one_fails: list[str] = []
    both_fail = 0
    for n, (where, code) in enumerate(docs_snippets()):
        folder = tmp_path / str(n)
        folder.mkdir()
        monkeypatch.chdir(folder)  # snippets that call save() write here
        try:
            want = _normal_build(code, folder, normal_runner)
        except Exception:  # noqa: BLE001 - a broken docs snippet: the doc tests of its page report it
            want = None
        try:
            got: Any = build_snippet(code, sync_runner)["files"]
        except SnippetError as e:
            got = e
        if want is None or isinstance(got, SnippetError):
            if (want is None) != isinstance(got, SnippetError):
                only_one_fails.append(f"{where}: normal {'fails' if want is None else 'builds'}, browser {got!r}")
            else:
                both_fail += 1
            continue
        (identical if got == want else different).append(where)
    print(f"identical={len(identical)} different={len(different)} fail in both={both_fail}")
    assert not different, f"browser build differs from the normal build: {different}"
    assert not only_one_fails, only_one_fails
    assert len(identical) >= MIN_IDENTICAL, f"only {len(identical)} snippets built ({both_fail} fail in both)"


@needs_node
def test_build_files_is_a_data_folder(runners: tuple[ElkRunner, ElkRunner]) -> None:
    workspace, _ = run_code(SHOP)
    files, model = build_files(workspace, runners[1])
    assert "index.json" in files and any(p.startswith("model.") for p in files)
    assert any(p.startswith("scene/") for p in files)
    result = build_snippet(SHOP, runners[1])
    assert result["files"] == files and result["drawn"] > 0 and result["focus"]["route"] == "#/m/mail"
    assert '"name": "w"' in result["workspaceJson"] or '"name":"w"' in result["workspaceJson"]
