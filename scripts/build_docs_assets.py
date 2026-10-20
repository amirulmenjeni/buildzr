"""Stage what the docs' Run Code button loads into ``docs/runcode/`` (gitignored), before ``mkdocs build``.

Usage (from the repository root, after ``npm ci`` in ``viewer/``)::

    uv run python scripts/build_docs_assets.py [--out docs/runcode] [--viewer DIR | --no-viewer-build]

Writes:

* ``viewer/``: the viewer bundle (``npm run build`` in ``viewer/``, or a built one given with ``--viewer``); the docs
  embed it in an iframe in embed mode.
* ``wheels/buildzr-<version>-py3-none-any.whl``: a slim wheel made from the source tree, only what the in-memory
  build needs (no PlantUML jars, no viewer bundle, no elkjs: about 0.3 MB instead of 22 MB).
* ``wheels/pyhumps-3.8.0-py3-none-any.whl``: the one pure-Python dependency Pyodide does not ship, the exact file
  ``uv.lock`` pins (sha256 checked; cached in ``~/.cache/buildzr/docs``).
* ``elk.bundled.js`` (the vendored elkjs) and ``browser_elk.js`` (its synchronous runner).
* ``manifest.json``: the wheels and every file with its sha256, so the page can ask for ``file?v=<hash>``.

Deterministic (same sources give the same bytes) and idempotent (the folder is replaced as a whole). Stdlib only.
"""

from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import urllib.request
import zipfile
from typing import Iterable, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PACKAGE = os.path.join(ROOT, "buildzr")
STATIC = os.path.join(PACKAGE, "site", "static")
LAYOUT = os.path.join(PACKAGE, "site", "layout")
#: Pyodide release the page loads from the jsdelivr CDN (keep in step with docs/javascripts/runcode-worker.js).
PYODIDE_VERSION = "0.28.3"
#: Parts of the package the browser never uses: the PlantUML jars, the viewer bundle (staged on its own), the built
#: example of ``buildzr serve --example``, elkjs (loaded as JavaScript) and the Node runner.
DROP = ("buildzr/jars/", "buildzr/site/static/", "buildzr/site/example/", "buildzr/site/layout/vendor/",
        "buildzr/site/layout/runner.mjs", "buildzr/site/layout/browser_elk.js")
KEEP_SUFFIXES = (".py", ".json", ".txt", ".typed")
#: Pure-Python wheels the slim wheel needs that Pyodide does not ship (typing-extensions it does).
VENDORED = ("pyhumps",)
ZIP_DATE = (1980, 1, 1, 0, 0, 0)


def version() -> str:
    with open(os.path.join(PACKAGE, "__about__.py"), encoding="utf-8") as f:
        m = re.search(r'^VERSION\s*=\s*"([^"]+)"', f.read(), re.M)
    if not m:
        raise SystemExit("no VERSION in buildzr/__about__.py")
    return m.group(1)


def package_files() -> list[str]:
    """Paths (relative to the repository, ``/``-separated, sorted) of the package files the slim wheel holds."""
    out: list[str] = []
    for root, dirs, names in os.walk(PACKAGE):
        dirs[:] = sorted(d for d in dirs if d != "__pycache__")
        for name in names:
            rel = os.path.relpath(os.path.join(root, name), ROOT).replace(os.sep, "/")
            if name.endswith(KEEP_SUFFIXES) and not rel.startswith(DROP):
                out.append(rel)
    return sorted(out)


def _record_hash(data: bytes) -> str:
    return "sha256=" + base64.urlsafe_b64encode(hashlib.sha256(data).digest()).rstrip(b"=").decode()


def _write(z: zipfile.ZipFile, name: str, data: bytes) -> None:
    info = zipfile.ZipInfo(name, ZIP_DATE)
    info.external_attr = 0o644 << 16
    info.compress_type = zipfile.ZIP_DEFLATED
    z.writestr(info, data, compresslevel=9)


def slim_wheel(out_dir: str) -> str:
    """Write ``buildzr-<version>-py3-none-any.whl`` into ``out_dir``; return its file name."""
    v = version()
    dist_info = f"buildzr-{v}.dist-info"
    entries: list[tuple[str, bytes]] = []
    for rel in package_files():
        with open(os.path.join(ROOT, rel), "rb") as f:
            entries.append((rel, f.read()))
    metadata = (f"Metadata-Version: 2.1\nName: buildzr\nVersion: {v}\nSummary: buildzr for the docs' Run Code "
                "(slim: no PlantUML export, no viewer, no Node layout)\nRequires-Python: >=3.10\n"
                "Requires-Dist: pyhumps==3.8.0\nRequires-Dist: typing-extensions>=4.12.2\n").encode()
    wheel = b"Wheel-Version: 1.0\nGenerator: buildzr scripts/build_docs_assets.py\nRoot-Is-Purelib: true\nTag: py3-none-any\n"
    entries += [(f"{dist_info}/METADATA", metadata), (f"{dist_info}/WHEEL", wheel)]
    record = "".join(f"{name},{_record_hash(data)},{len(data)}\n" for name, data in entries)
    record += f"{dist_info}/RECORD,,\n"
    entries.append((f"{dist_info}/RECORD", record.encode()))
    name = f"buildzr-{v}-py3-none-any.whl"
    with zipfile.ZipFile(os.path.join(out_dir, name), "w") as z:
        for path, data in entries:
            _write(z, path, data)
    return name


def locked_wheel(package: str) -> tuple[str, str]:
    """``(url, sha256)`` of the ``py3-none-any`` wheel of ``package`` in ``uv.lock``."""
    with open(os.path.join(ROOT, "uv.lock"), encoding="utf-8") as f:
        lock = f.read()
    block = re.search(r'\[\[package\]\]\nname = "' + re.escape(package) + r'"\n(.*?)(?=\n\[\[package\]\]|\Z)', lock, re.S)
    if not block:
        raise SystemExit(f"{package} is not in uv.lock")
    m = re.search(r'\{ url = "([^"]+-py3-none-any\.whl)", hash = "sha256:([0-9a-f]{64})"', block.group(1))
    if not m:
        raise SystemExit(f"uv.lock has no py3-none-any wheel of {package}")
    return m.group(1), m.group(2)


def fetch_wheel(package: str, out_dir: str) -> str:
    """Copy the locked wheel of ``package`` into ``out_dir`` (downloaded once, sha256 checked); return its name."""
    url, sha = locked_wheel(package)
    name = url.rsplit("/", 1)[1]
    cache = os.path.join(os.environ.get("XDG_CACHE_HOME") or os.path.expanduser("~/.cache"), "buildzr", "docs")
    cached = os.path.join(cache, name)
    if not (os.path.isfile(cached) and _sha256(cached) == sha):
        os.makedirs(cache, exist_ok=True)
        with urllib.request.urlopen(url, timeout=60) as r:  # noqa: S310 - the https URL uv.lock pins
            data = r.read()
        if hashlib.sha256(data).hexdigest() != sha:
            raise SystemExit(f"{url}: sha256 differs from uv.lock")
        with open(cached + ".part", "wb") as f:
            f.write(data)
        os.replace(cached + ".part", cached)
    shutil.copyfile(cached, os.path.join(out_dir, name))
    return name


def _sha256(path: str) -> str:
    with open(path, "rb") as f:
        return hashlib.sha256(f.read()).hexdigest()


def build_viewer() -> None:
    """``npm run build`` in ``viewer/`` (its dependencies must be installed: ``npm ci``)."""
    viewer = os.path.join(ROOT, "viewer")
    if not os.path.isdir(os.path.join(viewer, "node_modules")):
        raise SystemExit("viewer/node_modules is missing: run `npm ci` in viewer/ first")
    npm = shutil.which("npm")
    if not npm:
        raise SystemExit("npm was not found: Node.js 22 is needed to build the viewer")
    subprocess.run([npm, "run", "build"], cwd=viewer, check=True, stdout=sys.stderr)


def stage(out: str, viewer: str) -> dict[str, object]:
    """Fill a new folder and put it at ``out`` (replacing what was there); return the manifest."""
    if not os.path.isfile(os.path.join(viewer, "index.html")):
        raise SystemExit(f"no built viewer in {viewer}: run `npm run build` in viewer/")
    parent = os.path.dirname(os.path.abspath(out))
    os.makedirs(parent, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix=".runcode-", dir=parent)
    try:
        shutil.copytree(viewer, os.path.join(tmp, "viewer"))
        wheels = os.path.join(tmp, "wheels")
        os.makedirs(wheels)
        names = [slim_wheel(wheels)] + [fetch_wheel(p, wheels) for p in VENDORED]
        shutil.copyfile(os.path.join(LAYOUT, "vendor", "elk.bundled.js"), os.path.join(tmp, "elk.bundled.js"))
        shutil.copyfile(os.path.join(LAYOUT, "browser_elk.js"), os.path.join(tmp, "browser_elk.js"))
        manifest: dict[str, object] = {
            "schema": "buildzr.runcode/1", "buildzr": version(), "pyodide": PYODIDE_VERSION,
            "wheels": ["wheels/" + n for n in names], "files": dict(_hashes(tmp)),
        }
        with open(os.path.join(tmp, "manifest.json"), "w", encoding="utf-8") as f:
            json.dump(manifest, f, indent=1, sort_keys=True)
            f.write("\n")
        if os.path.isdir(out):
            shutil.rmtree(out)
        os.replace(tmp, out)
        return manifest
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def _hashes(folder: str) -> Iterable[tuple[str, str]]:
    for root, dirs, names in os.walk(folder):
        dirs.sort()
        for name in sorted(names):
            path = os.path.join(root, name)
            yield os.path.relpath(path, folder).replace(os.sep, "/"), _sha256(path)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0] if __doc__ else None)
    ap.add_argument("--out", default=os.path.join(ROOT, "docs", "runcode"), help="default: docs/runcode")
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--viewer", help="a built viewer folder to use instead of building viewer/")
    group.add_argument("--no-viewer-build", action="store_true",
                       help="use buildzr/site/static as it is (built earlier with `npm run build`)")
    args = ap.parse_args(argv)
    if not args.viewer and not args.no_viewer_build:
        build_viewer()
    manifest = stage(args.out, args.viewer or STATIC)
    files = manifest["files"]
    assert isinstance(files, dict)
    total = sum(os.path.getsize(os.path.join(args.out, p)) for p in files)
    print(f"{os.path.relpath(args.out, ROOT)}: {len(files)} files, {total:,} bytes; wheels: "
          + ", ".join(f"{w} ({os.path.getsize(os.path.join(args.out, str(w))):,} bytes)"
                      for w in manifest["wheels"]))  # type: ignore[attr-defined]
    return 0


if __name__ == "__main__":
    sys.exit(main())
