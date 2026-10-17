"""The ``buildzr`` command: ``build``, ``serve`` and ``deploy``.

Every setting comes from a flag, then from ``buildzr.yaml`` (see :mod:`buildzr.site.config`), then from the
built-in default. Exit codes: 0 ok, 1 build, check or runtime failure, 2 usage or config error.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any, Iterable, NoReturn, Optional

from buildzr.site import config as cfgmod
from buildzr.site.build import BuildError, build_site, swap_dir
from buildzr.site.check import check_site
from buildzr.site.config import DEFAULT_OUT, BuildSettings, Config, ConfigError
from buildzr.site.serve import serve

MAX_ERRORS_SHOWN = 20
NOT_YET_URL = "deploying to a running instance is not available in this version; use a dir target or build"


class _Parser(argparse.ArgumentParser):
    def error(self, message: str) -> NoReturn:
        self.print_usage(sys.stderr)
        raise _Usage(message)


class _Usage(Exception):
    """A usage or configuration problem: printed as ``buildzr: error: ...``, exit 2."""


def _add_build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("-w", "--workspace", metavar="FILE", default=None,
                   help="DSL .py file that creates a Workspace (default: workspace: in buildzr.yaml)")
    p.add_argument("--k", type=int, default=None, metavar="N",
                   help="layout parameter (default: build.k in buildzr.yaml, else 4)")
    p.add_argument("--text-color", choices=["wcag", "c4"], default=None,
                   help="node text colour rule (default: build.text_color in buildzr.yaml, else wcag)")
    p.add_argument("--no-viewer", action="store_true", help="write data only, without the viewer bundle")
    p.add_argument("-c", "--config", metavar="FILE", default=None,
                   help="config file (default: buildzr.yaml, searched from the current folder upward)")


def _parser() -> argparse.ArgumentParser:
    ap = _Parser(prog="buildzr", description="Build, serve and deploy a buildzr model site.")
    sub = ap.add_subparsers(dest="cmd", required=True, parser_class=_Parser)
    b = sub.add_parser("build", help="build the site directory from a workspace file")
    _add_build_args(b)
    b.add_argument("-o", "--out", metavar="DIR", default=None,
                   help=f"output directory (default: build.out in buildzr.yaml, else {DEFAULT_OUT})")
    s = sub.add_parser("serve", help="serve a built site directory (read-only)")
    s.add_argument("dir", nargs="?", default=None, metavar="DIR",
                   help=f"built site (default: build.out of the nearest buildzr.yaml, else {DEFAULT_OUT})")
    s.add_argument("-p", "--port", type=int, default=8000, help="port (default 8000)")
    s.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1; use 0.0.0.0 explicitly to share")
    d = sub.add_parser("deploy", help="build the site and put it on a target from buildzr.yaml")
    _add_build_args(d)
    d.add_argument("-t", "--target", metavar="NAME", default=None,
                   help="target name in buildzr.yaml (default: default_target)")
    d.add_argument("--path", metavar="P", default=None, help="site path below the target; overrides the target's path")
    d.add_argument("--from", dest="from_dir", metavar="DIR", default=None,
                   help="deploy an already built site instead of building (the build flags are then refused)")
    d.add_argument("--dry-run", action="store_true",
                   help="load the config, build and check, print the resolved target; write nothing to it")
    d.add_argument("--rollback", action="store_true", help="not available in this version")
    d.add_argument("--base-path", default=None, help=argparse.SUPPRESS)  # removed; kept to explain itself
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


def _load_config(explicit: Optional[str], required: bool = False) -> Optional[Config]:
    """The config named by ``-c``, or the nearest ``buildzr.yaml``; ``None`` when there is none."""
    if explicit is not None:
        if not os.path.isfile(explicit):
            raise _Usage(f"config file not found: {explicit}")
        return cfgmod.load_config(explicit)
    found = cfgmod.find_config(os.getcwd())
    if found is None:
        if required:
            raise _Usage("no buildzr.yaml found; deploy needs a target")
        return None
    return cfgmod.load_config(found)


def _counts(site: str) -> str:
    """``13 elements, 6 relationships, 1 view`` of a built site, or ``""`` if it cannot be read."""
    try:
        with open(os.path.join(site, "data", "index.json"), encoding="utf-8") as f:
            index = json.load(f)
        with open(os.path.join(site, "data", index["model"]["file"]), encoding="utf-8") as f:
            model = json.load(f)
        parts = [(len(model["elements"]), "element"), (len(model["relationships"]), "relationship"),
                 (len(model["views"]), "view")]
        return ", ".join(f"{n} {w}{'' if n == 1 else 's'}" for n, w in parts)
    except (OSError, ValueError, KeyError, TypeError):
        return ""


def _short_hash(h: str) -> str:
    return h[:19] + "…"


def _summary(site: str, info: dict[str, Any]) -> str:
    counts = _counts(site)
    return (counts + "; " if counts else "") + "modelHash " + _short_hash(info["modelHash"])


def _tree_size(site: str) -> tuple[int, int]:
    n = size = 0
    for root, _dirs, files in os.walk(site):
        for f in files:
            n += 1
            size += os.path.getsize(os.path.join(root, f))
    return n, size


def _human(size: int) -> str:
    return f"{size} B" if size < 1024 else f"{size / 1024:.0f} KB"


def _check(site: str) -> Optional[int]:
    """Run the checker on ``site``; print the problems and return 1 when there are any."""
    try:
        import jsonschema  # type: ignore[import-untyped]  # noqa: F401
    except ImportError:
        print("buildzr: warning: jsonschema is not installed; the site check skips the schema step", file=sys.stderr)
    rep = check_site(os.path.join(site, "data"), require_build_json=True)
    if rep.ok:
        return None
    print(f"buildzr: error: the checker found {len(rep.errors)} problem(s) in the built site:", file=sys.stderr)
    for e in rep.errors[:MAX_ERRORS_SHOWN]:
        print(f"  {e}", file=sys.stderr)
    if len(rep.errors) > MAX_ERRORS_SHOWN:
        print(f"  ... and {len(rep.errors) - MAX_ERRORS_SHOWN} more", file=sys.stderr)
    return 1


class _BuildArgs:
    """Build settings after flag, file and default are merged."""

    def __init__(self, args: argparse.Namespace, cfg: Optional[Config], need_out: bool) -> None:
        env = os.environ
        base = cfg.build if cfg is not None else BuildSettings()
        if args.k is not None and args.k < 1:
            raise _Usage("--k: expected a whole number of at least 1")
        self.k: int = args.k if args.k is not None else base.k
        self.text_color: str = args.text_color if args.text_color is not None else base.text_color
        self.viewer: bool = base.viewer and not args.no_viewer
        if args.workspace is not None:
            self.workspace: Optional[str] = args.workspace
        else:
            ws = cfgmod.resolve_workspace(cfg, env) if cfg is not None else None
            self.workspace = str(ws) if ws is not None else None
        self.out: Optional[str] = None
        if need_out:
            if getattr(args, "out", None) is not None:
                self.out = args.out
            elif cfg is not None:
                self.out = str(cfgmod.resolve_build(cfg, env).out)
            else:
                self.out = DEFAULT_OUT

    def need_workspace(self) -> str:
        if self.workspace is None:
            raise _Usage("no workspace given; pass --workspace FILE or set workspace: in buildzr.yaml")
        return self.workspace


# --- commands -----------------------------------------------------------------------------------


def _cmd_build(args: argparse.Namespace) -> int:
    cfg = _load_config(args.config)
    b = _BuildArgs(args, cfg, need_out=True)
    ws = b.need_workspace()
    assert b.out is not None
    info = build_site(ws, b.out, b.k, b.text_color, viewer=b.viewer)
    print(f"built {_show(Path(os.path.abspath(b.out)))} ({_summary(b.out, info)})")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    directory = args.dir
    if directory is None:
        cfg = _load_config(None)
        directory = str(cfgmod.resolve_build(cfg, os.environ).out) if cfg is not None else DEFAULT_OUT
    if not os.path.isfile(os.path.join(directory, "data", "index.json")) and \
            not os.path.isfile(os.path.join(directory, "index.html")):
        return _fail(f"{directory} does not look like a built site (run `buildzr build` first)")
    try:
        serve(directory, args.host, args.port)
    except OSError as e:
        return _fail(f"cannot serve on {args.host}:{args.port}: {e.strerror or e}")
    return 0


def _guard_replace(dest: Path) -> None:
    """Refuse to replace a folder that is not a buildzr site (``deploy`` swaps ``dest`` as a whole)."""
    if dest.exists() and not (dest / "build.json").is_file():
        if not dest.is_dir() or any(dest.iterdir()):
            raise BuildError(f"{dest} exists and is not a buildzr site (no build.json); "
                             "refusing to replace it. Empty it or pick another dir/path")


def _previous_hash(dest: Path) -> Optional[str]:
    try:
        with open(dest / "build.json", encoding="utf-8") as f:
            h = json.load(f)["modelHash"]
        return h if isinstance(h, str) else None
    except (OSError, ValueError, KeyError, TypeError):
        return None


def _cmd_deploy(args: argparse.Namespace) -> int:
    if args.base_path is not None:
        raise _Usage("--base-path was removed; use --path P (or the target's path: in buildzr.yaml)")
    if args.rollback:
        raise _Usage("--rollback is not available in this version")
    path_override: Optional[str] = None
    if args.path is not None:
        path_override, perr = cfgmod._check_path(args.path)
        if perr:
            raise _Usage(f"--path: {perr}")
    if args.from_dir is not None:
        clash = [f for f, v in (("--workspace", args.workspace), ("--k", args.k), ("--text-color", args.text_color),
                                ("--no-viewer", args.no_viewer or None)) if v is not None]
        if clash:
            raise _Usage(f"{', '.join(clash)} cannot be used with --from (the site is deployed as built)")
    cfg = _load_config(args.config, required=True)
    assert cfg is not None
    target = cfgmod.resolve_target(cfg, args.target, os.environ)
    if target.url is not None:
        return _fail(NOT_YET_URL)
    assert target.dir is not None
    path = target.path if path_override is None else path_override
    dest = target.dir / path if path else target.dir
    viewer = target.viewer and not args.no_viewer

    b: Optional[_BuildArgs] = None
    if args.from_dir is not None:
        if not os.path.isfile(os.path.join(args.from_dir, "data", "index.json")):
            return _fail(f"{args.from_dir} does not look like a built site (no data/index.json)")
    else:
        b = _BuildArgs(args, cfg, need_out=False)
        b.need_workspace()

    _guard_replace(dest)
    try:
        stage_parent = tempfile.mkdtemp() if args.dry_run else None
        if stage_parent is None:
            os.makedirs(dest.parent, exist_ok=True)
            stage_parent = tempfile.mkdtemp(prefix=".buildzr-deploy-", dir=dest.parent)
    except OSError as e:
        return _fail(f"cannot write to {dest}: {e.strerror or e}")
    try:
        site = os.path.join(stage_parent, "site")
        if b is None:
            shutil.copytree(args.from_dir, site)
            failed = _check(site)
            if failed:
                return failed
            with open(os.path.join(site, "build.json"), encoding="utf-8") as f:
                info = json.load(f)
            print(f"using {_show(Path(os.path.abspath(args.from_dir)))} ({_summary(site, info)})")
        else:
            info = build_site(b.need_workspace(), site, b.k, b.text_color, viewer=viewer)
            print(f"built ({_summary(site, info)})")
            failed = _check(site)
            if failed:
                return failed
        n, size = _tree_size(site)
        where = f"{dest} (target {target.name}" + (f", path {path}" if path else "") + ")"
        if args.dry_run:
            print(f"checked {n} files, {_human(size)}: no problems")
            print(f"dry run: would write {n} files, {_human(size)} to {where}; nothing was written")
            return 0
        prev = _previous_hash(dest)
        print(f"writing {n} files, {_human(size)} to {where}")
        try:
            swap_dir(site, str(dest))
        except OSError as e:
            return _fail(f"cannot write to {dest}: {e.strerror or e}")
        print(f"deployed {path or target.name}: modelHash {_short_hash(info['modelHash'])}"
              + (f" (previous {_short_hash(prev)})" if prev else ""))
        return 0
    finally:
        shutil.rmtree(stage_parent, ignore_errors=True)


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = _parser()
    try:
        try:
            args = ap.parse_args(list(argv) if argv is not None else None)
        except SystemExit as e:  # --help (0)
            return int(e.code or 0)
        if args.cmd == "build":
            return _cmd_build(args)
        if args.cmd == "serve":
            return _cmd_serve(args)
        return _cmd_deploy(args)
    except _Usage as e:
        return _fail(str(e), 2)
    except ConfigError as e:
        print(str(e), file=sys.stderr)  # the loader already formatted every line
        return 2
    except BuildError as e:
        return _fail(str(e), 1)


if __name__ == "__main__":
    sys.exit(main())
