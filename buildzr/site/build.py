"""``buildzr build``: the Python files of a workspaces folder -> one built workspace per ``Workspace``.

The build output holds one folder per workspace, named after it (see :func:`safe_name`)::

    OUT/<name>/index.html, OUT/<name>/assets/...   the viewer bundle (``buildzr/site/static/``)
    OUT/<name>/data/model.<h8>.json, index.json, scene/...
    OUT/<name>/build.json                          versions, k, modelHash, source file, fingerprint, status;
                                                   no timestamps (schema/build.schema.json)

Relative URLs only, so a built workspace works at any path. Each Python file runs in a fresh subprocess; a built
workspace is checked (:mod:`buildzr.site.check`), written to a temporary folder and then renamed into place, so a
reader never sees half of one. When the workspace is at fault (its model file raises, its layout fails, its data
fails the check), a BROKEN built workspace replaces the old one; when the machine is at fault, nothing is written.
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
from typing import Any, Callable, Iterable, Optional, Sequence, Union

from buildzr.site import canonical
from buildzr.site.export import read_export_result, run_export, run_export_all

STATIC_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "static")

#: ``layout_workspace(levels, model, data_dir, k=...)`` of ``buildzr.site.layout`` (W2).
LayoutFn = Callable[..., Any]

#: Names a built workspace cannot take: they would hide a file or an address of ``buildzr serve``.
RESERVED_NAMES = ("api", "assets", "data", "_buildzr", "index.html", "build.json", "llms.txt")
NAME_MAX = 64
FINGERPRINT_VERSION = "buildzr.fingerprint/1"
#: The steps at which a workspace can break: running the model file, the layout, the data checker.
STAGES = ("model", "layout", "check")
MAX_ERRORS = 50
MAX_ERROR_CHARS = 500


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


def _errors(lines: Iterable[str]) -> list[str]:
    """At most :data:`MAX_ERRORS` errors of at most :data:`MAX_ERROR_CHARS` characters each, for ``build.json``."""
    out = []
    for line in lines:
        text = str(line)
        out.append(text if len(text) <= MAX_ERROR_CHARS else text[:MAX_ERROR_CHARS - 1] + "…")
        if len(out) == MAX_ERRORS:
            break
    return out


def is_environment_problem(err: BaseException) -> bool:
    """Whether ``err`` comes from the machine (Node, the disk, permissions, memory), not from the workspace.

    Such a failure leaves the previous built workspace as it is; any other failure writes a broken one.
    """
    if isinstance(err, (OSError, MemoryError)):
        return True
    try:
        from buildzr.site.layout.elk import ElkEnvironmentError
    except ImportError:
        return False
    return isinstance(err, ElkEnvironmentError)


def _elk_version() -> Optional[str]:
    try:
        return getattr(importlib.import_module("buildzr.site.layout"), "ELK_VERSION", None)
    except ImportError:
        return None


def check_workspace(data_dir: str) -> list[str]:
    """The errors of :func:`buildzr.site.check.check_built` on a freshly laid-out ``data/`` folder (no time limit:
    the data is our own)."""
    from buildzr.site.check import check_built

    return check_built(data_dir, timeout=None).errors


def _publish(built: str, out: str, viewer: bool, static_dir: str, info: dict[str, Any]) -> None:
    """Add the viewer bundle and ``build.json`` to the folder ``built`` and put it at ``out`` in one rename."""
    if viewer:
        for name in sorted(os.listdir(static_dir)):
            src = os.path.join(static_dir, name)
            dst = os.path.join(built, name)
            if os.path.isdir(src):
                shutil.copytree(src, dst)
            else:
                shutil.copy2(src, dst)
    canonical.write(os.path.join(built, "build.json"), info)
    swap_dir(built, out)


def _write_workspace(stage: str, out: str, k: int, viewer: bool, layout: LayoutFn, static_dir: str,
                     info: dict[str, Any]) -> dict[str, Any]:
    """Lay out the export in ``stage``, check it and put the built workspace at ``out`` (replaced as a whole).

    A layout that fails because of the model, or data that fails :func:`buildzr.site.check.check_built`, gives a
    broken built workspace (``status: broken``; with stage ``check`` the data is kept, with stage ``layout`` it is
    not). A failure of the machine (:func:`is_environment_problem`) is raised and ``out`` is left as it was.
    """
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
        status: dict[str, Any] = {"status": "ok"}
        try:
            layout(levels, model, data, k=k)  # writes data/model.<h8>.json, index.json and the scenes
        except Exception as err:
            if is_environment_problem(err):
                raise
            shutil.rmtree(data)
            status = {"status": "broken", "stage": "layout", "errors": _errors([f"{type(err).__name__}: {err}"])}
        else:
            problems = check_workspace(data)
            if problems:
                status = {"status": "broken", "stage": "check",
                          "errors": _errors(e.replace(data + os.sep, "data/") for e in problems)}
        info = {"buildzr": _version(), "elkjs": _elk_version(), "k": k, "textColor": info.pop("textColor"),
                **({"modelHash": model["modelHash"]} if os.path.isdir(data) else {}), **info, **status}
        _publish(built, out, viewer, static_dir, info)
        return info
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _write_broken(out: str, k: int, viewer: bool, static_dir: str, info: dict[str, Any], stage: str,
                  errors: Iterable[str]) -> dict[str, Any]:
    """Put a broken built workspace without data at ``out``: ``build.json`` and the viewer, which says it is broken."""
    _guard_replace(out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".build-", dir=os.path.dirname(out))
    try:
        built = os.path.join(tmp, "workspace")
        os.makedirs(built)
        info = {"buildzr": _version(), "elkjs": _elk_version(), "k": k, "textColor": info.pop("textColor"), **info,
                "status": "broken", "stage": stage, "errors": _errors(errors)}
        _publish(built, out, viewer, static_dir, info)
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
                "fingerprint": fingerprint(workspace, find_helpers(root), root, k, text_color, viewer),
                "workspacesFolder": folder_record(root, os.path.dirname(out))}
        return _write_workspace(stage, out, k, viewer, layout, static_dir, info)


# --- every workspace of a folder ----------------------------------------------------------------


@dataclass
class Built:
    """A workspace written to the build output, ok or broken (``info["status"]``)."""

    name: str
    folder: str
    source: str
    info: dict[str, Any]

    @property
    def broken(self) -> bool:
        return self.info.get("status") == "broken"


@dataclass
class Failure:
    """A Python file, or one workspace of it, that could not be built and has no built workspace for it.

    ``workspace`` is ``None`` for the whole file. ``environment`` is true when the machine is at fault (see
    :func:`is_environment_problem`); the previous built workspace is then kept as it was.
    """

    source: str
    workspace: Optional[str]
    message: str
    path: str = ""
    environment: bool = False

    def where(self, shown: str) -> str:
        """``shown`` (the file as the caller shows it) and the workspace name, for a message."""
        return shown + (f' (workspace "{self.workspace}")' if self.workspace is not None else "")


@dataclass
class Removed:
    """A built workspace that :func:`build_all` removed, and why (``"gone"``, ``"unlisted"`` or ``"dropped"``)."""

    name: str
    source: str
    reason: str


@dataclass
class BuildResult:
    """What :func:`build_all` did. ``empty`` lists the files (absolute paths) that create no workspace.

    ``built`` holds the ok workspaces written now, ``broken`` the broken ones, ``fresh`` those left as they were.
    """

    built: list[Built] = field(default_factory=list)
    failed: list[Failure] = field(default_factory=list)
    empty: list[str] = field(default_factory=list)
    fresh: list[Built] = field(default_factory=list)
    removed: list[Removed] = field(default_factory=list)
    broken: list[Built] = field(default_factory=list)


def folder_record(root: str, out: str) -> str:
    """How ``build.json`` records the workspaces folder ``root``: relative to the build output ``out``."""
    try:
        return os.path.relpath(root, out).replace(os.sep, "/")
    except ValueError:  # another drive on Windows
        return root


def _from_folder(info: dict[str, Any], root: str, out: str, listed: Optional[str] = None) -> bool:
    """Whether the built workspace of ``info`` was built from the workspaces folder ``root``, and from the
    ``workspaces:`` list of the config file ``listed`` (``None``: from a single path, not from a list)."""
    rec = info.get("workspacesFolder")
    if not (isinstance(rec, str) and os.path.normpath(os.path.join(out, rec)) == os.path.normpath(root)):
        return False
    lst = info.get("workspacesList")
    if listed is None or lst is None:
        return listed is None and lst is None
    return isinstance(lst, str) and os.path.normpath(os.path.join(out, lst)) == os.path.normpath(listed)


def _owned(out: str, root: Optional[str] = None, listed: Optional[str] = None) -> dict[str, dict[str, Any]]:
    """The ``build.json`` of every built workspace in ``out`` that records its source file, by folder name.

    With ``root``, only those built from that workspaces folder, and from the list of the config file ``listed``
    (or from no list when it is ``None``).
    """
    found: dict[str, dict[str, Any]] = {}
    try:
        names = sorted(os.listdir(out))
    except OSError:
        return found
    for name in names:
        info = read_build_json(os.path.join(out, name))
        if info is None or not isinstance(info.get("input"), dict):
            continue
        src = info["input"].get("file")
        if isinstance(src, str) and src and (root is None or _from_folder(info, root, out, listed)):
            found[name] = info
    return found


def is_fresh(source_rel: str, fp: str, owned: dict[str, dict[str, Any]]) -> bool:
    """Whether every workspace the file built last time is in the output with this fingerprint (ok or broken)."""
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


@dataclass(frozen=True)
class Entry:
    """A Python file or a folder of them, and the options of the workspaces built from it.

    One entry of a ``workspaces:`` list in ``buildzr.yaml``, or the single path of a build. ``helpers`` is the folder
    whose ``_*.py`` files count in the fingerprint (see :func:`find_helpers`); ``None`` means the build's ``root``.
    """

    path: str
    k: int = 4
    text_color: str = "wcag"
    viewer: bool = True
    helpers: Optional[str] = None


@dataclass
class Plan:
    """Which files of a build must run (``todo``) and which built workspaces are up to date (``fresh``).

    ``entries`` gives the entry of every file found, ``fingerprints`` its fingerprint.
    """

    todo: list[str]
    fresh: list[Built]
    fingerprints: dict[str, str]
    entries: dict[str, Entry] = field(default_factory=dict)


Paths = Union[str, Sequence[Entry]]


def _entries(path: Paths, k: Optional[int], text_color: Optional[str], viewer: bool) -> list[Entry]:
    if isinstance(path, str):
        return [Entry(path, 4 if k is None else k, "wcag" if text_color is None else text_color, viewer)]
    return list(path)


def plan(path: Paths, out: str, k: Optional[int] = None, text_color: Optional[str] = None, viewer: bool = True,
         root: Optional[str] = None, only_stale: bool = True, listed: Optional[str] = None) -> Plan:
    """Work out what :func:`build_all` would run: every file, or with ``only_stale`` the stale ones only.

    ``path`` is a file or folder built with ``k``, ``text_color`` and ``viewer``, or a list of :class:`Entry`, each
    with its own options. A file is stale when one of the workspaces it built last time is missing from ``out`` or
    was built with another fingerprint (see :func:`fingerprint`); a file never built is stale too. File dates are not
    used. A broken built workspace is up to date like an ok one, so the same broken input is not built again and
    again.
    """
    entries = _entries(path, k, text_color, viewer)
    for e in entries:
        if not os.path.exists(e.path):
            raise BuildError(f"not found: {e.path}")
    out = os.path.abspath(out)
    if root is None:
        if len(entries) != 1:
            raise BuildError("a build of several entries needs the folder its paths are relative to (root)")
        root = source_root(entries[0].path)
    root = os.path.abspath(root)
    owned = _owned(out, root, listed)
    result = Plan([], [], {})
    helpers: dict[str, list[str]] = {}
    for e in entries:
        folder = os.path.abspath(e.helpers) if e.helpers is not None else root
        if folder not in helpers:
            helpers[folder] = find_helpers(folder)
        for s in find_sources(e.path):
            if s in result.entries:
                raise BuildError(f"{relative_source(s, root)} is in two entries; list each file once")
            result.entries[s] = e
            result.fingerprints[s] = fingerprint(s, helpers[folder], root, e.k, e.text_color, e.viewer)
    for s, fp in result.fingerprints.items():
        rel = relative_source(s, root)
        if only_stale and is_fresh(rel, fp, owned):
            result.fresh += [Built(n, os.path.join(out, n), rel, i) for n, i in sorted(owned.items())
                             if i["input"].get("file") == rel]
        else:
            result.todo.append(s)
    return result


@dataclass
class _Job:
    """One workspace to write: from an export (``folder``), or broken at the model step (``errors``)."""

    source: str
    name: str
    workspace: str
    names: list[str]
    folder: Optional[str] = None
    errors: Optional[list[str]] = None
    fallback: bool = False  # named after the file: it failed before it created any workspace
    homeless: bool = False  # a fallback whose name another workspace has


def build_all(path: Paths, out: str, k: Optional[int] = None, text_color: Optional[str] = None, viewer: bool = True,
              layout_fn: Optional[LayoutFn] = None, static_dir: str = STATIC_DIR, verbose: bool = False,
              only_stale: bool = False, root: Optional[str] = None, prune: bool = False,
              listed: Optional[str] = None) -> BuildResult:
    """Build every workspace of the Python file or workspaces folder ``path`` into ``out/<name>/``.

    ``path`` may also be a list of :class:`Entry` (the ``workspaces:`` list of ``buildzr.yaml``): each file is then
    built with the options of its entry, and ``k``, ``text_color`` and ``viewer`` are not used. ``listed`` is the
    config file that holds that list; it is recorded in ``build.json`` (``workspacesList``) so that a build of
    another list, or of a single path, never removes these workspaces, and with ``prune`` a workspace whose file is
    no longer listed is removed.

    Each file runs in a fresh subprocess. Every built workspace is checked with
    :func:`buildzr.site.check.check_built` before it is put in place. A workspace whose model file raises, whose
    layout fails or whose data fails the check REPLACES its previous output as a broken built workspace
    (:attr:`BuildResult.broken`); the others are still built. A failure of the machine (Node, the disk, a killed
    process) writes nothing and keeps the previous output (:attr:`BuildResult.failed`, ``environment``). Two
    workspaces with the same folder name stop the whole build before anything is written (:class:`BuildError`).
    With ``only_stale``, a file whose workspaces are all in ``out`` with the current fingerprint is not run
    (:attr:`BuildResult.fresh`). ``root`` is the workspaces folder the source paths in ``build.json`` are relative
    to (default: ``path`` or the folder holding it). With ``prune``, built workspaces this build did not produce
    are removed as :func:`_prune` says (:attr:`BuildResult.removed`).
    """
    entries = _entries(path, k, text_color, viewer)
    for e in entries:
        _check_options(e.k, e.text_color, e.viewer, static_dir)
    out = os.path.abspath(out)
    if root is None and len(entries) == 1:
        root = source_root(entries[0].path)
    p = plan(entries, out, root=root, only_stale=only_stale, listed=listed)
    root = os.path.abspath(str(root))
    result = BuildResult(fresh=p.fresh)
    todo, fps = p.todo, p.fingerprints
    listed_rec = {"workspacesList": folder_record(listed, out)} if listed is not None else {}
    if not todo:
        if prune:
            _prune(out, root, result, listed, p)
        return result
    layout = layout_fn or _default_layout()
    owned = _owned(out, root, listed)
    with tempfile.TemporaryDirectory(prefix="buildzr-export-") as stage:
        jobs: list[_Job] = []
        for i, s in enumerate(todo):
            rel = relative_source(s, root)
            stem = os.path.splitext(os.path.basename(s))[0]
            here = os.path.join(stage, str(i))
            code = run_export_all(s, here, text_color=p.entries[s].text_color, quiet=not verbose)
            try:
                exported = read_export_result(here)
            except (OSError, ValueError, KeyError):
                exported = None
            if exported is not None and isinstance(exported.get("fileError"), list):
                # The model file raised: every workspace it made before, or built last time, becomes broken.
                names = list(dict.fromkeys(
                    [safe_name(n, stem) for n in exported.get("created") or []]
                    + [n for n, info in owned.items() if info["input"].get("file") == rel]))
                fallback = not names
                names = names or [safe_name("", stem)]
                for name in names:
                    jobs.append(_Job(s, name, str(owned.get(name, {}).get("workspace", name)), names,
                                     errors=[str(e) for e in exported["fileError"]], fallback=fallback))
                continue
            if code != 0 or exported is None:
                result.failed.append(Failure(rel, None, "running it failed (see the error above)", s, environment=True))
                continue
            made = exported["workspaces"]
            if not made:
                result.empty.append(s)
                continue
            names = [safe_name(w["name"], stem) for w in made]
            for w, name in zip(made, names):
                jobs.append(_Job(s, name, w["name"], names, folder=os.path.join(here, w["dir"]),
                                 errors=[w["error"]] if w["error"] else None))
        # Names: every workspace of this build, plus the fresh ones already in the output. A file that failed before
        # it created any workspace falls back to its file name, which gives way to a real workspace of that name.
        taken: dict[str, tuple[str, str]] = {b.name: (b.source, str(b.info.get("workspace", b.name)))
                                             for b in result.fresh}
        for job in sorted(jobs, key=lambda j: j.fallback):
            rel = relative_source(job.source, root)
            if job.name in taken:
                if job.fallback:
                    job.homeless = True
                    continue
                other_rel, other_ws = taken[job.name]
                raise BuildError(f'two workspaces would both be built as "{job.name}": "{other_ws}" in {other_rel} '
                                 f'and "{job.workspace}" in {rel} (paths in {root}); rename one of them')
            taken[job.name] = (rel, job.workspace)
        env_problem: Optional[str] = None
        for job in jobs:
            rel = relative_source(job.source, root)
            shown: Optional[str] = job.workspace
            if job.homeless:
                result.failed.append(Failure(rel, None, "running it failed (see the error above), and its broken "
                                             f'workspace cannot be written as "{job.name}", which another workspace '
                                             "has", job.source))
                continue
            problem = check_name(job.name)
            if problem:
                result.failed.append(Failure(rel, shown, problem, job.source))
                continue
            if env_problem is not None:
                result.failed.append(Failure(rel, shown, env_problem, job.source, environment=True))
                continue
            e = p.entries[job.source]
            info = {"textColor": e.text_color, "workspace": job.workspace, "name": job.name, "workspaces": job.names,
                    "input": {"file": rel, "sha256": _sha256_file(job.source)}, "fingerprint": fps[job.source],
                    "workspacesFolder": folder_record(root, out), **listed_rec}
            dest = os.path.join(out, job.name)
            try:
                if job.errors is not None:
                    written = _write_broken(dest, e.k, e.viewer, static_dir, info, "model", job.errors)
                else:
                    assert job.folder is not None
                    written = _write_workspace(job.folder, dest, e.k, e.viewer, layout, static_dir, info)
            except Exception as err:  # not the workspace's fault (see _write_workspace): the old output stays
                msg = str(err) if isinstance(err, BuildError) else f"{type(err).__name__}: {err}"
                if is_environment_problem(err) and not isinstance(err, OSError):
                    env_problem = msg  # Node or ELK cannot be used: the next workspaces would fail the same way
                result.failed.append(Failure(rel, shown, msg, job.source, environment=True))
                continue
            done = Built(job.name, dest, rel, written)
            (result.broken if done.broken else result.built).append(done)
    if prune:
        _prune(out, root, result, listed, p)
    return result


def _prune(out: str, root: str, result: BuildResult, listed: Optional[str] = None, p: Optional[Plan] = None) -> None:
    """Remove the built workspaces of ``out`` that this build did not produce and whose model file is gone, no
    longer listed, or no longer creates them.

    Only folders whose ``build.json`` records a source file, the workspaces folder ``root`` and the same list
    (``listed``, see :func:`_from_folder`) are considered. A folder is removed when that file no longer exists in
    ``root`` (``"gone"``), when this build comes from the list ``listed`` and its file is not in it any more
    (``"unlisted"``), or when the file ran in this build and did not create the workspace (``"dropped"``). A file
    that failed because of the machine keeps all its previous output.
    """
    current = {relative_source(s, root) for s in p.entries} if p is not None else set()
    kept = {f.source for f in result.failed if f.environment}
    done: dict[str, set[str]] = {relative_source(e, root): set() for e in result.empty}
    for b in result.built + result.broken:
        done.setdefault(b.source, set()).update(b.info.get("workspaces") or [b.name])
    for f in result.failed:
        done.setdefault(f.source, set())
    produced = {b.name for b in result.built + result.broken + result.fresh}
    for name, info in _owned(out, root, listed).items():
        src = info["input"]["file"]
        if name in produced or src in kept:
            continue
        if not os.path.exists(os.path.join(root, src)):
            reason = "gone"
        elif listed is not None and src not in current:
            reason = "unlisted"
        elif src in done and name not in done[src]:
            reason = "dropped"
        else:
            continue
        shutil.rmtree(os.path.join(out, name))
        result.removed.append(Removed(name, src, reason))


def warn(msg: str) -> None:
    print(f"buildzr: {msg}", file=sys.stderr)
