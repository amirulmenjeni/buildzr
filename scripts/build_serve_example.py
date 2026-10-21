"""Build the example of ``buildzr serve --example`` into ``buildzr/site/example/`` (committed, shipped in the package).

Usage (from the repository root, with Node 18 or newer on the path, as for ``buildzr build``)::

    uv run python scripts/build_serve_example.py           # rebuild buildzr/site/example/
    uv run python scripts/build_serve_example.py --check   # exit 1 when it differs from a fresh build

Builds ``scripts/serve_example/workspace.py`` without the viewer (``serve --example`` adds the viewer bundle) in a
temporary folder, so no configuration of the caller applies, then replaces ``buildzr/site/example/`` by ``build.json``
and ``data/``. ``--check`` compares only ``data/``: ``build.json`` also holds the buildzr and elkjs versions.
"""

from __future__ import annotations

import argparse
import filecmp
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Sequence

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SOURCE = os.path.join(ROOT, "scripts", "serve_example")
TARGET = os.path.join(ROOT, "buildzr", "site", "example")
NAME = "example"


def build(out: str) -> str:
    """Build the example workspace into ``out``; return its folder."""
    with tempfile.TemporaryDirectory(prefix="buildzr-example-cwd-") as cwd:
        subprocess.run([sys.executable, "-m", "buildzr.site.cli", "build", "--no-viewer", "-w", SOURCE, "-o", out],
                       cwd=cwd, check=True, env={**os.environ, "PYTHONPATH": ROOT})
    return os.path.join(out, NAME)


def same_tree(a: str, b: str) -> bool:
    cmp = filecmp.dircmp(a, b)
    if cmp.left_only or cmp.right_only or cmp.funny_files:
        return False
    _, mismatch, errors = filecmp.cmpfiles(a, b, cmp.common_files, shallow=False)
    return not mismatch and not errors and all(same_tree(os.path.join(a, d), os.path.join(b, d)) for d in cmp.common_dirs)


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--check", action="store_true", help="only compare the committed data with a fresh build")
    args = ap.parse_args(argv)
    with tempfile.TemporaryDirectory(prefix="buildzr-example-out-") as out:
        built = build(out)
        if args.check:
            if not same_tree(os.path.join(built, "data"), os.path.join(TARGET, "data")):
                print("buildzr/site/example/data differs from a fresh build; run scripts/build_serve_example.py",
                      file=sys.stderr)
                return 1
            print("buildzr/site/example/data is up to date")
            return 0
        shutil.rmtree(TARGET, ignore_errors=True)
        os.makedirs(TARGET)
        shutil.copyfile(os.path.join(built, "build.json"), os.path.join(TARGET, "build.json"))
        shutil.copytree(os.path.join(built, "data"), os.path.join(TARGET, "data"))
    print(f"wrote {os.path.relpath(TARGET, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
