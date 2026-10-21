"""Build a workspace in memory: the "Run Code" button of the docs, under Pyodide in the reader's browser.

The same stages as ``buildzr build`` run here: ``export_model`` -> ``build_levels`` -> the three-pass layout
(:class:`~buildzr.site.layout.passes.Layouter`) -> ``write_workspace``. Only the ELK runner differs: in the browser
there is no Node process, so :class:`JsElkRunner` calls ``elkLayoutSync``, the synchronous elkjs function that
``buildzr/site/layout/browser_elk.js`` defines in the same JavaScript realm. The files are byte for byte the ones the
normal build writes into ``data/`` (``tests/site/test_browser.py`` proves it for the docs snippets).

Nothing in normal use imports this module. The docs page calls :func:`run_snippet` with the text of a code block.
"""

from __future__ import annotations

import contextlib
import io
import json
import os
import re
import runpy
import tempfile
import traceback
from dataclasses import dataclass
from typing import Any, Optional, Protocol

from buildzr.site.layout.passes import Layouter
from buildzr.site.levels import build_levels
from buildzr.site.model import DRAWN_TYPES, export_model
from buildzr.site.scene import write_workspace

Json = dict[str, Any]

#: Added before a snippet that does not import the DSL itself.
PRELUDE = "from buildzr.dsl import *\n"
_HAS_WORKSPACE = re.compile(r"with\s+Workspace\s*\([^)]*\)\s+as\s+\w+\s*:", re.I)
_HAS_IMPORT = re.compile(r"from\s+buildzr\.dsl\s+import", re.I)
#: ``# focus: <element id>`` or ``# focus: view:<key>``: where the viewer opens (see :func:`focus_for`).
FOCUS = re.compile(r"^[ \t]*#[ \t]*focus:[ \t]*(\S+)[ \t]*$", re.M)
#: View kinds the model canvas cannot show: a snippet that defines one of these is about that view.
OWN_CANVAS = ("deployment", "dynamic")
#: Printed output kept for the page (a snippet that prints a whole workspace JSON stays readable).
MAX_STDOUT = 20_000
#: Longest snippet :func:`run_snippet` accepts (characters). The docs' browser demo limits its editor to half of this.
MAX_CODE = 100_000


class ElkLike(Protocol):
    def layout(self, graphs: dict[str, Json]) -> dict[str, Json]: ...


@dataclass(frozen=True)
class Wrapped:
    """A snippet made runnable: line ``n`` of the snippet is line ``n + offset`` of ``code``."""

    code: str
    offset: int


class SnippetError(Exception):
    """The snippet failed: ``line`` is a line of the snippet as the page shows it (1-based), when one is known."""

    def __init__(self, message: str, line: Optional[int] = None, source: str = "") -> None:
        super().__init__(message)
        self.message = message
        self.line = line
        self.source = source

    def to_json(self) -> Json:
        return {"message": self.message, "line": self.line, "source": self.source}


def wrap_snippet(code: str) -> Wrapped:
    """The docs show fragments: add ``from buildzr.dsl import *`` when the snippet has no such import, and put a
    fragment without ``with Workspace(...) as name:`` inside one (indented)."""
    if not _HAS_WORKSPACE.search(code):
        body = "\n".join("    " + ln for ln in code.split("\n"))
        return Wrapped(PRELUDE + "with Workspace('w') as w:\n" + body + "\n", 2)
    if _HAS_IMPORT.search(code):
        return Wrapped(code, 0)
    return Wrapped(PRELUDE + code, 1)


def run_code(code: str) -> tuple[Any, str]:
    """Run a snippet as a fresh process would and return the last ``Workspace`` it created.

    Element ids start at 1 again (the DSL counts them per process). Returns ``(workspace, printed text)``.
    Raises :class:`SnippetError` with the snippet's line when the snippet fails.
    """
    from buildzr.dsl import Workspace
    from buildzr.dsl.factory import GenerateId

    wrapped = wrap_snippet(code)
    lines = code.splitlines()
    created: list[Any] = []
    orig = Workspace.__init__

    def recording_init(self: Any, *a: Any, **kw: Any) -> None:
        orig(self, *a, **kw)
        created.append(self)

    out = io.StringIO()
    GenerateId.reset()
    Workspace.__init__ = recording_init  # type: ignore[method-assign]
    try:
        with tempfile.TemporaryDirectory() as folder:
            # Run as `buildzr build` runs a file (runpy.run_path): the module name shows in style tags of lambdas.
            path = os.path.join(folder, "snippet.py")
            with open(path, "w", encoding="utf-8") as f:
                f.write(wrapped.code)
            try:
                with contextlib.redirect_stdout(out):
                    runpy.run_path(path)
            except SyntaxError as e:
                line = _user_line(e.lineno if e.filename == path else None, wrapped.offset, len(lines))
                raise SnippetError(f"SyntaxError: {e.msg}", line, _line_text(lines, line)) from None
            except BaseException as e:  # noqa: BLE001 - SystemExit and KeyboardInterrupt from the reader's code too
                found = [fs.lineno for fs in traceback.extract_tb(e.__traceback__) if fs.filename == path]
                line = _user_line(found[-1] if found else None, wrapped.offset, len(lines))
                text = str(e)
                raise SnippetError(f"{type(e).__name__}: {text}" if text else type(e).__name__, line,
                                   _line_text(lines, line)) from None
    finally:
        Workspace.__init__ = orig  # type: ignore[method-assign]
    if not created:
        raise SnippetError("the code created no Workspace, so there is nothing to draw")
    return created[-1], out.getvalue()


def _user_line(lineno: Optional[int], offset: int, count: int) -> Optional[int]:
    if lineno is None:
        return None
    n = lineno - offset
    return n if 1 <= n <= count else None


def _line_text(lines: list[str], line: Optional[int]) -> str:
    return lines[line - 1].strip() if line is not None else ""


def build_files(workspace: Any, runner: ElkLike, k: float = 4.0) -> tuple[dict[str, str], Json]:
    """The ``data/`` folder of a built workspace, as relative path -> text, and the model.

    Same stages and options as ``buildzr build`` (text colour ``wcag``, frame budget ``k`` 4).
    """
    model = export_model(workspace)
    levels = build_levels(workspace, model, text_color="wcag")
    lay = Layouter(levels, runner, k=k)  # type: ignore[arg-type]
    lay.layout_generated()
    lay.layout_views()
    files: dict[str, str] = {}
    with tempfile.TemporaryDirectory() as out:
        write_workspace(out, model, levels, lay.placed)
        for root, _dirs, names in os.walk(out):
            for name in names:
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as f:
                    files[os.path.relpath(path, out).replace(os.sep, "/")] = f.read()
    return files, model


def focus_for(code: str, model: Json) -> Json:
    """Where the viewer opens for a snippet: ``{"route": "#/...", "why": ...}``, ``route`` a viewer hash route.

    1. A ``# focus: <element id>`` comment (the viewer's id, such as ``shop/api``) or ``# focus: view:<key>``.
    2. Else, when the snippet defines a deployment or dynamic view, the first one (the model canvas cannot show it).
    3. Else the model canvas, with the last-created element that has children expanded.
    4. Else (nothing has children) the whole landscape.

    Raises :class:`SnippetError` when the comment names nothing in the model (a mistake of the page's author).
    """
    m = FOCUS.search(code)
    if m:
        target = m.group(1)
        line = code.count("\n", 0, m.start()) + 1
        if target.startswith("view:"):
            key = target[len("view:"):]
            if key not in {v["key"] for v in model["views"]}:
                raise SnippetError(f"# focus: there is no view {key!r}", line, m.group(0).strip())
            return {"route": "#/v/" + key, "why": "marker"}
        el = next((e for e in model["elements"] if e["id"] == target), None)
        if el is None:
            ids = ", ".join(sorted(e["id"] for e in model["elements"]))
            raise SnippetError(f"# focus: there is no element {target!r} (ids: {ids})", line, m.group(0).strip())
        path = target if el["children"] else (el["parent"] or "")
        return {"route": f"#/m/{path}?sel={target}" if path else f"#/m?sel={target}", "why": "marker"}
    own = [v for v in model["views"] if v["kind"] in OWN_CANVAS]
    if own:
        return {"route": "#/v/" + own[0]["key"], "why": f"{own[0]['kind']} view"}
    drawn = [e for e in model["elements"] if e["type"] in DRAWN_TYPES and e["children"]]
    if drawn:
        last = max(drawn, key=lambda e: int(e["modelId"]) if str(e["modelId"]).isdigit() else -1)
        return {"route": "#/m/" + last["id"], "why": "last element with children"}
    return {"route": "#/m", "why": "landscape"}


def build_snippet(code: str, runner: ElkLike, k: float = 4.0) -> Json:
    """Run ``code`` and build what the viewer needs: ``files`` (the ``data/`` folder), ``focus`` (see
    :func:`focus_for`), ``workspaceJson`` (the Structurizr JSON), ``stdout`` and ``drawn`` (boxes over all scenes).
    Raises :class:`SnippetError`."""
    workspace, stdout = run_code(code)
    try:
        files, model = build_files(workspace, runner, k)
        workspace_json = workspace.to_json()
    except Exception as e:  # noqa: BLE001 - the model the reader wrote cannot be drawn
        raise SnippetError(f"the workspace could not be drawn: {type(e).__name__}: {e}") from None
    focus = focus_for(code, model)
    drawn = sum(len(json.loads(text).get("nodes", [])) for path, text in files.items() if path.startswith("scene/"))
    if len(stdout) > MAX_STDOUT:
        stdout = stdout[:MAX_STDOUT] + "\n…"
    return {"files": files, "focus": focus, "workspaceJson": workspace_json, "stdout": stdout, "drawn": drawn}


class JsElkRunner:
    """The ELK runner of the browser: same ``layout(graphs)`` as :class:`buildzr.site.layout.elk.ElkRunner`, backed
    by ``elkLayoutSync`` of ``browser_elk.js`` in this JavaScript realm (Pyodide's ``js`` module)."""

    def __init__(self) -> None:
        import js  # type: ignore[import-not-found]  # Pyodide only

        self._sync = js.elkLayoutSync
        self.total_ms = 0.0
        self.calls = 0

    def layout(self, graphs: dict[str, Json]) -> dict[str, Json]:
        if not graphs:
            return {}
        resp = json.loads(self._sync(json.dumps(graphs, separators=(",", ":"))))
        out: dict[str, Json] = {}
        for name, r in resp.items():
            if "error" in r:
                raise RuntimeError(f"ELK failed on {name}: {r['error']}")
            self.total_ms += float(r["ms"])
            out[name] = r["graph"]
        self.calls += len(out)
        return out


def run_snippet(code: str) -> str:
    """The entry point of the docs page: JSON ``{"ok": true, ...}`` (see :func:`build_snippet`) or
    ``{"ok": false, "error": {"message", "line", "source"}}``. Never raises for a mistake in the snippet."""
    try:
        if len(code) > MAX_CODE:
            raise SnippetError(f"the code is {len(code):,} characters long; the limit is {MAX_CODE:,}")
        result = {"ok": True, **build_snippet(code, JsElkRunner())}
    except SnippetError as e:
        result = {"ok": False, "error": e.to_json()}
    return json.dumps(result)
