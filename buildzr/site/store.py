"""The site store: a folder that holds several sites, each with a current and a previous release.

No HTTP in this module. Layout (``docs/store.md``)::

    DIR/buildzr-store.json        marks the folder as a store; per site path: current and previous release
    DIR/sites/<key>/r-0007/       one release: an ordinary built site; <key> = sha256(site path)[:16]
    DIR/incoming/<random>/        sites being unpacked and checked; emptied when the store is opened
    DIR/deploys.log               one JSON line per install or rollback

A site path never becomes a file system path: the folder name is a hash of it. :meth:`Store.install` and
:meth:`Store.rollback` are plain functions (the deploy listener of a later stage and the tests call them); readers use
the immutable :class:`RouteTable` snapshot, which install and rollback replace under a lock.
"""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import tempfile
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable, Mapping, Optional

STORE_FILE = "buildzr-store.json"
STORE_VERSION = 1
LOG_FILE = "deploys.log"

#: Segment names no site path may contain: a nested site could hide a file of the site above it.
RESERVED = frozenset({"api", "assets", "data", "_buildzr", "index.html", "build.json", "llms.txt"})
MAX_SEGMENTS = 8
MAX_LENGTH = 128
_SEGMENT = re.compile(r"[a-z0-9][a-z0-9._-]*\Z")
_RELEASE = re.compile(r"r-\d{4,}\Z")


class StoreError(Exception):
    """The store cannot be opened or an operation is refused; the message is one line for the user."""


class SitePathError(StoreError):
    """A site path breaks the rules of :func:`normalise_site_path`."""


def normalise_site_path(path: str) -> str:
    """The canonical form of a site path (``""`` is the root); raises :class:`SitePathError` with the reason.

    Segments are ``[a-z0-9][a-z0-9._-]*``; no empty, ``.`` or ``..`` segment, no backslash or NUL; leading and trailing
    ``/`` are removed; at most 8 segments and 128 characters; the reserved names are refused anywhere.
    """
    if not isinstance(path, str):
        raise SitePathError("a site path must be text")
    if "\0" in path:
        raise SitePathError("a site path must not contain a NUL byte")
    if "\\" in path:
        raise SitePathError("a site path must not contain a backslash")
    p = path.strip("/")
    if p == "":
        return ""
    if len(p) > MAX_LENGTH:
        raise SitePathError(f"a site path has at most {MAX_LENGTH} characters")
    segments = p.split("/")
    if len(segments) > MAX_SEGMENTS:
        raise SitePathError(f"a site path has at most {MAX_SEGMENTS} segments")
    for s in segments:
        if s == "":
            raise SitePathError(f"site path {path!r} has an empty segment")
        if s in (".", ".."):
            raise SitePathError(f"site path {path!r} has a {s!r} segment")
        if s in RESERVED:
            raise SitePathError(f"site path {path!r}: {s!r} is a reserved name ({', '.join(sorted(RESERVED))})")
        if not _SEGMENT.match(s):
            raise SitePathError(f"site path segment {s!r} must match [a-z0-9][a-z0-9._-]*")
    return "/".join(segments)


def site_key(site_path: str) -> str:
    """The folder name of a site: the first 16 hex characters of the sha256 of its (canonical) path."""
    return hashlib.sha256(site_path.encode("utf-8")).hexdigest()[:16]


@dataclass(frozen=True)
class Release:
    """One release of a site: ``id`` (``r-0007``), the folder it lives in and the ``modelHash`` of its model."""

    id: str
    dir: str
    model_hash: str


@dataclass(frozen=True)
class Route:
    """A registered site path with its current and previous release; ``last`` is the highest release number used."""

    site_path: str
    current: Release
    previous: Optional[Release]
    last: int


class RouteTable:
    """An immutable snapshot of the routes. Readers hold one; install and rollback make a new one."""

    def __init__(self, routes: Mapping[str, Route]) -> None:
        self._routes: dict[str, Route] = dict(routes)

    def __len__(self) -> int:
        return len(self._routes)

    def __contains__(self, site_path: object) -> bool:
        return site_path in self._routes

    def route(self, site_path: str) -> Optional[Route]:
        return self._routes.get(site_path)

    def routes(self) -> list[Route]:
        return [self._routes[k] for k in sorted(self._routes)]

    def lookup(self, url_path: str) -> Optional[tuple[str, str, str]]:
        """``(site path, release folder, remainder)`` for a decoded, normalised URL path, or ``None``.

        The longest registered site path that is a prefix on whole segments wins; the root site (``""``) catches what no
        other site claims. ``remainder`` starts with ``/`` (``/`` for the site's own address) and is ``""`` when the URL
        names the site path without its trailing slash (the caller redirects).
        """
        r = self.find(url_path)
        if r is None:
            return None
        route, remainder = r
        return route.site_path, route.current.dir, remainder

    def find(self, url_path: str) -> Optional[tuple[Route, str]]:
        """Like :meth:`lookup`, but returns the whole :class:`Route` (the caller may need the previous release)."""
        if not url_path.startswith("/"):
            return None
        segments = url_path[1:].split("/")
        for n in range(len(segments), -1, -1):
            candidate = "/".join(segments[:n])
            route = self._routes.get(candidate)
            if route is not None:
                rest = "/".join(segments[n:])
                if n == len(segments):
                    return route, ("/" if candidate == "" else "")
                return route, "/" + rest
        return None


@dataclass(frozen=True)
class Installed:
    """The result of an install or rollback."""

    release: str
    model_hash: str
    previous_model_hash: Optional[str]


class Store:
    """A store folder. Use :meth:`open`. All writes go through :meth:`install` and :meth:`rollback` (one at a time)."""

    def __init__(self, directory: str, routes: Mapping[str, Route], grace: float = 0.0) -> None:
        self.dir = directory
        #: Seconds a pruned release stays on disk (a request that started on it can finish); 0 deletes at once.
        self.grace = grace
        self._table = RouteTable(routes)
        self._lock = threading.Lock()
        #: Test hook: called with a step name between the steps of install and rollback (may raise).
        self.hook: Optional[Callable[[str], None]] = None

    # --- opening ----------------------------------------------------------------------------------

    @classmethod
    def open(cls, directory: str, create: bool = False, grace: float = 0.0) -> "Store":
        """Open the store in ``directory`` (made when ``create`` is true and the folder is missing or empty).

        ``grace`` is how long a release that install pruned stays on disk before it is deleted (default: not at all).
        """
        d = os.path.abspath(directory)
        marker = os.path.join(d, STORE_FILE)
        if not os.path.isfile(marker):
            if not create:
                raise StoreError(f"{directory} is not a buildzr store (no {STORE_FILE})")
            if os.path.exists(d) and (not os.path.isdir(d) or os.listdir(d)):
                raise StoreError(f"{directory} exists and is not an empty folder or a store; not creating a store there")
            try:
                os.makedirs(d, exist_ok=True)
                _write_store_file(d, {})
            except OSError as e:
                raise StoreError(f"cannot create a store in {directory}: {e.strerror or e}") from None
        try:
            routes = _read_store_file(d)
            os.makedirs(os.path.join(d, "sites"), exist_ok=True)
            _clean(d, routes)
        except OSError as e:
            raise StoreError(f"cannot read the store {directory}: {e.strerror or e}") from None
        return cls(d, routes, grace)

    @property
    def table(self) -> RouteTable:
        """The current snapshot (a plain attribute read; no lock)."""
        return self._table

    # --- operations -------------------------------------------------------------------------------

    def _step(self, name: str) -> None:
        if self.hook is not None:
            self.hook(name)

    def install(self, site_dir: str, site_path: str) -> Installed:
        """Make the checked site in ``site_dir`` (a folder under ``incoming/``) the current release of ``site_path``.

        Steps: rename the folder to ``sites/<key>/r-<n+1>/``; write the new store file (temporary file, fsync,
        ``os.replace``); update the route table; delete the release older than the previous one; append the audit line.
        After a kill at any step, opening the store again finds it consistent.
        """
        sp = normalise_site_path(site_path)
        incoming = os.path.realpath(os.path.join(self.dir, "incoming"))
        src = os.path.realpath(site_dir)
        if not src.startswith(incoming + os.sep) or not os.path.isdir(src):
            raise StoreError("the site folder must be a folder under incoming/ of this store")
        model_hash = _model_hash_of(src)
        with self._lock:
            old = self._table.route(sp)
            n = (old.last if old else 0) + 1
            rid = f"r-{n:04d}"
            parent = os.path.join(self.dir, "sites", site_key(sp))
            target = os.path.join(parent, rid)
            if os.path.lexists(target):
                raise StoreError(f"release folder {rid} of {sp or '/'} already exists")
            os.makedirs(parent, exist_ok=True)
            os.rename(src, target)
            try:
                self._step("renamed")
                new = Route(sp, Release(rid, target, model_hash), old.current if old else None, n)
                routes = {r.site_path: r for r in self._table.routes()}
                routes[sp] = new
                self._write(routes)
            except Exception:
                if self._table.route(sp) is old and not _listed(self.dir, sp, rid):
                    shutil.rmtree(target, ignore_errors=True)
                raise
            self._table = RouteTable(routes)
            self._step("routed")
            if old and old.previous is not None:
                self._retire(old.previous.dir)
            self._step("pruned")
            self._log("install", sp, rid, model_hash, old.current.model_hash if old else None, "ok")
            return Installed(rid, model_hash, old.current.model_hash if old else None)

    def rollback(self, site_path: str) -> Installed:
        """Swap the current and the previous release of ``site_path``; refused when there is no previous one."""
        sp = normalise_site_path(site_path)
        with self._lock:
            old = self._table.route(sp)
            if old is None:
                raise StoreError(f"no site at {sp or '/'}")
            if old.previous is None:
                self._log("rollback", sp, old.current.id, old.current.model_hash, None, "refused: no previous release")
                raise StoreError(f"{sp or '/'} has no previous release to roll back to")
            new = Route(sp, old.previous, old.current, old.last)
            routes = {r.site_path: r for r in self._table.routes()}
            routes[sp] = new
            self._write(routes)
            self._table = RouteTable(routes)
            self._step("routed")
            self._log("rollback", sp, new.current.id, new.current.model_hash, old.current.model_hash, "ok")
            return Installed(new.current.id, new.current.model_hash, old.current.model_hash)

    def _retire(self, path: str) -> None:
        if self.grace <= 0:
            shutil.rmtree(path, ignore_errors=True)
            return
        t = threading.Timer(self.grace, shutil.rmtree, args=(path,), kwargs={"ignore_errors": True})
        t.daemon = True  # a kill leaves an orphan folder; the next open deletes it
        t.start()

    def _write(self, routes: Mapping[str, Route]) -> None:
        _write_store_file(self.dir, routes, step=self._step)

    def _log(self, action: str, site_path: str, release: str, model_hash: str, previous_hash: Optional[str],
             result: str) -> None:
        line = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "sitePath": site_path,
                "release": release, "modelHash": model_hash, "previousModelHash": previous_hash,
                "action": action, "result": result}
        with open(os.path.join(self.dir, LOG_FILE), "a", encoding="utf-8") as f:
            f.write(json.dumps(line, separators=(",", ":")) + "\n")
            f.flush()
            os.fsync(f.fileno())
        self._step("logged")


# --- the store file -------------------------------------------------------------------------------------


def _release_json(r: Release) -> dict[str, str]:
    return {"release": r.id, "modelHash": r.model_hash}


def _write_store_file(directory: str, routes: Mapping[str, Route], step: Optional[Callable[[str], None]] = None) -> None:
    """Write ``buildzr-store.json`` through a temporary file in the same folder and ``os.replace``."""
    sites = {}
    for sp in sorted(routes):
        r = routes[sp]
        sites[sp] = {"last": r.last, "current": _release_json(r.current),
                     "previous": _release_json(r.previous) if r.previous else None}
    text = json.dumps({"version": STORE_VERSION, "sites": sites}, indent=2, sort_keys=True) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=STORE_FILE + ".", suffix=".tmp", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        if step:
            step("store-tmp-written")
        os.replace(tmp, os.path.join(directory, STORE_FILE))
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise
    if step:
        step("store-replaced")


def _listed(directory: str, site_path: str, rid: str) -> bool:
    """Whether the store file on disk names ``rid`` for ``site_path`` (after a failed write we cannot know)."""
    try:
        routes = _read_store_file(directory)
    except (StoreError, OSError):
        return False
    r = routes.get(site_path)
    return bool(r and (r.current.id == rid or (r.previous and r.previous.id == rid)))


def _bad(msg: str) -> StoreError:
    return StoreError(f"{STORE_FILE}: {msg}")


def _read_release(directory: str, site_path: str, v: Any, what: str, last: int) -> Release:
    if not isinstance(v, dict) or set(v) != {"release", "modelHash"}:
        raise _bad(f"site {site_path!r}: '{what}' must be an object with 'release' and 'modelHash'")
    rid, mh = v["release"], v["modelHash"]
    if not isinstance(rid, str) or not _RELEASE.match(rid):
        raise _bad(f"site {site_path!r}: '{what}' release {rid!r} is not like r-0007")
    if not isinstance(mh, str) or not mh:
        raise _bad(f"site {site_path!r}: '{what}' modelHash must be text")
    if int(rid[2:]) > last:
        raise _bad(f"site {site_path!r}: release {rid} is newer than 'last' ({last})")
    sites = os.path.realpath(os.path.join(directory, "sites"))
    path = os.path.join(directory, "sites", site_key(site_path), rid)
    real = os.path.realpath(path)
    if not real.startswith(sites + os.sep):
        raise _bad(f"site {site_path!r}: release {rid} resolves outside sites/")
    if not os.path.isdir(path):
        raise _bad(f"site {site_path!r}: release folder {rid} is listed but missing")
    return Release(rid, path, mh)


def _read_store_file(directory: str) -> dict[str, Route]:
    path = os.path.join(directory, STORE_FILE)
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except OSError as e:
        raise _bad(f"cannot read it: {e.strerror or e}") from None
    except (ValueError, RecursionError) as e:
        raise _bad(f"not valid JSON ({e})") from None
    if not isinstance(data, dict) or set(data) != {"version", "sites"}:
        raise _bad("expected an object with 'version' and 'sites'")
    if data["version"] != STORE_VERSION or isinstance(data["version"], bool):
        raise _bad(f"unknown version {data['version']!r}; this buildzr reads version {STORE_VERSION}")
    if not isinstance(data["sites"], dict):
        raise _bad("'sites' must be an object")
    routes: dict[str, Route] = {}
    for sp, entry in data["sites"].items():
        try:
            canon = normalise_site_path(sp)
        except SitePathError as e:
            raise _bad(str(e)) from None
        if canon != sp:
            raise _bad(f"site path {sp!r} is not in canonical form ({canon!r})")
        if not isinstance(entry, dict) or set(entry) != {"last", "current", "previous"}:
            raise _bad(f"site {sp!r}: expected 'last', 'current' and 'previous'")
        last = entry["last"]
        if not isinstance(last, int) or isinstance(last, bool) or last < 1:
            raise _bad(f"site {sp!r}: 'last' must be a positive integer")
        cur = _read_release(directory, sp, entry["current"], "current", last)
        prev = _read_release(directory, sp, entry["previous"], "previous", last) if entry["previous"] is not None else None
        if prev is not None and prev.id == cur.id:
            raise _bad(f"site {sp!r}: current and previous are the same release")
        routes[sp] = Route(sp, cur, prev, last)
    return routes


def _clean(directory: str, routes: Mapping[str, Route]) -> None:
    """Empty ``incoming/``, delete release folders the store file does not list and stray temporary store files."""
    incoming = os.path.join(directory, "incoming")
    shutil.rmtree(incoming, ignore_errors=True)
    os.makedirs(incoming)
    for name in os.listdir(directory):
        if name.startswith(STORE_FILE + ".") and name.endswith(".tmp"):
            try:
                os.unlink(os.path.join(directory, name))
            except OSError:
                pass
    keep: dict[str, set[str]] = {}
    for sp, r in routes.items():
        ids = keep.setdefault(site_key(sp), set())
        ids.add(r.current.id)
        if r.previous:
            ids.add(r.previous.id)
    sites = os.path.join(directory, "sites")
    for key in os.listdir(sites):
        kd = os.path.join(sites, key)
        if key not in keep:
            _remove(kd)
            continue
        if os.path.islink(kd) or not os.path.isdir(kd):
            _remove(kd)
            continue
        for rid in os.listdir(kd):
            if rid not in keep[key]:
                _remove(os.path.join(kd, rid))


def _remove(path: str) -> None:
    if os.path.islink(path) or not os.path.isdir(path):
        try:
            os.unlink(path)
        except OSError:
            pass
    else:
        shutil.rmtree(path, ignore_errors=True)


def _model_hash_of(site_dir: str) -> str:
    """The ``modelHash`` of a built site: from its model file (named by ``data/index.json``), else ``build.json``."""
    try:
        with open(os.path.join(site_dir, "data", "index.json"), encoding="utf-8") as f:
            name = json.load(f)["model"]["file"]
        data = os.path.realpath(os.path.join(site_dir, "data"))
        full = os.path.realpath(os.path.join(data, name))
        if full.startswith(data + os.sep):
            with open(full, encoding="utf-8") as f:
                h = json.load(f)["modelHash"]
            if isinstance(h, str) and h:
                return h
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    try:
        with open(os.path.join(site_dir, "build.json"), encoding="utf-8") as f:
            h = json.load(f)["modelHash"]
        if isinstance(h, str) and h:
            return h
    except (OSError, ValueError, KeyError, TypeError, RecursionError):
        pass
    raise StoreError("the site folder has no readable modelHash (neither in its model file nor in build.json)")
