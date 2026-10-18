"""``buildzr build``: the Python files of a workspaces folder -> one built workspace per ``Workspace``.

The build output holds one folder per workspace, named after it (see :func:`safe_name`)::

    OUT/<name>/index.html, OUT/<name>/assets/...   the viewer bundle (``buildzr/site/static/``)
    OUT/<name>/data/model.<h8>.json, index.json, scene/...
    OUT/<name>/build.json                          versions, k, modelHash, source file, fingerprint; no timestamps

Relative URLs only, so a built workspace works at any path. Each Python file runs in a fresh subprocess; a built
workspace is written to a temporary folder and then renamed into place, so a reader never sees half of one.
"""

from __future__ import annotations

import hashlib
import importlib
import json
import os
import re
import shutil
import sys
import tempfile
from dataclasses import dataclass, field
from typing import Any, Callable, Iterable, Optional

from buildzr.site import canonical
from buildzr.site.export import read_export_list, run_export, run_export_all

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: ``layout_workspace(levels, model, data_dir, k=...)`` of ``buildzr.site.layout`` (W2).
LayoutFn = Callable[..., Any]

#: Names a built workspace cannot take: they would hide a file or an address of ``buildzr serve``.
RESERVED_NAMES = ("api", "assets", "data", "_buildzr", "index.html", "build.json", "llms.txt")
NAME_MAX = 64
FINGERPRINT_VERSION = "buildzr.fingerprint/1"


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
    return mod.layout_workspace  # type: ignore[no-any-return]


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


# --- the workspaces folder ----------------------------------------------------------------------


def _skipped(name: str) -> bool:
    return name.startswith((".", "_"))


def find_sources(path: str) -> list[str]:
    """The Python files to run for ``path``: the file itself, or every ``.py`` below the folder.

    Names starting with ``_`` or ``.`` are skipped, files and folders alike (``_helpers.py`` holds shared code;
    ``__pycache__`` goes too). Sorted by relative path, so the order is the same on every machine.
    """
    path = os.path.abspath(path)
    if os.path.isfile(path):
        return [path]
    found: list[str] = []
    for root, dirs, files in os.walk(path):
        dirs[:] = sorted(d for d in dirs if not _skipped(d))
        found += [os.path.join(root, f) for f in sorted(files) if f.endswith(".py") and not _skipped(f)]
    return sorted(found, key=lambda p: os.path.relpath(p, path).split(os.sep))


def find_helpers(folder: str) -> list[str]:
    """Every ``_*.py`` file below ``folder`` (not in folders whose name starts with ``.``, nor ``__pycache__``)."""
    found: list[str] = []
    for root, dirs, files in os.walk(os.path.abspath(folder)):
        dirs[:] = sorted(d for d in dirs if not d.startswith(".") and d != "__pycache__")
        found += [os.path.join(root, f) for f in sorted(files) if f.startswith("_") and f.endswith(".py")]
    return sorted(found)


def source_root(path: str) -> str:
    """The workspaces folder of ``path``: the folder itself, or the folder holding the file."""
    path = os.path.abspath(path)
    return path if os.path.isdir(path) else os.path.dirname(path)


def relative_source(file: str, root: str) -> str:
    """``file`` relative to the workspaces folder ``root``, with ``/`` separators (as ``build.json`` records it)."""
    return os.path.relpath(os.path.abspath(file), root).replace(os.sep, "/")


def safe_name(name: str, stem: str) -> str:
    """The folder name of a workspace: lowercase, ``[a-z0-9._-]`` only, starting with a letter or digit, ≤ 64 chars.

    Other characters become ``-``. An empty result falls back to the file stem (made safe the same way), then to
    ``workspace``. Reserved names (:data:`RESERVED_NAMES`) are returned as they are; :func:`check_name` refuses them.
    """
    for text in (name, stem, "workspace"):
        s = re.sub(r"[^a-z0-9._-]", "-", (text or "").lower())
        s = re.sub(r"^[^a-z0-9]+", "", s)[:NAME_MAX]
        if s:
            return s
    return "workspace"  # not reached


def check_name(name: str) -> Optional[str]:
    """Why ``name`` cannot be a built workspace's folder, or ``None`` when it can."""
    if name in RESERVED_NAMES:
        return (f'the name "{name}" is reserved ({", ".join(RESERVED_NAMES)}); '
                "give the Workspace another name")
    return None


def fingerprint(source: str, helpers: Iterable[str], root: str, k: int, text_color: str, viewer: bool) -> str:
    """What decides whether a built workspace is stale: a sha256 of the source file, every ``_*.py`` helper of the
    workspaces folder (path and content), the buildzr version and the options that change the output.

    Code imported from outside the workspaces folder is not part of it.
    """
    h = hashlib.sha256()

    def part(label: str, data: bytes) -> None:
        h.update(f"{label}\0{len(data)}\0".encode())
        h.update(data)

    part("format", FINGERPRINT_VERSION.encode())
    part("buildzr", _version().encode())
    part("options", json.dumps({"k": k, "textColor": text_color, "viewer": viewer}, sort_keys=True).encode())
    with open(source, "rb") as f:
        part("source", f.read())
    for helper in sorted(helpers, key=lambda p: relative_source(p, root)):
        with open(helper, "rb") as f:
            part("helper " + relative_source(helper, root), f.read())
    return "sha256:" + h.hexdigest()


def read_build_json(folder: str) -> Optional[dict[str, Any]]:
    """The ``build.json`` of a built workspace, or ``None`` when it is missing or unreadable."""
    try:
        with open(os.path.join(folder, "build.json"), encoding="utf-8") as f:
            info = json.load(f)
        return info if isinstance(info, dict) else None
    except (OSError, ValueError):
        return None


# --- one workspace ------------------------------------------------------------------------------


def _check_options(k: Optional[int], text_color: Optional[str], viewer: bool, static_dir: str) -> tuple[int, str]:
    k = 4 if k is None else k
    text_color = "wcag" if text_color is None else text_color
    if text_color not in ("wcag", "c4"):
        raise BuildError(f"text_color must be 'wcag' or 'c4', not {text_color!r}")
    if viewer and not os.path.isfile(os.path.join(static_dir, "index.html")):
        raise BuildError(f"the viewer bundle is missing ({static_dir}/index.html); build the viewer "
                         "or pass --no-viewer for data only")
    return k, text_color


def _guard_replace(dest: str) -> None:
    """Refuse to replace a folder that is not a built workspace (it has no ``build.json``)."""
    if os.path.exists(dest) and not os.path.isfile(os.path.join(dest, "build.json")):
        if not os.path.isdir(dest) or os.listdir(dest):
            raise BuildError(f"{dest} exists and is not a built workspace (no build.json); "
                             "refusing to replace it. Empty it or pick another output folder")


def _write_workspace(stage: str, out: str, k: int, viewer: bool, layout: LayoutFn, static_dir: str,
                     info: dict[str, Any]) -> dict[str, Any]:
    """Lay out the export in ``stage`` and put the built workspace at ``out`` (replaced as a whole)."""
    with open(os.path.join(stage, "model.json"), encoding="utf-8") as f:  # staging name, not the output's
        model = json.load(f)
    with open(os.path.join(stage, "levels.json"), encoding="utf-8") as f:
        levels = json.load(f)
    _guard_replace(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".build-", dir=os.path.dirname(out))
    try:
        built = os.path.join(tmp, "workspace")
        data = os.path.join(built, "data")
        os.makedirs(data)
        layout(levels, model, data, k=k)  # writes data/model.<h8>.json, index.json and the scenes
        if viewer:
            for name in sorted(os.listdir(static_dir)):
                src = os.path.join(static_dir, name)
                dst = os.path.join(built, name)
                if os.path.isdir(src):
                    shutil.copytree(src, dst)
                else:
                    shutil.copy2(src, dst)
        elk = None
        try:
            elk = getattr(importlib.import_module("buildzr.site.layout"), "ELK_VERSION", None)
        except ImportError:
            pass
        info = {"buildzr": _version(), "elkjs": elk, "k": k, "textColor": info.pop("textColor"),
                "modelHash": model["modelHash"], **info}
        canonical.write(os.path.join(built, "build.json"), info)
        swap_dir(built, out)
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def build_workspace(workspace: str, out: str = ".buildzr/build/workspace", k: Optional[int] = None,
                    text_color: Optional[str] = None, viewer: bool = True, layout_fn: Optional[LayoutFn] = None,
                    static_dir: str = STATIC_DIR, verbose: bool = False, index: int = -1) -> dict[str, Any]:
    """Build one workspace of the Python file ``workspace`` (the last one it creates, or ``index``) into ``out``.

    Returns the ``build.json`` object. ``k`` and ``text_color`` default to 4 and ``"wcag"``. ``out`` is replaced as a
    whole. With ``verbose`` the step that runs the file prints its summary line; errors are shown either way.
    :func:`build_all` is what ``buildzr build`` uses.
    """
    workspace = os.path.abspath(workspace)
    if not os.path.isfile(workspace):
        raise BuildError(f"workspace file not found: {workspace}")
    k, text_color = _check_options(k, text_color, viewer, static_dir)
    layout = layout_fn or _default_layout()
    out = os.path.abspath(out)
    root = os.path.dirname(workspace)
    with tempfile.TemporaryDirectory(prefix="buildzr-export-") as stage:
        if run_export(workspace, stage, index, text_color=text_color, quiet=not verbose) != 0:
            raise BuildError(f"executing {workspace} failed (see the error above)")
        info = {"textColor": text_color,
                "input": {"file": relative_source(workspace, root), "sha256": _sha256_file(workspace)},
                "fingerprint": fingerprint(workspace, find_helpers(root), root, k, text_color, viewer)}
        return _write_workspace(stage, out, k, viewer, layout, static_dir, info)


# --- every workspace of a folder ----------------------------------------------------------------


@dataclass
class Built:
    """A workspace written to the build output."""

    name: str
    folder: str
    source: str
    info: dict[str, Any]


@dataclass
class Failure:
    """A Python file, or one workspace of it, that could not be built. ``workspace`` is ``None`` for the whole file."""

    source: str
    workspace: Optional[str]
    message: str
    path: str = ""

    def where(self, shown: str) -> str:
        """``shown`` (the file as the caller shows it) and the workspace name, for a message."""
        return shown + (f' (workspace "{self.workspace}")' if self.workspace is not None else "")


@dataclass
class BuildResult:
    """What :func:`build_all` did. ``empty`` lists the files (absolute paths) that create no workspace."""

    built: list[Built] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    fresh: list[Built] = field(default_factory=list)


def _owned(out: str) -> dict[str, dict[str, Any]]:
    """The ``build.json`` of every built workspace in ``out``, by folder name."""
    found: dict[str, dict[str, Any]] = {}
    try:
        names = sorted(os.listdir(out))
    except OSError:
        return found
    for name in names:
        info = read_build_json(os.path.join(out, name))
        if info is not None and isinstance(info.get("input"), dict):
            found[name] = info
    return found


def is_fresh(source_rel: str, fp: str, owned: dict[str, dict[str, Any]]) -> bool:
    """Whether every workspace the file built last time is in the output with this fingerprint."""
    mine = {n: i for n, i in owned.items() if i["input"].get("file") == source_rel}
    if not mine:
        return False
    for info in mine.values():
        siblings = info.get("workspaces")
        if info.get("fingerprint") != fp or not isinstance(siblings, list):
            return False
        if any(s not in mine for s in siblings):
            return False
    return True


def build_all(path: str, out: str, k: Optional[int] = None, text_color: Optional[str] = None, viewer: bool = True,
              layout_fn: Optional[LayoutFn] = None, static_dir: str = STATIC_DIR, verbose: bool = False,
              only_stale: bool = False, root: Optional[str] = None) -> BuildResult:
    """Build every workspace of the Python file or workspaces folder ``path`` into ``out/<name>/``.

    Each file runs in a fresh subprocess. A file that fails, or one workspace of it, is recorded in
    :attr:`BuildResult.failed` and the others are still built; the previous output of a failed workspace is left as
    it was. Two workspaces with the same folder name stop the whole build before anything is written
    (:class:`BuildError`). With ``only_stale``, a file whose workspaces are all in ``out`` with the current
    fingerprint is not run (:attr:`BuildResult.fresh`). ``root`` is the workspaces folder the source paths in
    ``build.json`` are relative to (default: ``path`` or the folder holding it).
    """
    if not os.path.exists(path):
        raise BuildError(f"not found: {path}")
    k, text_color = _check_options(k, text_color, viewer, static_dir)
    out = os.path.abspath(out)
    root = os.path.abspath(root) if root is not None else source_root(path)
    sources = find_sources(path)
    helpers = find_helpers(root)
    owned = _owned(out)
    result = BuildResult()
    fps = {s: fingerprint(s, helpers, root, k, text_color, viewer) for s in sources}
    todo = []
    for s in sources:
        rel = relative_source(s, root)
        if only_stale and is_fresh(rel, fps[s], owned):
            result.fresh += [Built(n, os.path.join(out, n), rel, i) for n, i in sorted(owned.items())
                             if i["input"].get("file") == rel]
        else:
            todo.append(s)
    if not todo:
        return result
    layout = layout_fn or _default_layout()
    with tempfile.TemporaryDirectory(prefix="buildzr-export-") as stage:
        exported: list[tuple[str, str, list[dict[str, Any]]]] = []  # (source, stage folder, export list)
        for i, s in enumerate(todo):
            rel = relative_source(s, root)
            here = os.path.join(stage, str(i))
            if run_export_all(s, here, text_color=text_color, quiet=not verbose) != 0:
                result.failed.append(Failure(rel, None, "running it failed (see the error above)", s))
                continue
            listed = read_export_list(here)
            if not listed:
                result.empty.append(s)
                continue
            exported.append((s, here, listed))
        # Names: every workspace of this build, plus the fresh ones already in the output.
        taken: dict[str, tuple[str, str]] = {b.name: (b.source, str(b.info.get("workspace", b.name)))
                                             for b in result.fresh}
        plan: list[tuple[str, str, dict[str, Any], str, list[str]]] = []
        for s, here, listed in exported:
            rel = relative_source(s, root)
            stem = os.path.splitext(os.path.basename(s))[0]
            names = [safe_name(e["name"], stem) for e in listed]
            for e, name in zip(listed, names):
                if name in taken:
                    other_rel, other_ws = taken[name]
                    raise BuildError(f'two workspaces would both be built as "{name}": "{other_ws}" in {other_rel} '
                                     f'and "{e["name"]}" in {rel} (paths in {root}); rename one of them')
                taken[name] = (rel, e["name"])
            for e, name in zip(listed, names):
                plan.append((s, os.path.join(here, e["dir"]), e, name, names))
        for s, folder, e, name, names in plan:
            rel = relative_source(s, root)
            problem = e["error"] or check_name(name)
            if problem:
                result.failed.append(Failure(rel, e["name"], problem, s))
                continue
            info = {"textColor": text_color, "workspace": e["name"], "name": name, "workspaces": names,
                    "input": {"file": rel, "sha256": _sha256_file(s)}, "fingerprint": fps[s]}
            dest = os.path.join(out, name)
            try:
                written = _write_workspace(folder, dest, k, viewer, layout, static_dir, info)
            except BuildError as err:
                result.failed.append(Failure(rel, e["name"], str(err), s))
                continue
            except Exception as err:  # a layout failure of one workspace does not stop the others
                result.failed.append(Failure(rel, e["name"], f"{type(err).__name__}: {err}", s))
                continue
            result.built.append(Built(name, dest, rel, written))
    _prune(out, result)
    return result


def _prune(out: str, result: BuildResult) -> None:
    """Remove the built workspaces a file no longer creates (renamed in it), for the files built without failure."""
    failed = {f.source for f in result.failed}
    done: dict[str, set[str]] = {}
    for b in result.built:
        done.setdefault(b.source, set()).update(b.info.get("workspaces") or [b.name])
    for name, info in _owned(out).items():
        src = info["input"].get("file")
        if src in done and src not in failed and name not in done[src]:
            shutil.rmtree(os.path.join(out, name), ignore_errors=True)


def warn(msg: str) -> None:
    print(f"buildzr: {msg}", file=sys.stderr)
