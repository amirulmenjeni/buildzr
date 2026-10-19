"""Helpers of the doc tests: fenced code blocks of a page, the directives before them, output normalising, and a
build that uses the stub layout when the real one cannot run."""

from __future__ import annotations

import glob
import json
import os
import re
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "docs")
SKILLS = os.path.join(ROOT, "skills")

#: The pages whose examples are tested: the Publishing section in its order, then the Getting Started pages.
PAGES = ["serve-workspaces.md", "cli.md", "config.md", "publishing-recipes.md", "hosting.md", "ui-settings.md",
         "viewer-hash-routes.md", "model-api.md", "getting-started/quick-start.md", "getting-started/ai-agents.md",
         "user-guide/deployment.md"]

FENCE = re.compile(r"^(\s*)```([\w+-]*)(?:\s+\w[^`]*)?\s*$")  # attributes such as hl_lines="2-4" may follow
DIRECTIVE = re.compile(r"^<!--\s*doctest:\s*(\w+)\s*(.*?)\s*-->\s*$")


@dataclass
class Block:
    """One fenced code block. ``directive`` is ``(name, argument)`` of the ``<!-- doctest: ... -->`` line before it."""

    page: str
    line: int  # 1-based line of the opening fence
    lang: str
    text: str
    directive: Optional[tuple[str, str]] = None

    @property
    def id(self) -> str:
        return f"{self.page}:{self.line}"


def extract_blocks(page: str, root: str = DOCS) -> list[Block]:
    """The fenced blocks of ``page``, a path relative to ``root`` (the docs folder, or the skills folder)."""
    with open(os.path.join(root, page), encoding="utf-8") as f:
        lines = f.read().split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        indent, lang = m.group(1), m.group(2)
        j = i + 1
        body: list[str] = []
        while j < len(lines):
            closing = FENCE.match(lines[j])
            if closing and not closing.group(2):
                break
            body.append(lines[j][len(indent):] if lines[j].startswith(indent) else lines[j])
            j += 1
        directive: Optional[tuple[str, str]] = None
        k = i - 1
        if k >= 0 and not lines[k].strip():
            k -= 1
        if k >= 0:
            d = DIRECTIVE.match(lines[k].strip())
            if d:
                directive = (d.group(1), d.group(2))
        blocks.append(Block(page, i + 1, lang, "\n".join(body) + "\n", directive))
        i = j + 1
    return blocks


def doc_pages() -> list[str]:
    """Every page of the docs folder, relative to it, in a fixed order."""
    found = [os.path.relpath(os.path.join(d, f), DOCS) for d, _, files in os.walk(DOCS) for f in files
             if f.endswith(".md")]
    return sorted(p.replace(os.sep, "/") for p in found)


# --- Run Code ---------------------------------------------------------------------------------------------

#: The first line of a python block that gets no Run Code button; the reason follows the colon.
NO_RUN = re.compile(r"^#\s*no-?run\b:?\s*(.*)$")

RUN_CODE_JS = os.path.join(DOCS, "javascripts", "interactive-code.js")


def no_run(text: str) -> Optional[str]:
    """The reason of a ``# no-run: reason`` first line (``""`` when the reason is missing), ``None`` when the block
    runs. Run Code reads the same line (``interactive-code.js``)."""
    m = NO_RUN.match(text.strip().split("\n", 1)[0])
    return m.group(1).strip() if m else None


def run_code_source(text: str) -> tuple[str, int]:
    """The program that the Run Code button runs for a snippet (``wrap_snippet`` of ``buildzr.site.browser``), and
    the number of lines it adds before the snippet's first line: a snippet without ``with Workspace(...) as w:``
    runs inside one, and a snippet that imports nothing from ``buildzr.dsl`` gets ``from buildzr.dsl import *``."""
    from buildzr.site.browser import wrap_snippet

    wrapped = wrap_snippet(text.rstrip("\n"))
    return wrapped.code, wrapped.offset


# --- building -----------------------------------------------------------------------------------------------


def real_layout() -> bool:
    """Whether builds can use the real layout: Node and the built viewer are there, and no test forces the stub."""
    from buildzr.site.build import STATIC_DIR

    return bool(shutil.which("node") or os.environ.get("BUILDZR_NODE")) and os.path.isfile(
        os.path.join(STATIC_DIR, "index.html")) and not os.environ.get("BUILDZR_DOCTEST_STUB")


def stub_layout_unless_real(monkeypatch: pytest.MonkeyPatch, static_dir: Path) -> None:
    """Without the real layout, make ``buildzr.site.cli`` build with the stub layout and a stand-in viewer in
    ``static_dir`` (an empty folder), and skip the checks that the stub's scenes cannot pass."""
    if real_layout():
        return
    import buildzr.site.build as build_mod
    import buildzr.site.cli as cli
    from tests.site.stub_layout import stub_layout
    from tests.site.test_cli import make_static

    static = make_static(static_dir)
    real = cli.build_all

    def stub_build_all(path: str, out: str, *a: Any, **kw: Any) -> Any:
        return real(path, out, *a, **{**kw, "layout_fn": stub_layout, "static_dir": str(static)})

    monkeypatch.setattr(cli, "build_all", stub_build_all)
    monkeypatch.setattr(cli, "_node_problem", lambda: None)
    monkeypatch.setattr(build_mod, "check_workspace", lambda data_dir: [])  # the stub's scenes fit no page model


def authored_views(source: str, name: str) -> dict[str, set[str]]:
    """The view keys of the one workspace that ``source`` makes, by Structurizr view list. Runs ``source`` in the
    current folder."""
    from buildzr.dsl import Workspace

    scope: dict[str, object] = {"__name__": "__main__"}
    exec(compile(source, name, "exec"), scope)
    [w] = [v for v in scope.values() if isinstance(v, Workspace)]
    views = json.loads(w.to_json()).get("views", {})
    return {key: {v["key"] for v in items} for key, items in views.items() if isinstance(items, list) and items}


def build_and_check_views(source: str, name: str, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                          tmp_path_factory: pytest.TempPathFactory) -> dict[str, set[str]]:
    """Build ``source`` with ``buildzr build`` as the only model file of a project in ``tmp_path``. Every view of
    the workspace is built and, with the real layout, a deployment view draws deployment nodes and a dynamic view
    its steps (the stub layout's scenes are fixtures). Returns the view keys by Structurizr view list."""
    import buildzr.site.cli as cli

    stub_layout_unless_real(monkeypatch, tmp_path_factory.mktemp("static"))
    (tmp_path / ".git").mkdir()  # so that the config search stops here
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "model.py").write_text(source, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    written = authored_views(source, name)
    assert cli.main(["build"]) == 0
    built = list((tmp_path / ".buildzr" / "build").iterdir())
    assert len(built) == 1 and (built[0] / "index.html").is_file(), built
    with open(glob.glob(str(built[0] / "data" / "model.*.json"))[0], encoding="utf-8") as f:
        model_views = json.load(f)["views"]
    built_views = {v["viewKey"] for v in model_views}
    assert built_views == set().union(*written.values()), "every view is built, deployment and dynamic views too"
    if not real_layout():
        return written
    with open(built[0] / "data" / "index.json", encoding="utf-8") as f:
        scenes = json.load(f)["scenes"]
    for v in model_views:
        if v["viewKey"] in written.get("deploymentViews", set()) | written.get("dynamicViews", set()):
            assert v["kind"] in ("deployment", "dynamic") and v["scene"] in scenes, v
            with open(built[0] / "data" / scenes[v["scene"]]["file"], encoding="utf-8") as f:
                scene = json.load(f)
            if v["kind"] == "deployment":
                drawn = {n["type"] for n in scene["nodes"]}
                assert "DeploymentNode" in drawn, f"deployment view {v['viewKey']} draws no deployment node: {drawn}"
            else:
                assert scene["edges"], f"dynamic view {v['viewKey']} draws no step"
    return written


# --- output normalising -------------------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sha256:[0-9a-f]{64}"), "sha256:HASH"),
    (re.compile(r"sha256:[0-9a-f]{4,}…?"), "sha256:HASH"),
    (re.compile(r"(?<![\w:/.])/[\w.@+\-/]+"), "<PATH>"),
    (re.compile(r"(?<=[\d\]]):\d{2,5}\b"), ":PORT"),
    (re.compile(r"\b\d+ ms\b"), "N ms"),
]


def normalise(line: str) -> str:
    """Hashes, absolute paths, ports, file counts and sizes, and timings replaced by fixed words."""
    for pat, repl in _RULES:
        line = pat.sub(repl, line)
    return line.rstrip()


def same_lines(expected: list[str], actual: list[str]) -> Optional[str]:
    """``None`` when ``actual`` matches ``expected`` after normalising (a line ``...`` stands for any lines), else a
    message that shows both."""
    exp = [normalise(x) for x in expected]
    act = [normalise(x) for x in actual]

    def match(i: int, j: int) -> bool:
        if i == len(exp):
            return j == len(act)
        if exp[i] == "...":
            return any(match(i + 1, k) for k in range(j, len(act) + 1))
        return j < len(act) and exp[i] == act[j] and match(i + 1, j + 1)

    if match(0, 0):
        return None
    return "expected:\n  " + "\n  ".join(exp) + "\nactual:\n  " + "\n  ".join(act)


# --- JSON shapes ------------------------------------------------------------------------------------------

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _kind(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    return "array" if isinstance(v, list) else "object"


def compare_json(doc: Any, live: Any, where: str = "$", values: bool = True,
                 ignore: frozenset[str] = frozenset()) -> list[str]:
    """Differences between the JSON of a page (``doc``) and a live answer: same keys, same types (a ``null`` on
    either side stands for 'depends on the build') and, with ``values``, the same values. Keys in ``ignore`` are
    only checked for their type. A ``modelHash`` is a hash on both sides."""
    out: list[str] = []
    kd, kl = _kind(doc), _kind(live)
    if kd == "null" or kl == "null":
        return out
    if kd != kl:
        return [f"{where}: the page has {kd}, the server answers {kl}"]
    if isinstance(doc, dict):
        if set(doc) != set(live):
            out.append(f"{where}: keys differ: only on the page {sorted(set(doc) - set(live))}, "
                       f"only in the answer {sorted(set(live) - set(doc))}")
        for k in doc:
            if k in live:
                out += compare_json(doc[k], live[k], f"{where}.{k}", values and k not in ignore, ignore)
    elif isinstance(doc, list):
        if doc and live:
            if values:
                if len(doc) != len(live):
                    out.append(f"{where}: the page lists {len(doc)} items, the server {len(live)}")
                for n, (a, b) in enumerate(zip(doc, live)):
                    out += compare_json(a, b, f"{where}[{n}]", values, ignore)
            else:
                out += compare_json(doc[0], live[0], f"{where}[0]", values, ignore)
    elif values and doc != live:
        if isinstance(doc, str) and _HASH.match(doc) and isinstance(live, str) and _HASH.match(live):
            return out
        out.append(f"{where}: the page has {doc!r}, the server answers {live!r}")
    return out
