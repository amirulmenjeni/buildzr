"""Run ELK (elkjs) on Node from Python: locate and verify the bundle, keep one process alive.

The default bundle is the unmodified ``elk.bundled.js`` of elkjs 0.12.0 vendored in
``vendor/`` (EPL-2.0, see ``vendor/NOTICE``); its sha256 is checked before every use.
``BUILDZR_ELK=download`` fetches the npm tarball of elkjs 0.12.0 instead, checks the same
sha256 on the extracted file and caches it. ``BUILDZR_NODE`` names the node executable.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import shutil
import subprocess
import tarfile
import urllib.request
from typing import Any, Optional

ELK_VERSION = "0.12.0"
ELK_SHA256 = "1222e44f953ce7746af23801e723708f8e6f436b8b377a6a5fc7552f34a307b3"
ELK_TARBALL_URL = f"https://registry.npmjs.org/elkjs/-/elkjs-{ELK_VERSION}.tgz"
ELK_TARBALL_MEMBER = "package/lib/elk.bundled.js"

HERE = os.path.dirname(os.path.abspath(__file__))
VENDORED_ELK = os.path.join(HERE, "vendor", "elk.bundled.js")
RUNNER = os.path.join(HERE, "runner.mjs")

Json = dict[str, Any]


class ElkError(RuntimeError):
    """Node or ELK could not be used (missing node, bad checksum, ELK failure)."""


def _sha256_file(path: str) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def find_node() -> str:
    """Return the node executable (``BUILDZR_NODE`` or ``node`` on PATH) or raise a clear error."""
    exe = os.environ.get("BUILDZR_NODE") or shutil.which("node")
    if not exe or not (os.path.isfile(exe) and os.access(exe, os.X_OK)):
        raise ElkError(
            "Node.js was not found. The layout runs elkjs on Node (version 18 or newer): "
            "install Node and put it on PATH, or set BUILDZR_NODE to the executable."
        )
    return exe


def _cache_dir() -> str:
    base = os.environ.get("XDG_CACHE_HOME") or os.path.join(os.path.expanduser("~"), ".cache")
    return os.path.join(base, "buildzr", f"elkjs-{ELK_VERSION}")


def download_elk() -> str:
    """Fetch the elkjs npm tarball, verify the bundle's sha256 and cache it. Returns the path."""
    target = os.path.join(_cache_dir(), "elk.bundled.js")
    if os.path.isfile(target) and _sha256_file(target) == ELK_SHA256:
        return target
    try:
        with urllib.request.urlopen(ELK_TARBALL_URL, timeout=60) as r:  # noqa: S310 - fixed https URL
            data = r.read()
    except OSError as e:
        raise ElkError(f"could not download elkjs {ELK_VERSION} from {ELK_TARBALL_URL}: {e}") from e
    with tarfile.open(fileobj=io.BytesIO(data), mode="r:gz") as tar:
        member = tar.extractfile(ELK_TARBALL_MEMBER)
        if member is None:
            raise ElkError(f"{ELK_TARBALL_MEMBER} not found in the elkjs tarball")
        blob = member.read()
    got = hashlib.sha256(blob).hexdigest()
    if got != ELK_SHA256:
        raise ElkError(f"downloaded elk.bundled.js has sha256 {got}, expected {ELK_SHA256}")
    os.makedirs(os.path.dirname(target), exist_ok=True)
    tmp = target + ".part"
    with open(tmp, "wb") as f:
        f.write(blob)
    os.replace(tmp, target)
    return target


def elk_bundle_path() -> str:
    """Path of the verified ELK bundle: vendored by default, downloaded with ``BUILDZR_ELK=download``."""
    if os.environ.get("BUILDZR_ELK", "").lower() == "download":
        return download_elk()
    if not os.path.isfile(VENDORED_ELK):
        raise ElkError(f"vendored ELK bundle missing: {VENDORED_ELK} (set BUILDZR_ELK=download to fetch it)")
    got = _sha256_file(VENDORED_ELK)
    if got != ELK_SHA256:
        raise ElkError(f"{VENDORED_ELK} has sha256 {got}, expected {ELK_SHA256}; refusing to run it")
    return VENDORED_ELK


class ElkRunner:
    """One Node process running elkjs; :meth:`layout` sends a batch of graphs and reads the results.

    Use as a context manager. ``total_ms`` adds up the in-process ELK time of every graph laid out.
    """

    def __init__(self, bundle: Optional[str] = None) -> None:
        self.bundle = bundle or elk_bundle_path()
        self.total_ms = 0.0
        self.calls = 0
        self._proc: Optional[subprocess.Popen[str]] = None
        self._next_id = 0

    def __enter__(self) -> "ElkRunner":
        self.start()
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def start(self) -> None:
        node = find_node()
        self._proc = subprocess.Popen(
            [node, RUNNER, self.bundle],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            text=True, encoding="utf-8",
        )
        ready = self._read()
        if not ready.get("ready"):
            raise ElkError(f"unexpected first message from the ELK runner: {ready}")

    def close(self) -> None:
        p = self._proc
        if p is None:
            return
        self._proc = None
        try:
            if p.stdin:
                p.stdin.close()
            p.wait(timeout=10)
        except (OSError, subprocess.TimeoutExpired):
            p.kill()
        finally:
            for s in (p.stdout, p.stderr):
                if s:
                    s.close()

    def _read(self) -> Json:
        assert self._proc is not None and self._proc.stdout is not None
        line = self._proc.stdout.readline()
        if not line:
            err = self._proc.stderr.read() if self._proc.stderr else ""
            raise ElkError(f"the ELK runner exited unexpectedly: {err.strip()[:2000]}")
        out: Json = json.loads(line)
        return out

    def layout(self, graphs: dict[str, Json]) -> dict[str, Json]:
        """Lay out ``graphs`` (name -> ELK graph); returns name -> laid-out graph, adds to ``total_ms``."""
        if not graphs:
            return {}
        if self._proc is None or self._proc.stdin is None:
            raise ElkError("ElkRunner is not started")
        self._next_id += 1
        req = {"id": self._next_id, "graphs": graphs}
        try:
            self._proc.stdin.write(json.dumps(req, separators=(",", ":")) + "\n")
            self._proc.stdin.flush()
        except OSError as e:
            raise ElkError(f"cannot talk to the ELK runner: {e}") from e
        resp = self._read()
        out: dict[str, Json] = {}
        for name, r in resp["results"].items():
            if "error" in r:
                raise ElkError(f"ELK failed on {name}: {r['error']}")
            self.total_ms += float(r["ms"])
            out[name] = r["graph"]
        self.calls += len(out)
        return out
