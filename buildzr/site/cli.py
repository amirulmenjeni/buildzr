"""The ``buildzr`` command: ``build`` and ``serve``.

Every setting comes from a flag, then from ``buildzr.yaml`` (see :mod:`buildzr.site.config`), then from the
built-in default. Exit codes: 0 ok, 1 build, check or runtime failure, 2 usage or config error.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Iterable, NoReturn, Optional

from buildzr.site import config as cfgmod
from buildzr.site.api import normalise_origin, normalise_public_url
from buildzr.site.build import BuildError, BuildResult, build_all, plan, source_root
from buildzr.site.config import DEFAULT_OUT, DEFAULT_WORKSPACES, BuildSettings, Config, ConfigError
from buildzr.site.serve import Catalog, holds_built_workspaces, serve


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise _Usage(message)


class _Usage(Exception):
    """A usage or configuration problem: printed as ``buildzr: error: ...``, exit 2."""


def _add_build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-w", "--workspaces", dest="workspace", metavar="PATH", default=None,
                   help="the Python file or folder that creates workspaces "
                        f"(default: workspaces: in buildzr.yaml, else {DEFAULT_WORKSPACES}/)")
    p.add_argument("--k", type=int, default=None, metavar="N",
                   help="room for a box that contains other boxes, in areas of an empty box; raise it if their insides "
                        "are too small to read, lower it for compact diagrams (default: build.k in buildzr.yaml, else 4)")
    p.add_argument("--text-color", choices=["wcag", "c4"], default=None,
                   help="text colour on boxes, wcag or c4 (default: build.text_color in buildzr.yaml, else wcag)")
    p.add_argument("--no-viewer", action="store_true", help="write data only, without the viewer bundle")
    p.add_argument("-c", "--config", metavar="FILE", default=None,
                   help="config file (default: buildzr.yaml, searched from the current folder upward)")
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also show the summary line of the step that runs each Python file")


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="buildzr", description="Build and serve buildzr workspaces.")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    b = sub.add_parser("build", help="build every workspace of the workspaces folder")
    _add_build_args(b)
    b.add_argument("-o", "--out", metavar="DIR", default=None,
                   help=f"build output: one folder per workspace (default: build.out in buildzr.yaml, else {DEFAULT_OUT})")
    s = sub.add_parser("serve", help="build what is stale, then serve every workspace (read-only)")
    s.add_argument("path", nargs="?", default=None, metavar="PATH",
                   help="a workspaces folder or a .py file (built if stale, then the build output is served), or a "
                        "folder of built workspaces (served as it is) (default: the project's workspaces folder)")
    s.add_argument("--no-build", action="store_true", help="serve the build output as it is, without building")
    s.add_argument("--rebuild", action="store_true", help="build every workspace again, even the up-to-date ones")
    s.add_argument("-c", "--config", metavar="FILE", default=None,
                   help="config file (default: buildzr.yaml, searched from the current folder upward)")
    s.add_argument("-v", "--verbose", action="store_true",
                   help="also show the summary line of the step that runs each Python file")
    s.add_argument("-p", "--port", type=int, default=8000, help="port (default 8000)")
    s.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1; use 0.0.0.0 explicitly to share")
    s.add_argument("--public-url", metavar="URL", default=None,
                   help="address of the server as readers see it (http:// or https://); the base of the "
                        "API's viewerUrl links")
    s.add_argument("--cors-origin", metavar="ORIGIN", action="append", default=[],
                   help="let this web origin read the API from a browser (repeatable; there is no wildcard)")
    s.set_defaults(workspace=None, k=None, text_color=None, no_viewer=False, out=None)
    return ap


# --- helpers ------------------------------------------------------------------------------------


def _fail(msg: str, code: int = 1) -> int:
    print(f"buildzr: error: {msg}", file=sys.stderr)
    return code


def _show(path: Path) -> str:
    """``path`` relative to the current folder when it is below it, else absolute."""
    try:
        return os.path.relpath(path) if Path(os.getcwd()) in path.parents else str(path)
    except ValueError:
        return str(path)


def _load_config(explicit: Optional[str]) -> Optional[Config]:
    """The config named by ``-c``, or the nearest ``buildzr.yaml``; ``None`` when there is none."""
    if explicit is not None:
        if not os.path.isfile(explicit):
            raise _Usage(f"config file not found: {explicit}")
        return cfgmod.load_config(explicit)
    found = cfgmod.find_config(os.getcwd())
    if found is None:
        return None
    return cfgmod.load_config(found)


def _counts(folder: str) -> str:
    """``13 elements, 6 relationships, 1 view`` of a built workspace, or ``""`` if it cannot be read."""
    try:
        with open(os.path.join(folder, "data", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        with open(os.path.join(folder, "data", index["model"]["file"]), encoding="utf-8") as f:
            model = json.load(f)
        parts = [(len(model["elements"]), "element"), (len(model["relationships"]), "relationship"),
                 (len(model["views"]), "view")]
        return ", ".join(f"{n} {w}{'' if n == 1 else 's'}" for n, w in parts)
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def _short_hash(h: str) -> str:
    return h[:19] + "…"


def _summary(folder: str, info: dict[str, Any]) -> str:
    counts = _counts(folder)
    return (counts + "; " if counts else "") + "modelHash " + _short_hash(info["modelHash"])


class _BuildArgs:
    """Build settings after flag, file and default are merged."""

    def __init__(self, args: argparse.Namespace, cfg: Optional[Config]) -> None:
        env = os.environ
        base = cfg.build if cfg is not None else BuildSettings()
        if args.k is not None and args.k < 1:
            raise _Usage("--k: expected a whole number of at least 1")
        self.k: int = args.k if args.k is not None else base.k
        self.text_color: str = args.text_color if args.text_color is not None else base.text_color
        self.viewer: bool = base.viewer and not args.no_viewer
        here = cfg.root if cfg is not None else Path(os.getcwd())
        configured = cfgmod.resolve_workspaces(cfg, env) if cfg is not None else None
        #: The workspaces folder of the project: what ``build.json`` records source paths against.
        self.folder: Path = configured if configured is not None else here / DEFAULT_WORKSPACES
        self.path: Path = Path(os.path.abspath(args.workspace)) if args.workspace is not None else self.folder
        if getattr(args, "out", None) is not None:
            self.out = Path(os.path.abspath(args.out))
        elif cfg is not None:
            self.out = cfgmod.resolve_build(cfg, env).out
        else:
            self.out = Path(os.path.abspath(DEFAULT_OUT))

    @property
    def root(self) -> str:
        """The folder source paths are relative to: the project's workspaces folder when PATH is in it."""
        folder = self.folder if self.folder.is_dir() else self.folder.parent
        if self.path == folder or folder in self.path.parents:
            return str(folder)
        return source_root(str(self.path))

    def need_path(self) -> str:
        if not self.path.exists():
            raise _Usage(f"{_show(self.path)} not found; create the workspaces folder, pass -w PATH "
                         "or set workspaces: in buildzr.yaml")
        return str(self.path)


# --- commands -----------------------------------------------------------------------------------


def _report(result: BuildResult) -> None:
    """One line per skipped file and built workspace on stdout, one per failure on stderr."""
    for e in result.empty:
        print(f"skipped {_show(Path(e))}: it creates no workspace")
    for b in result.built:
        print(f"built {_show(Path(b.folder))} ({_summary(b.folder, b.info)})")
    for f in result.failed:
        print(f"buildzr: error: {f.where(_show(Path(f.path)))}: {f.message}", file=sys.stderr)


def _cmd_build(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    b = _BuildArgs(args, cfg)
    path = b.need_path()
    result = build_all(path, str(b.out), b.k, b.text_color, viewer=b.viewer, verbose=args.verbose, root=b.root)
    _report(result)
    if result.failed:
        return 1
    if not result.built:
        return _fail(f"no workspace found in {_show(b.path)}: no .py file there creates a Workspace")
    return 0


def _node_problem() -> Optional[str]:
    """Why the layout cannot run here (no Node), or ``None``."""
    try:
        from buildzr.site.layout.elk import find_node
        find_node()
    except Exception:
        return ("building needs Node.js 18 or newer, which was not found; install it (or set BUILDZR_NODE), "
                "or serve what is already built with --no-build")
    return None


def _build_stale(args: argparse.Namespace, b: _BuildArgs) -> None:
    """``serve``: build the workspaces that are missing or stale (all with ``--rebuild``); print what happened."""
    path = b.need_path()
    todo = plan(path, str(b.out), b.k, b.text_color, b.viewer, b.root, only_stale=not args.rebuild)
    fresh = sorted(w.name for w in todo.fresh)
    if fresh:
        print("up to date: " + ", ".join(fresh))
    if not todo.todo:
        return
    problem = _node_problem()
    if problem:
        print(f"buildzr: error: {problem}", file=sys.stderr)
        return
    try:
        result = build_all(path, str(b.out), b.k, b.text_color, viewer=b.viewer, verbose=args.verbose,
                           only_stale=not args.rebuild, root=b.root)
    except BuildError as e:
        print(f"buildzr: error: {e}", file=sys.stderr)
        return
    _report(result)


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        public_url = normalise_public_url(args.public_url) if args.public_url is not None else None
    except ValueError as e:
        raise _Usage(f"--public-url: {e}") from None
    try:
        origins = list(dict.fromkeys(normalise_origin(o) for o in args.cors_origin))
    except ValueError as e:
        raise _Usage(f"--cors-origin: {e}") from None
    if args.no_build and args.rebuild:
        raise _Usage("--no-build and --rebuild cannot be used together")
    if args.path is not None and not os.path.exists(args.path):
        raise _Usage(f"{args.path} not found")
    if args.path is not None and os.path.isdir(args.path) and holds_built_workspaces(args.path):
        if args.rebuild:
            raise _Usage(f"{args.path} holds built workspaces, which are served as they are; --rebuild needs "
                         "the workspaces folder or a .py file")
        directory = args.path
    else:
        args.workspace = args.path
        b = _BuildArgs(args, _load_config(args.config))
        directory = str(b.out)
        if not args.no_build:
            if not b.path.exists():
                raise _Usage(f"{_show(b.path)} not found; create the workspaces folder, pass PATH, set workspaces: "
                             f"in buildzr.yaml, or serve {_show(b.out)} as it is with --no-build")
            _build_stale(args, b)
    if not Catalog(directory).entries():
        return _fail(f"nothing to serve: {_show(Path(os.path.abspath(directory)))} holds no built workspace")
    try:
        serve(directory, args.host, args.port, public_url, origins, shown=_show(Path(os.path.abspath(directory))))
    except OSError as e:
        return _fail(f"cannot serve on {args.host}:{args.port}: {e.strerror or e}")
    return 0


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = _parser()
    try:
        try:
            args = ap.parse_args(list(argv) if argv is not None else None)
        except SystemExit as e:  # --help (0)
            return int(e.code or 0)
        if args.cmd == "build":
            return _cmd_build(args)
        return _cmd_serve(args)
    except _Usage as e:
        return _fail(str(e), 2)
    except ConfigError as e:
        print(str(e), file=sys.stderr)  # the loader already formatted every line
        return 2
    except BuildError as e:
        return _fail(str(e), 1)


if __name__ == "__main__":
    sys.exit(main())
