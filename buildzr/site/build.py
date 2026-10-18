"""``buildzr build``: DSL file -> static site directory.

Output (relative URLs only, so it works at ``/`` and under any subpath)::

    DIR/index.html, DIR/assets/...   the viewer bundle (``buildzr/site/static/``)
    DIR/data/model.<h8>.json, index.json, scene/...
    DIR/build.json                   versions, k, modelHash, input hash; no timestamps
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import shutil
import sys
import tempfile
from typing import Any, Callable, Optional

from buildzr.site import canonical
from buildzr.site.export import run_export

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: ``layout_site(levels, model, data_dir, k=...)`` of ``buildzr.site.layout`` (W2).
LayoutFn = Callable[..., Any]


class BuildError(Exception):
    """A build step failed; the message is meant for the user."""


def _sha256_file(path: str) -> str:
    with open(path, "rb") as f:
        return "sha256:" + hashlib.sha256(f.read()).hexdigest()


def _version() -> str:
    try:
        from importlib.metadata import version
        return version("buildzr")
    except Exception:
        return "unknown"


def _default_layout() -> LayoutFn:
    try:
        mod = importlib.import_module("buildzr.site.layout")
    except ImportError as e:
        raise BuildError("the layout stage (buildzr.site.layout) is not available: " + str(e)) from e
    return mod.layout_site  # type: ignore[no-any-return]


def swap_dir(new: str, dest: str) -> None:
    """Replace ``dest`` by ``new`` with renames, so a reader never sees a half-written directory."""
    dest = os.path.abspath(dest)
    old = None
    if os.path.exists(dest):
        old = tempfile.mkdtemp(prefix=".old-", dir=os.path.dirname(dest))
        os.rmdir(old)
        os.rename(dest, old)
    os.rename(new, dest)
    if old:
        shutil.rmtree(old, ignore_errors=True)


def build_site(workspace: str, out: str = ".buildzr/site", k: Optional[int] = None, text_color: Optional[str] = None,
               viewer: bool = True, layout_fn: Optional[LayoutFn] = None,
               static_dir: str = STATIC_DIR, verbose: bool = False) -> dict[str, Any]:
    """Build ``workspace`` into ``out``. Returns the ``build.json`` object.

    ``k`` and ``text_color`` default to 4 and ``"wcag"``; the CLI fills them from ``buildzr.yaml`` first.
    The output directory is replaced atomically. With ``verbose`` the step that runs the model file prints its summary
    line (``FILE: N elements, ... -> FOLDER``); errors are shown either way.
    """
    workspace = os.path.abspath(workspace)
    if not os.path.isfile(workspace):
        raise BuildError(f"workspace file not found: {workspace}")
    k = 4 if k is None else k
    text_color = "wcag" if text_color is None else text_color
    if text_color not in ("wcag", "c4"):
        raise BuildError(f"text_color must be 'wcag' or 'c4', not {text_color!r}")
    if viewer and not os.path.isfile(os.path.join(static_dir, "index.html")):
        raise BuildError(f"the viewer bundle is missing ({static_dir}/index.html); build the viewer "
                         "or pass --no-viewer for data only")
    layout = layout_fn or _default_layout()
    out = os.path.abspath(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".build-", dir=os.path.dirname(out))
    try:
        stage = os.path.join(tmp, "export")
        if run_export(workspace, stage, text_color=text_color, quiet=not verbose) != 0:
            raise BuildError(f"executing {workspace} failed (see the error above)")
        with open(os.path.join(stage, "model.json"), encoding="utf-8") as f:  # staging name, not the site's
            model = json.load(f)
        with open(os.path.join(stage, "levels.json"), encoding="utf-8") as f:
            levels = json.load(f)
        site = os.path.join(tmp, "site")
        data = os.path.join(site, "data")
        os.makedirs(data)
        layout(levels, model, data, k=k)  # writes data/model.<h8>.json, index.json and the scenes
        if viewer:
            for name in sorted(os.listdir(static_dir)):
                src = os.path.join(static_dir, name)
                dst = os.path.join(site, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        elk = None
        try:
            elk = getattr(importlib.import_module("buildzr.site.layout"), "ELK_VERSION", None)
        except ImportError:
            pass
        info = {"buildzr": _version(), "elkjs": elk, "k": k, "textColor": text_color,
                "modelHash": model["modelHash"],
                "input": {"file": os.path.basename(workspace), "sha256": _sha256_file(workspace)}}
        canonical.write(os.path.join(site, "build.json"), info)
        swap_dir(site, out)
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def warn(msg: str) -> None:
    print(f"buildzr: {msg}", file=sys.stderr)
