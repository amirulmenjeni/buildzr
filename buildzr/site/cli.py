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
from buildzr.site.api import normalise_origin, normalise_public_url
from buildzr.site.build import BuildError, build_site, swap_dir
from buildzr.site.check import check_site
from buildzr.site.config import DEFAULT_OUT, BuildSettings, Config, ConfigError
from buildzr.site.serve import serve, serve_store
from buildzr.site import deploy_client as dc
from buildzr.site.deploy import DEFAULT_DEPLOY_PORT, DEFAULT_MAX_UPLOAD_MB, run_instance
from buildzr.site.store import DEPLOY_GRACE_SECONDS, SitePathError, Store, StoreError, normalise_site_path

MAX_ERRORS_SHOWN = 20


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
    p.add_argument("-v", "--verbose", action="store_true",
                   help="also show the summary line of the step that runs the model file")


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
    s.add_argument("--store", metavar="DIR", default=None,
                   help="serve every site of the store folder DIR, read only (instead of one site DIR)")
    s.add_argument("-p", "--port", type=int, default=8000, help="port (default 8000)")
    s.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1; use 0.0.0.0 explicitly to share")
    s.add_argument("--public-url", metavar="URL", default=None,
                   help="address of the site as readers see it (http:// or https://); the base of the API's viewerUrl links")
    s.add_argument("--cors-origin", metavar="ORIGIN", action="append", default=[],
                   help="let this web origin read the API from a browser (repeatable; there is no wildcard)")
    s.add_argument("--accept-deploys", action="store_true",
                   help="with --store: also accept deploys on a second listener at 127.0.0.1 (this machine only; "
                        "no authentication); creates the store when DIR is missing or empty")
    s.add_argument("--deploy-port", type=int, metavar="N", default=None,
                   help=f"port of the deploy listener (default {DEFAULT_DEPLOY_PORT}); it always binds 127.0.0.1")
    s.add_argument("--max-upload-mb", type=int, metavar="N", default=None,
                   help=f"largest upload accepted, compressed (default {DEFAULT_MAX_UPLOAD_MB})")
    d = sub.add_parser("deploy", help="build the site and put it on a target from buildzr.yaml")
    _add_build_args(d)
    d.add_argument("-t", "--target", metavar="NAME", default=None,
                   help="target name in buildzr.yaml (default: default_target)")
    d.add_argument("--path", metavar="P", default=None, help="site path below the target; overrides the target's path")
    d.add_argument("--from", dest="from_dir", metavar="DIR", default=None,
                   help="deploy an already built site instead of building (the build flags are then refused)")
    d.add_argument("--dry-run", action="store_true",
                   help="load the config, build and check, print the resolved target; write nothing to it")
    d.add_argument("--rollback", action="store_true",
                   help="url targets: make the previous release of the site current again (nothing is built)")
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
    info = build_site(ws, b.out, b.k, b.text_color, viewer=b.viewer, verbose=args.verbose)
    print(f"built {_show(Path(os.path.abspath(b.out)))} ({_summary(b.out, info)})")
    return 0


def _cmd_serve(args: argparse.Namespace) -> int:
    try:
        public_url = normalise_public_url(args.public_url) if args.public_url is not None else None
    except ValueError as e:
        raise _Usage(f"--public-url: {e}") from None
    try:
        origins = list(dict.fromkeys(normalise_origin(o) for o in args.cors_origin))
    except ValueError as e:
        raise _Usage(f"--cors-origin: {e}") from None
    if not args.accept_deploys:
        for flag, v in (("--deploy-port", args.deploy_port), ("--max-upload-mb", args.max_upload_mb)):
            if v is not None:
                raise _Usage(f"{flag} needs --accept-deploys")
    if args.accept_deploys:
        if args.store is None:
            raise _Usage("--accept-deploys needs --store DIR (deploys go into a store)")
        if args.dir is not None:
            raise _Usage("--store and a site DIR cannot be used together")
        return _serve_deploys(args, public_url, origins)
    if args.store is not None:
        if args.dir is not None:
            raise _Usage("--store and a site DIR cannot be used together")
        try:
            Store.open(args.store)  # refuses a folder that is not a store, with one line
        except StoreError as e:
            return _fail(str(e))
        try:
            serve_store(args.store, args.host, args.port, public_url, origins)
        except StoreError as e:
            return _fail(str(e))
        except OSError as e:
            return _fail(f"cannot serve on {args.host}:{args.port}: {e.strerror or e}")
        return 0
    directory = args.dir
    if directory is None:
        cfg = _load_config(None)
        directory = str(cfgmod.resolve_build(cfg, os.environ).out) if cfg is not None else DEFAULT_OUT
    if not os.path.isfile(os.path.join(directory, "data", "index.json")) and \
            not os.path.isfile(os.path.join(directory, "index.html")):
        return _fail(f"{directory} does not look like a built site (run `buildzr build` first)")
    try:
        serve(directory, args.host, args.port, public_url, origins)
    except OSError as e:
        return _fail(f"cannot serve on {args.host}:{args.port}: {e.strerror or e}")
    return 0


def _serve_deploys(args: argparse.Namespace, public_url: Optional[str], origins: list[str]) -> int:
    deploy_port = DEFAULT_DEPLOY_PORT if args.deploy_port is None else args.deploy_port
    max_mb = DEFAULT_MAX_UPLOAD_MB if args.max_upload_mb is None else args.max_upload_mb
    if not 0 <= deploy_port <= 65535:
        raise _Usage("--deploy-port: expected a port number from 0 to 65535")
    if deploy_port != 0 and deploy_port == args.port:
        raise _Usage("--deploy-port must differ from --port")
    if max_mb < 1:
        raise _Usage("--max-upload-mb: expected a whole number of at least 1")
    try:
        import jsonschema  # noqa: F401
    except ImportError:
        return _fail("--accept-deploys checks every upload against the JSON schemas and needs jsonschema; "
                     "install it with: pip install 'buildzr[serve]'")
    try:
        store = Store.open(args.store, create=True, grace=DEPLOY_GRACE_SECONDS, exclusive=True)
    except StoreError as e:
        return _fail(str(e))
    try:
        run_instance(store, args.host, args.port, deploy_port, max_mb, public_url, tuple(origins))
    except OSError as e:
        return _fail(f"cannot serve on {args.host}:{args.port} and 127.0.0.1:{deploy_port}: {e.strerror or e}")
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
    path = target.path if path_override is None else path_override
    if args.rollback:
        if target.url is None:
            raise _Usage("--rollback works with url targets only (a dir target keeps no previous release)")
        clash = [f for f, v in (("--workspace", args.workspace), ("--k", args.k), ("--text-color", args.text_color),
                                ("--no-viewer", args.no_viewer or None), ("--from", args.from_dir)) if v is not None]
        if clash:
            raise _Usage(f"{', '.join(clash)} cannot be used with --rollback (nothing is built)")
    if target.url is not None:
        return _deploy_url(args, cfg, target.url, target.name, path, target.timeout, target.viewer)
    assert target.dir is not None
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
            info = build_site(b.need_workspace(), site, b.k, b.text_color, viewer=viewer, verbose=args.verbose)
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


def _deploy_url(args: argparse.Namespace, cfg: Config, url: str, name: str, path: str, timeout: float,
                target_viewer: bool) -> int:
    """``deploy`` to a ``url`` target: build (or ``--from``), check, pack and upload; or ``--rollback``."""
    try:
        path = normalise_site_path(path)
    except SitePathError as e:
        raise _Usage(f"site path: {e}") from None
    try:
        dc.parse_address(url)
    except dc.DeployFailed as e:
        return dc.report(e)
    if args.rollback:
        try:
            return dc.rollback(url, path, timeout, args.dry_run)
        except dc.DeployFailed as e:
            return dc.report(e)
        except KeyboardInterrupt:
            return _fail("interrupted; the rollback may or may not have happened (check the instance)", 3)
    b: Optional[_BuildArgs] = None
    if args.from_dir is not None:
        if not os.path.isfile(os.path.join(args.from_dir, "data", "index.json")):
            return _fail(f"{args.from_dir} does not look like a built site (no data/index.json)")
    else:
        b = _BuildArgs(args, cfg, need_out=False)
        b.need_workspace()
    stage = tempfile.mkdtemp(prefix="buildzr-deploy-")
    try:
        site = os.path.join(stage, "site")
        shown: Optional[str] = None
        if b is None:
            shown = args.from_dir
            try:
                dc.check_tree(args.from_dir)
                shutil.copytree(args.from_dir, site, symlinks=True)
            except dc.DeployFailed as e:
                return dc.report(e)
            except (shutil.Error, OSError) as e:
                return _fail(f"cannot read {args.from_dir}: {e}")
            failed = _check(site)
            if failed:
                return failed
            with open(os.path.join(site, "build.json"), encoding="utf-8") as f:
                info = json.load(f)
            print(f"using {_show(Path(os.path.abspath(args.from_dir)))} ({_summary(site, info)})")
        else:
            info = build_site(b.need_workspace(), site, b.k, b.text_color, viewer=target_viewer and not args.no_viewer,
                              verbose=args.verbose)
            print(f"built ({_summary(site, info)})")
            failed = _check(site)
            if failed:
                return failed
        try:
            return dc.deploy(site, url, path, timeout, args.dry_run, shown=shown)
        except dc.DeployFailed as e:
            return dc.report(e)
        except KeyboardInterrupt:
            return _fail("interrupted; if the upload was not complete nothing changed on the instance", 3)
    finally:
        shutil.rmtree(stage, ignore_errors=True)


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
