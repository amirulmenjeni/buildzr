"""The ``buildzr`` command: ``build``, ``serve`` and ``deploy``."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Iterable, Optional

from buildzr.site.build import BuildError, build_site
from buildzr.site.serve import serve


def _add_build_args(p: argparse.ArgumentParser) -> None:
    p.add_argument("--workspace", required=True, help="DSL .py file that creates a Workspace")
    p.add_argument("--k", type=int, default=None, help="layout parameter (default: [tool.buildzr] k, else 4)")
    p.add_argument("--text-color", choices=["wcag", "c4"], default=None,
                   help="node text colour rule (default: [tool.buildzr] text_color, else wcag)")
    p.add_argument("--no-viewer", action="store_true", help="write data only, without the viewer bundle")


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="buildzr", description="Build, serve and deploy a buildzr model site.")
    sub = ap.add_subparsers(dest="cmd", required=True)
    b = sub.add_parser("build", help="build the site directory from a workspace file")
    _add_build_args(b)
    b.add_argument("--out", default="site", help="output directory (default ./site)")
    s = sub.add_parser("serve", help="serve a built site directory")
    s.add_argument("dir", nargs="?", default="site")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--host", default="127.0.0.1", help="default 127.0.0.1; use 0.0.0.0 explicitly to share")
    d = sub.add_parser("deploy", help="build into a target directory (a local directory is the only target)")
    _add_build_args(d)
    d.add_argument("--target", default=".buildzr/site", help="target directory (default .buildzr/site)")
    d.add_argument("--base-path", default="", help="sub directory below the target, e.g. pr/42")
    args = ap.parse_args(list(argv) if argv is not None else None)
    try:
        if args.cmd == "build":
            info = build_site(args.workspace, args.out, args.k, args.text_color, viewer=not args.no_viewer)
            print(f"built {args.out} (modelHash {info['modelHash'][:19]}...)")
        elif args.cmd == "serve":
            if not os.path.isfile(os.path.join(args.dir, "data", "index.json")) and \
                    not os.path.isfile(os.path.join(args.dir, "index.html")):
                raise BuildError(f"{args.dir} does not look like a built site (run `buildzr build` first)")
            serve(args.dir, args.host, args.port)
        else:
            base = args.base_path.strip("/")
            if ".." in base.split("/"):
                raise BuildError("--base-path must not contain '..'")
            dest = os.path.join(args.target, base) if base else args.target
            build_site(args.workspace, dest, args.k, args.text_color, viewer=not args.no_viewer)
            print(f"deployed to {dest}")
    except BuildError as e:
        print(f"buildzr: error: {e}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
