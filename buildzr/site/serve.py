"""``buildzr serve``: a read-only server for the built workspaces of a build output (standard library only).

Every built workspace is at ``/<name>/``: its static files (the viewer, ``data/``), the Model API at
``/<name>/api/v1/`` and a generated ``/<name>/llms.txt`` (see :mod:`buildzr.site.api`). ``/`` redirects to the only
workspace or lists them; ``/_buildzr/v1/workspaces`` lists them as JSON. Only GET and HEAD are answered; nothing is
ever written.

The build output is scanned again when ``/`` or the list is asked for, and when a request names a workspace that
is not known yet, so workspaces built by another ``buildzr build`` show up without a restart. A folder that has no
``build.json``, or neither ``index.html`` nor ``data/index.json`` (a build is replacing it), is not served.
"""

from __future__ import annotations

import hashlib
import html
import http.server
import json
import mimetypes
import os
import sys
import threading
import time
from dataclasses import dataclass
from typing import Any, Optional, Sequence
from urllib.parse import quote, unquote

from buildzr.site.api import API_VERSION, PARAMS, Api, ApiError, Source
from buildzr.site.build import read_build_json, safe_name

MIME = {".json": "application/json", ".js": "text/javascript", ".mjs": "text/javascript",
        ".css": "text/css", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".html": "text/html"}

API_PREFIX = "/api/v1"

READ_TIMEOUT = 60.0  # seconds a connection of the reading listener may stay silent before the server closes it


def _etag_matches(header: Optional[str], etag: str) -> bool:
    """``If-None-Match`` against ``etag`` (weak comparison, as the rule for GET says)."""
    if not header:
        return False
    if header.strip() == "*":
        return True
    return any(t.strip().removeprefix("W/") == etag for t in header.split(","))


class Server(http.server.ThreadingHTTPServer):
    """The threading server of every listener; the default backlog of 5 drops connections when many readers connect."""

    request_queue_size = 128


class Handler(http.server.SimpleHTTPRequestHandler):
    """GET and HEAD only; no directory listings; nothing outside the served directory."""

    extensions_map = {**mimetypes.types_map, **MIME}
    source: Optional[Source] = None
    cors_origins: tuple[str, ...] = ()

    def setup(self) -> None:
        self.timeout = READ_TIMEOUT  # read when the connection starts, so a test can change READ_TIMEOUT
        super().setup()

    def list_directory(self, path: Any) -> None:
        self.send_error(404, "No permission to list directory")
        return None

    def translate_path(self, path: str) -> str:
        p = super().translate_path(path)
        root = os.path.realpath(self.directory)
        real = os.path.realpath(p)
        if real != root and not real.startswith(root + os.sep):
            return os.path.join(root, ".buildzr-outside-root-404")  # never exists -> 404
        return p

    def end_headers(self) -> None:
        self.send_header("Cache-Control", "no-cache")
        super().end_headers()

    def log_message(self, format: str, *args: Any) -> None:
        pass

    # --- routing ----------------------------------------------------------------------------------

    def _is_api(self) -> bool:
        p = (getattr(self, "path", "") or "").split("?", 1)[0]
        return p == API_PREFIX or p.startswith(API_PREFIX + "/")

    def do_GET(self) -> None:
        if not self._special(head=False):
            super().do_GET()

    def do_HEAD(self) -> None:
        if not self._special(head=True):
            super().do_HEAD()

    def _special(self, head: bool) -> bool:
        path, _, query = self.path.partition("?")  # not urlsplit: '//host/x' would read as a network location
        if self.source is not None and (path == API_PREFIX or path.startswith(API_PREFIX + "/")):
            self._api(path, query, head)
            return True
        if self.source is not None and path == "/llms.txt":
            self._llms(head)
            return True
        return False

    def send_error(self, code: int, message: Optional[str] = None, explain: Optional[str] = None) -> None:
        """Methods other than GET and HEAD are 405 problem details under the API and 501 elsewhere."""
        if code == 501 and self.source is not None and self._is_api() and self.command != "OPTIONS":
            err = ApiError(405, "method-not-allowed", "Method not allowed",
                           f"{self.command} is not allowed here; the API is read-only (GET and HEAD)")
            self._send_problem(err, None, head=False, allow=True)
            return
        super().send_error(code, message, explain)

    # --- answers ----------------------------------------------------------------------------------

    def _cors(self) -> None:
        origin = self.headers.get("Origin") if hasattr(self, "headers") else None
        if origin and origin in self.cors_origins:
            self.send_header("Access-Control-Allow-Origin", origin)
            self.send_header("Vary", "Origin")

    def _send(self, status: int, ctype: str, body: bytes, head: bool, etag: Optional[str] = None,
              allow: bool = False, location: Optional[str] = None) -> None:
        self.send_response(status)
        if status != 304:
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
        if etag:
            self.send_header("ETag", etag)
        if allow:
            self.send_header("Allow", "GET, HEAD")
        if location:
            self.send_header("Location", location)
        self._cors()
        self.end_headers()
        if not head and status != 304:
            self.wfile.write(body)

    def _send_problem(self, err: ApiError, model_hash: Optional[str], head: bool, allow: bool = False) -> None:
        instance = getattr(self, "path", "") or ""
        body = json.dumps(err.problem(instance, model_hash), ensure_ascii=False, separators=(",", ":")).encode()
        self._send(err.status, "application/problem+json", body, head, allow=allow)

    def _api(self, path: str, query: str, head: bool) -> None:
        assert self.source is not None
        if path == API_PREFIX:
            self._send(301, "text/plain", b"", head, location=API_PREFIX + "/" + (("?" + query) if query else ""))
            return
        endpoint = path[len(API_PREFIX) + 1:]
        api: Optional[Api] = None
        try:
            api = self.source.current()
            if endpoint != "" and endpoint not in PARAMS:
                raise ApiError(404, "unknown-endpoint", "Unknown endpoint",
                               f"No endpoint {endpoint!r}; see {api.api_base} for the list",
                               endpoints=sorted(PARAMS))
            answer = api.answer(endpoint, query)
        except ApiError as e:
            self._send_problem(e, api.hash if api else None, head)
            return
        except Exception:  # never a traceback to the client
            self._send_problem(ApiError(500, "internal-error", "Internal error",
                                        "the API failed on this request"), api.hash if api else None, head)
            return
        etag = f'"{api.hash}"'
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send(304, "", b"", head, etag=etag)
            return
        body = json.dumps(answer, ensure_ascii=False, separators=(",", ":")).encode()
        self._send(200, "application/json", body, head, etag=etag)

    def _llms(self, head: bool) -> None:
        assert self.source is not None
        try:
            api = self.source.current()
        except ApiError as e:
            body = f"{e.title}: {e.detail}\n".encode()
            self._send(503, "text/plain; charset=utf-8", body, head)
            return
        etag = f'"{api.hash}"'
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send(304, "", b"", head, etag=etag)
            return
        self._send(200, "text/plain; charset=utf-8", api.llms_txt().encode(), head, etag=etag)


def make_workspace_server(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
                          cors_origins: Sequence[str] = ()) -> http.server.ThreadingHTTPServer:
    """A server bound to ``host:port`` (port 0 picks a free one) serving ONE built workspace at ``/``.

    The building block of :func:`make_server` (which puts each workspace at ``/<name>/``), kept for tests and tools.
    ``public_url`` (no trailing slash) is the base of the ``viewerUrl`` links; ``cors_origins`` are the only
    origins that get ``Access-Control-Allow-Origin``.
    """
    root = os.path.abspath(directory)
    handler = type("OneWorkspaceHandler", (Handler,), {
        "source": Source(root, public_url), "cors_origins": tuple(cors_origins),
        "directory": root})

    def make(*args: Any, **kw: Any) -> Handler:
        h: Handler = handler(*args, directory=root, **kw)
        return h
    return Server((host, port), make)


# --- every built workspace of a build output at /<name>/ ---------------------------------------------------

BUILDZR_PREFIX = "/_buildzr"
WORKSPACES_ENDPOINT = "/_buildzr/v1/workspaces"


def normalise_url_path(raw: str) -> Optional[str]:
    """Decode the percent-escapes of a request path once and refuse what cannot be a path in a built workspace.

    Returns ``None`` (the caller answers 404) for a path that does not start with ``/``, is not valid UTF-8 once
    decoded, contains a backslash, a NUL or another control character, an empty segment (a trailing ``/`` is fine) or a
    ``.``/``..`` segment. The result is never decoded again.
    """
    if not raw.startswith("/"):
        return None
    try:
        path = unquote(raw, errors="strict")
    except UnicodeDecodeError:
        return None
    if "\\" in path or any(ord(c) < 0x20 or ord(c) == 0x7F for c in path):
        return None
    segments = path[1:].split("/")
    for i, seg in enumerate(segments):
        if seg in (".", "..") or (seg == "" and i != len(segments) - 1):
            return None
    return path


def is_built_workspace(folder: str) -> bool:
    """Whether ``folder`` holds a complete built workspace: ``build.json`` and ``index.html`` or ``data/index.json``,
    or a ``build.json`` that says the workspace is broken (a broken one built without the viewer has nothing else)."""
    if not os.path.isfile(os.path.join(folder, "build.json")):
        return False
    if os.path.isfile(os.path.join(folder, "index.html")) or os.path.isfile(os.path.join(folder, "data", "index.json")):
        return True
    info = read_build_json(folder)
    return info is not None and info.get("status") == "broken"


def holds_built_workspaces(folder: str) -> bool:
    """Whether ``folder`` is a built workspace or has one in a direct subfolder."""
    if os.path.isfile(os.path.join(folder, "build.json")):
        return True
    try:
        return any(is_built_workspace(e.path) for e in os.scandir(folder) if e.is_dir() and not e.name.startswith("."))
    except OSError:
        return False


@dataclass(frozen=True)
class Entry:
    """One served workspace: its URL segment, its folder and its ``build.json``."""

    name: str
    folder: str
    info: dict[str, Any]


class Catalog:
    """The built workspaces of a build output (or one built workspace), found again when the folder changes.

    ``root`` is either a build output (each subfolder with a ``build.json`` is a workspace, named after the folder) or
    one built workspace (served under the name in its ``build.json``, else its folder name made safe).
    """

    def __init__(self, root: str) -> None:
        self.root = os.path.abspath(root)
        self._lock = threading.Lock()
        self._sig: Optional[tuple[Any, ...]] = None
        self._entries: dict[str, Entry] = {}

    def _signature(self) -> tuple[Any, ...]:
        """The mtimes of the root and of each subfolder: they change when a build adds, removes or replaces one."""
        try:
            sig: list[Any] = [os.stat(self.root).st_mtime_ns]
            for e in sorted(os.scandir(self.root), key=lambda e: e.name):
                if e.is_dir() and not e.name.startswith("."):
                    sig.append((e.name, e.stat().st_mtime_ns))
            return tuple(sig)
        except OSError:
            return ()

    def _scan(self) -> dict[str, Entry]:
        found: dict[str, Entry] = {}
        if os.path.isfile(os.path.join(self.root, "build.json")):
            info = read_build_json(self.root) or {}
            name = info.get("name") if isinstance(info.get("name"), str) else None
            name = safe_name(name or "", os.path.basename(self.root))
            if is_built_workspace(self.root):
                found[name] = Entry(name, self.root, info)
            return found
        try:
            names = sorted(e.name for e in os.scandir(self.root) if e.is_dir() and not e.name.startswith("."))
        except OSError:
            return found
        for name in names:
            folder = os.path.join(self.root, name)
            if is_built_workspace(folder):
                found[name] = Entry(name, folder, read_build_json(folder) or {})
        return found

    def entries(self, rescan: bool = False) -> dict[str, Entry]:
        """The workspaces by name; with ``rescan`` the folder is looked at again (only read when it changed)."""
        with self._lock:
            if rescan or self._sig is None:
                sig = self._signature()
                if sig != self._sig:
                    self._entries, self._sig = self._scan(), sig
            return dict(self._entries)

    def find(self, name: str) -> Optional[Entry]:
        """The workspace ``name``, looking at the folder again when it is not known (it may just have been built)."""
        entry = self.entries().get(name)
        if entry is None:
            entry = self.entries(rescan=True).get(name)
        if entry is not None and not is_built_workspace(entry.folder):
            return None  # being replaced right now
        return entry


class WorkspacesHandler(Handler):
    """GET and HEAD only, over a :class:`Catalog`: routes ``/<name>/...`` to that built workspace."""

    catalog: Catalog
    public_url: Optional[str] = None
    sources: dict[str, Source]
    sources_lock: threading.Lock

    def _api_looking(self) -> bool:
        p = (getattr(self, "path", "") or "").split("?", 1)[0]
        return "/api/v1" in p or p == BUILDZR_PREFIX or p.startswith(BUILDZR_PREFIX + "/")

    def send_error(self, code: int, message: Optional[str] = None, explain: Optional[str] = None) -> None:
        if code == 501 and self.command != "OPTIONS" and self._api_looking():
            err = ApiError(405, "method-not-allowed", "Method not allowed",
                           f"{self.command} is not allowed here; the API is read-only (GET and HEAD)")
            self._send_problem(err, None, head=False, allow=True)
            return
        super(Handler, self).send_error(code, message, explain)

    def do_GET(self) -> None:
        self._serve(head=False)

    def do_HEAD(self) -> None:
        self._serve(head=True)

    def _not_found(self, head: bool, what: str = "No such page") -> None:
        if self._api_looking():
            self._send_problem(ApiError(404, "not-found", "Not found", what), None, head)
        elif head:
            self._send(404, "text/plain; charset=utf-8", b"", True)
        else:
            self.send_error(404, "Not Found")

    def _source(self, entry: Entry) -> Source:
        with self.sources_lock:
            src = self.sources.get(entry.name)
            if src is None or src.directory != entry.folder:
                src = self.sources[entry.name] = Source(entry.folder, self.public_url, "/" + entry.name)
            return src

    def _url(self, name: str) -> str:
        """Where readers find workspace ``name``: under ``--public-url`` when it is set, else root-relative."""
        return (self.public_url or "") + "/" + quote(name) + "/"

    # --- routing ----------------------------------------------------------------------------------

    def _serve(self, head: bool) -> None:
        raw, _, query = self.path.partition("?")
        path = normalise_url_path(raw)
        if path is None:
            self._not_found(head)
            return
        if path == BUILDZR_PREFIX or path.startswith(BUILDZR_PREFIX + "/"):
            if path in (WORKSPACES_ENDPOINT, WORKSPACES_ENDPOINT + "/"):
                self._list(head)
            else:
                self._not_found(head, "No such endpoint; the only one is " + WORKSPACES_ENDPOINT)
            return
        if path == "/":
            self._root(head)
            return
        name, slash, rest = path[1:].partition("/")
        entry = self.catalog.find(name)
        if entry is None:
            self._not_found(head)
            return
        remainder = slash + rest
        local = "/" + quote(name) + "/"
        if remainder == "":
            self._send(308, "text/plain", b"", head, location=local + (("?" + query) if query else ""))
            return
        if remainder == API_PREFIX:
            self._send(301, "text/plain", b"", head, location=local + "api/v1/" + (("?" + query) if query else ""))
            return
        if remainder.startswith(API_PREFIX + "/") or remainder == "/llms.txt":
            self.source = self._source(entry)
            try:
                if remainder == "/llms.txt":
                    self._llms(head)
                else:
                    self._api(remainder, query, head)
            finally:
                self.source = None
            return
        self._static(entry, remainder, head)

    def _static(self, entry: Entry, remainder: str, head: bool) -> None:
        self.directory = entry.folder
        self.path = quote(remainder, safe="/")
        fs = self.translate_path(self.path)
        if os.path.isdir(fs) and not remainder.endswith("/"):
            self._send(308, "text/plain", b"", head,
                       location="/" + quote(entry.name) + "/" + quote(remainder.lstrip("/"), safe="/") + "/")
            return
        if head:
            http.server.SimpleHTTPRequestHandler.do_HEAD(self)
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)

    # --- answers about every workspace ------------------------------------------------------------

    def _root(self, head: bool) -> None:
        entries = self.catalog.entries(rescan=True)
        if len(entries) == 1:
            name = next(iter(entries))
            self._send(302, "text/plain", b"", head, location="/" + quote(name) + "/")
            return
        rows = []
        for e in entries.values():
            title = e.info.get("workspace") if isinstance(e.info.get("workspace"), str) else None
            model_hash = e.info.get("modelHash") if isinstance(e.info.get("modelHash"), str) else ""
            link = html.escape("/" + quote(e.name) + "/", quote=True)
            rows.append(f'<li><a href="{link}">{html.escape(e.name)}</a>'
                        + (f" &middot; {html.escape(title)}" if title and title != e.name else "")
                        + (f" <small><code>{html.escape(model_hash[:19])}</code></small>" if model_hash else "")
                        + "</li>")
        body = ("<!doctype html><meta charset=utf-8><meta name=viewport content='width=device-width'>"
                "<title>buildzr workspaces</title><h1>buildzr workspaces</h1>"
                + (f"<ul>{''.join(rows)}</ul>" if rows else "<p>No built workspace here yet. "
                   "Run <code>buildzr build</code>.</p>")
                + f'<p><a href="{WORKSPACES_ENDPOINT}">{WORKSPACES_ENDPOINT}</a> lists them as JSON.</p>').encode()
        self._send(200, "text/html; charset=utf-8", body, head)

    def _list(self, head: bool) -> None:
        items = []
        for e in self.catalog.entries(rescan=True).values():
            base = self._url(e.name)
            src = e.info.get("input")
            try:
                built_at: Optional[str] = time.strftime(
                    "%Y-%m-%dT%H:%M:%SZ", time.gmtime(os.stat(os.path.join(e.folder, "build.json")).st_mtime))
            except OSError:
                built_at = None
            items.append({
                "name": e.name, "path": "/" + e.name + "/",
                "workspaceName": e.info.get("workspace") if isinstance(e.info.get("workspace"), str) else None,
                "viewerUrl": base if os.path.isfile(os.path.join(e.folder, "index.html")) else None,
                "apiUrl": base + "api/v1/", "llmsUrl": base + "llms.txt",
                "modelHash": e.info.get("modelHash"), "builtAt": built_at,
                "source": src.get("file") if isinstance(src, dict) else None})
        body = json.dumps({"apiVersion": API_VERSION, "workspaces": items}, ensure_ascii=False,
                          separators=(",", ":")).encode()
        etag = '"' + hashlib.sha256(body).hexdigest()[:32] + '"'
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send(304, "", b"", head, etag=etag)
            return
        self._send(200, "application/json", body, head, etag=etag)


def make_server(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
                cors_origins: Sequence[str] = ()) -> http.server.ThreadingHTTPServer:
    """A server bound to ``host:port`` (port 0 picks a free one) serving every built workspace of ``directory``.

    ``directory`` is a build output or one built workspace. ``public_url`` (no trailing slash) is the base of the
    ``viewerUrl`` links; ``cors_origins`` are the only origins that get ``Access-Control-Allow-Origin``.
    """
    root = os.path.abspath(directory)
    handler = type("ServedWorkspacesHandler", (WorkspacesHandler,), {
        "catalog": Catalog(root), "public_url": public_url, "cors_origins": tuple(cors_origins),
        "sources": {}, "sources_lock": threading.Lock(), "directory": root})

    def make(*args: Any, **kw: Any) -> WorkspacesHandler:
        h: WorkspacesHandler = handler(*args, directory=root, **kw)
        return h
    return Server((host, port), make)


def serve(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
          cors_origins: Sequence[str] = (), shown: Optional[str] = None) -> None:
    """Serve every built workspace of ``directory`` until interrupted; print where each one is."""
    srv = make_server(directory, host, port, public_url, cors_origins)
    url = f"http://{host}:{srv.server_address[1]}/"
    base = (public_url + "/") if public_url else url
    entries = Catalog(directory).entries()
    print(f"Serving {shown or os.path.abspath(directory)} at {url} (Ctrl+C to stop)")
    for name in entries:
        print(f"  {base}{quote(name)}/")
    print(f"Workspace list at {base}{WORKSPACES_ENDPOINT[1:]}")
    sys.stdout.flush()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
