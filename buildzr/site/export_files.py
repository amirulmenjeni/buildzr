"""``buildzr export``: the workspaces of a Python file -> Structurizr JSON, PlantUML, SVG and PNG files.

The model file runs in a fresh subprocess with a temporary folder as its working directory (so a ``save()`` call in it
does not write into your project), as in ``buildzr build``. The subprocess then writes one folder per workspace::

    OUT/<name>/workspace.json        format json
    OUT/<name>/<view key>.puml       format plantuml, and next to each image
    OUT/<name>/<view key>.svg|png    format svg, png

``<name>`` is the workspace name made safe for a folder name (:func:`buildzr.site.build.safe_name`), with ``-2``, ``-3``
... added when two workspaces of the file would share a folder. Exit codes: 0 ok, 1 the model file or the export
failed, 2 usage error (no such file or workspace).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import traceback
import warnings
from typing import Any, Iterable, Optional, Sequence

from buildzr.site.build import safe_name
from buildzr.site.export import load_workspaces

FORMATS = ("json", "plantuml", "svg", "png")
LAYOUTS = ("dot", "smetana")
JSON_FILE = "workspace.json"


class ExportError(Exception):
    """The export cannot go on; the message is meant for the user. ``code`` is the exit status."""

    def __init__(self, message: str, code: int = 1) -> None:
        super().__init__(message)
        self.code = code


def _name_of(ws: Any) -> str:
    name = getattr(getattr(ws, "model", None), "name", None)
    return name if isinstance(name, str) else ""


def select(found: Sequence[Any], name: Optional[str], index: Optional[int]) -> list[Any]:
    """The workspaces to export: all of ``found``, the one called ``name``, or the one at ``index`` (0-based)."""
    shown = ", ".join(f"{i}: {_name_of(ws) or '(no name)'}" for i, ws in enumerate(found))
    if name is None and index is None:
        return list(found)
    if index is not None:
        if not 0 <= index < len(found):
            raise ExportError(f"--index {index}: the file creates {len(found)} workspace"
                              f"{'' if len(found) == 1 else 's'} ({shown})", 2)
        return [found[index]]
    hits = [ws for ws in found if _name_of(ws) == name]
    if not hits:
        raise ExportError(f"--workspace: no workspace is named {name!r}; the file creates: {shown}", 2)
    if len(hits) > 1:
        raise ExportError(f"--workspace: {len(hits)} workspaces are named {name!r}; pick one with --index "
                          f"({shown})", 2)
    return hits


def folder_names(workspaces: Sequence[Any], stem: str) -> list[str]:
    """One folder name per workspace, in order; a name that is taken gets ``-2``, ``-3``, ..."""
    taken: set[str] = set()
    out: list[str] = []
    for ws in workspaces:
        base = safe_name(_name_of(ws), stem)
        name, n = base, 1
        while name in taken:
            n += 1
            name = f"{base}-{n}"
        taken.add(name)
        out.append(name)
    return out


def _preflight(formats: Sequence[str], layout: str) -> None:
    """Fail before any file is written when a diagram format cannot work on this machine."""
    if not any(f != "json" for f in formats):
        return
    try:
        from buildzr.sinks.plantuml_sink import PlantUmlRenderError, PlantUmlSink
    except ImportError as e:
        raise ExportError("plantuml, svg and png need jpype1. Install it with: pip install "
                          "\"buildzr[export-plantuml]\"") from e
    if layout == "dot" and any(f in ("svg", "png") for f in formats):
        try:
            PlantUmlSink._ensure_graphviz_available()
        except PlantUmlRenderError as e:
            raise ExportError(f"{e} (or pass --layout smetana, which needs no Graphviz)") from e


def export_workspaces(path: str, out: str, formats: Sequence[str], layout: str = "dot", pretty: bool = False,
                      workspace: Optional[str] = None, index: Optional[int] = None,
                      base: Optional[str] = None) -> int:
    """Run ``path`` in this process and write the files of its workspaces under ``out``; return the exit status.

    Call it in a fresh process with a scratch working directory (:func:`run`). ``base`` is the folder that printed
    paths are relative to (default: the working directory).
    """
    base = os.path.abspath(base or os.getcwd())
    path = os.path.abspath(path)
    out = os.path.abspath(out)
    created: list[Any] = []
    try:
        found = load_workspaces(path, created)
    except (Exception, SystemExit) as e:
        if isinstance(e, SystemExit) and e.code in (None, 0):
            found = created
        else:
            tb = e.__traceback__  # from the model file's first frame: buildzr's own frames say nothing
            while tb is not None and os.path.abspath(tb.tb_frame.f_code.co_filename) != path:
                tb = tb.tb_next
            traceback.print_exception(type(e), e, tb or e.__traceback__)
            print(f"buildzr: error: {os.path.basename(path)} raised an error; nothing was exported", file=sys.stderr)
            return 1
    try:
        if not found:
            raise ExportError(f"{path} creates no workspace: it needs a `with Workspace(...)` block")
        chosen = select(found, workspace, index)
        _preflight(formats, layout)
        stem = os.path.splitext(os.path.basename(path))[0]
        for ws, name in zip(chosen, folder_names(chosen, stem)):
            _write_one(ws, os.path.join(out, name), formats, layout, pretty, base)
    except ExportError as e:
        print(f"buildzr: error: {e}", file=sys.stderr)
        return e.code
    except Exception as e:  # PlantUmlRenderError, Java and disk problems
        print(f"buildzr: error: {type(e).__name__}: {e}", file=sys.stderr)
        return 1
    return 0


def _show(path: str, base: str) -> str:
    """``path`` relative to ``base`` (the folder the command was run in) when it is below it, else as it is."""
    rel = os.path.relpath(path, base)
    return path if rel.startswith("..") or os.path.isabs(rel) else rel


def _write_one(ws: Any, folder: str, formats: Sequence[str], layout: str, pretty: bool, base: str) -> None:
    os.makedirs(folder, exist_ok=True)
    for fmt in formats:
        if fmt == "json":
            written = [ws._save("json", os.path.join(folder, JSON_FILE), pretty=pretty)]
        else:
            written = list(ws._save(fmt, folder, layout=layout))
            if not written:
                print(f"buildzr: warning: {_name_of(ws) or 'a workspace'} has no views; no {fmt} file was written",
                      file=sys.stderr)
        for f in written:
            print(f"wrote {_show(f, base)}")


def run(path: str, out: str, formats: Sequence[str], layout: str = "dot", pretty: bool = False,
        workspace: Optional[str] = None, index: Optional[int] = None) -> int:
    """:func:`export_workspaces` in a fresh subprocess whose working directory is a temporary folder."""
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (root, env.get("PYTHONPATH", "")) if p)
    argv = ["--in-process", "--file", os.path.abspath(path), "--out", os.path.abspath(out), "--layout", layout,
            "--base", os.getcwd()]
    for f in formats:
        argv += ["--format", f]
    if pretty:
        argv.append("--pretty")
    if workspace is not None:
        argv += ["--workspace", workspace]
    if index is not None:
        argv += ["--index", str(index)]
    with tempfile.TemporaryDirectory() as tmp:
        return subprocess.run([sys.executable, "-m", "buildzr.site.export_files"] + argv, cwd=tmp, env=env).returncode


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m buildzr.site.export_files")
    ap.add_argument("--in-process", action="store_true", required=True)
    ap.add_argument("--file", required=True)
    ap.add_argument("--out", required=True)
    ap.add_argument("--format", action="append", choices=FORMATS, required=True)
    ap.add_argument("--layout", choices=LAYOUTS, default="dot")
    ap.add_argument("--pretty", action="store_true")
    ap.add_argument("--workspace", default=None)
    ap.add_argument("--index", type=int, default=None)
    ap.add_argument("--base", default=None)
    a =ap.parse_args(list(argv) if argv is not None else None)
    with warnings.catch_warnings():
        # A model file that still calls Workspace.save() is what the user is migrating away from with this command.
        warnings.filterwarnings("ignore", message=r"Workspace\.save\(\) is deprecated", category=DeprecationWarning)
        return export_workspaces(a.file, a.out, a.format, a.layout, a.pretty, a.workspace, a.index, a.base)


if __name__ == "__main__":
    sys.exit(main())
