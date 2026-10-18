"""Stage 0 entry point: write ``model.json`` and ``levels.json`` for a workspace.

Usage::

    python -m buildzr.site.export --workspace FILE.py --out DIR

executes the DSL file in a fresh subprocess (cwd = a temporary directory, since
examples call ``save()`` at import time) and exports the ``Workspace`` it
creates. Files are canonical JSON (see :mod:`buildzr.site.canonical`).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
from typing import Any, Iterable, Optional

from buildzr.site import canonical
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model


def export(workspace: Any, out_dir: str, text_color: str = "wcag") -> tuple[dict[str, Any], dict[str, Any]]:
    """Write ``out_dir/model.json`` and ``out_dir/levels.json``; return both objects."""
    model = export_model(workspace)
    levels = build_levels(workspace, model, text_color=text_color)
    os.makedirs(out_dir, exist_ok=True)
    canonical.write(os.path.join(out_dir, "model.json"), model)
    canonical.write(os.path.join(out_dir, "levels.json"), levels)
    return model, levels


def load_workspaces(path: str) -> list[Any]:
    """Run the DSL file at ``path`` in this process and return the workspaces it created.

    Files inside a package (``tests/samples``) are imported as modules; their builder
    classes (a class with a ``build()`` method) are instantiated and built when the
    import itself created no workspace. Call this in a fresh process with a scratch cwd.
    """
    import importlib
    import inspect
    import runpy

    from buildzr.dsl import Workspace

    created: list[Any] = []
    orig_init = Workspace.__init__

    def recording_init(self: Any, *a: Any, **kw: Any) -> None:
        orig_init(self, *a, **kw)
        created.append(self)

    Workspace.__init__ = recording_init  # type: ignore[method-assign]
    try:
        path = os.path.abspath(path)
        d = os.path.dirname(path)
        parts = [os.path.splitext(os.path.basename(path))[0]]
        while os.path.exists(os.path.join(d, "__init__.py")):
            parts.insert(0, os.path.basename(d))
            d = os.path.dirname(d)
        if len(parts) > 1:
            sys.path.insert(0, d)
            ns = vars(importlib.import_module(".".join(parts)))
        else:
            sys.path.insert(0, os.path.dirname(path))
            ns = runpy.run_path(path)
        if not created:
            for v in list(ns.values()):
                if inspect.isclass(v) and v.__module__ == ns.get("__name__") and hasattr(v, "build"):
                    getattr(v(), 'build')()
    finally:
        Workspace.__init__ = orig_init  # type: ignore[method-assign]
    return created


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m buildzr.site.export", description=__doc__.splitlines()[0])
    ap.add_argument("--workspace", required=True, help="DSL .py file that creates a Workspace")
    ap.add_argument("--out", required=True, help="output directory")
    ap.add_argument("--index", type=int, default=-1, help="which workspace if the file creates several (default: last)")
    ap.add_argument("--text-color", choices=["wcag", "c4"], default="wcag")
    ap.add_argument("--in-process", action="store_true", help=argparse.SUPPRESS)
    ap.add_argument("--quiet", action="store_true", help=argparse.SUPPRESS)  # no summary line (buildzr build)
    args = ap.parse_args(list(argv) if argv is not None else None)
    out = os.path.abspath(args.out)
    if args.in_process:
        found = load_workspaces(args.workspace)
        if not found:
            print(f"no Workspace created by {args.workspace}", file=sys.stderr)
            return 2
        model, levels = export(found[args.index], out, args.text_color)
        if not args.quiet:
            print(f"{args.workspace}: {len(model['elements'])} elements, {len(model['relationships'])} relationships, "
                  f"{len(model['views'])} views, {len(levels['levels'])} levels -> {out}")
        return 0
    return run_export(args.workspace, out, args.index, args.text_color)


def run_export(workspace: str, out: str, index: int = -1, text_color: str = "wcag", quiet: bool = False) -> int:
    """Export ``workspace`` (a DSL file) into ``out`` in a fresh subprocess with a scratch cwd.

    ``quiet`` leaves out the summary line of the subprocess; whatever the model file prints, and every error, still shows.
    """
    root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    env = dict(os.environ)
    env["PYTHONPATH"] = os.pathsep.join(p for p in (root, env.get("PYTHONPATH", "")) if p)
    with tempfile.TemporaryDirectory() as tmp:
        cmd = [sys.executable, "-m", "buildzr.site.export", "--in-process", "--workspace",
               os.path.abspath(workspace), "--out", os.path.abspath(out), "--index", str(index),
               "--text-color", text_color] + (["--quiet"] if quiet else [])
        return subprocess.run(cmd, cwd=tmp, env=env).returncode


if __name__ == "__main__":
    sys.exit(main())
