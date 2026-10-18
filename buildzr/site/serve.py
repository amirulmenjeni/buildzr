"""``buildzr serve``: a read-only server for a built site (standard library only).

Static files, plus the Model API of the site at ``/api/v1/`` and a generated ``/llms.txt`` (see
:mod:`buildzr.site.api`). Only GET and HEAD are answered; nothing is ever written.
"""

from __future__ import annotations

import hashlib
import http.server
import json
import mimetypes
import os
import re
import threading
from typing import Any, Optional, Sequence
from urllib.parse import quote, unquote

from buildzr.site.api import API_VERSION, PARAMS, Api, ApiError, Source
from buildzr.site.store import Route, Store

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


def make_server(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
                cors_origins: Sequence[str] = ()) -> http.server.ThreadingHTTPServer:
    """A server bound to ``host:port`` (port 0 picks a free one) serving ``directory`` and its API.

    ``public_url`` (no trailing slash) is the base of the ``viewerUrl`` links; ``cors_origins`` are the only
    origins that get ``Access-Control-Allow-Origin``.
    """
    root = os.path.abspath(directory)
    handler = type("SiteHandler", (Handler,), {
        "source": Source(root, public_url), "cors_origins": tuple(cors_origins),
        "directory": root})

    def make(*args: Any, **kw: Any) -> Handler:
        h: Handler = handler(*args, directory=root, **kw)
        return h
    return Server((host, port), make)


def serve(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
          cors_origins: Sequence[str] = ()) -> None:
    """Serve ``directory`` until interrupted."""
    srv = make_server(directory, host, port, public_url, cors_origins)
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"Serving {os.path.abspath(directory)} at {url} (Ctrl+C to stop)")
    print(f"Model API at {(public_url + '/') if public_url else url}api/v1/ (read only)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()


# --- serve --store: several sites on one instance (read only) --------------------------------------------

STORE_PREFIX = "/_buildzr"
SITES_ENDPOINT = "/_buildzr/v1/sites"

#: Files whose name carries a content hash: a miss in the current release is looked up in the previous one.
_HASHED = re.compile(
    r"/data/model\.[0-9a-f]{8}\.json\Z|/data/scene/.+\.[0-9a-f]{8}\.json\Z|/assets/fonts/[^/]+\Z|"
    r"/assets/[^/]+-[A-Za-z0-9_-]{6,}\.[A-Za-z0-9]+\Z")


def normalise_url_path(raw: str) -> Optional[str]:
    """Decode the percent-escapes of a request path once and refuse what cannot be a path in a site.

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


class ReleaseSource(Source):
    """A :class:`Source` for a release: a release is never modified, so it is read once and not looked at again.

    (This also keeps a request that started on a release from failing when the release is pruned half way.)
    """

    def current(self) -> Api:
        with self._lock:
            if self._api is None:
                self._api = self._load()
            return self._api


class StoreHandler(Handler):
    """GET and HEAD only, over a :class:`~buildzr.site.store.Store`: routes the URL to a site, then to its release."""

    store: Store
    public_url: Optional[str] = None
    sources: dict[str, Source]
    sources_lock: threading.Lock

    # --- helpers ----------------------------------------------------------------------------------

    def _api_looking(self) -> bool:
        p = (getattr(self, "path", "") or "").split("?", 1)[0]
        return "/api/v1" in p or p == STORE_PREFIX or p.startswith(STORE_PREFIX + "/")

    def send_error(self, code: int, message: Optional[str] = None, explain: Optional[str] = None) -> None:
        if code == 501 and self.command != "OPTIONS" and self._api_looking():
            err = ApiError(405, "method-not-allowed", "Method not allowed",
                           f"{self.command} is not allowed here; the store is read-only (GET and HEAD)")
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

    def _source(self, route: Route) -> Source:
        key = route.current.dir
        with self.sources_lock:
            src = self.sources.get(key)
            if src is None:
                base = "/" + route.site_path if route.site_path else ""
                src = self.sources[key] = ReleaseSource(key, self.public_url, base)
            if len(self.sources) > 2 * len(self.store.table) + 2:  # drop the Apis of releases that are gone
                live = {r.current.dir for r in self.store.table.routes()}
                for k in [k for k in self.sources if k not in live]:
                    del self.sources[k]
            return src

    def _site_url(self, site_path: str) -> str:
        return (self.public_url or "") + "/" + (site_path + "/" if site_path else "")

    # --- routing ----------------------------------------------------------------------------------

    def _serve(self, head: bool) -> None:
        raw, _, query = self.path.partition("?")
        path = normalise_url_path(raw)
        if path is None:
            self._not_found(head)
            return
        if path == STORE_PREFIX or path.startswith(STORE_PREFIX + "/"):
            if path in (SITES_ENDPOINT, SITES_ENDPOINT + "/"):
                self._sites(head)
            else:
                self._not_found(head, "No such endpoint; the only one is " + SITES_ENDPOINT)
            return
        for attempt in range(3):
            found = self.store.table.find(path)  # one snapshot for the request
            if found is None:
                if path == "/":
                    self._index_page(head)
                else:
                    self._not_found(head)
                return
            if self._dispatch(found[0], found[1], query, head, last=attempt == 2):
                return

    def _dispatch(self, route: Route, remainder: str, query: str, head: bool, last: bool) -> bool:
        """Answer from ``route``; ``False`` (nothing sent) when its release vanished under us and a retry may help."""
        if remainder == "":
            self._send(308, "text/plain", b"", head, location=self._site_url_local(route.site_path)
                       + (("?" + query) if query else ""))
            return True
        if remainder == "/api/v1":
            self._send(301, "text/plain", b"", head,
                       location=self._site_url_local(route.site_path) + "api/v1/" + (("?" + query) if query else ""))
            return True
        if not last and not os.path.isdir(route.current.dir):
            return False
        if remainder.startswith("/api/v1/") or remainder == "/llms.txt":
            source = self._source(route)
            if not last:
                try:
                    source.current()
                except ApiError:
                    if self._stale(route):
                        return False  # replaced while the model was being read: look again
                except Exception:
                    pass
            self.source = source
            try:
                if remainder == "/llms.txt":
                    self._llms(head)
                else:
                    self._api(remainder, query, head)
            finally:
                self.source = None
            return True
        return self._static(route, remainder, head, last)

    def _stale(self, route: Route) -> bool:
        """Whether install or rollback has replaced the release ``route`` points at since the request began."""
        now = self.store.table.route(route.site_path)
        return now is None or now.current.dir != route.current.dir

    def _site_url_local(self, site_path: str) -> str:
        """Root-relative address of a site (the redirect stays on the host the client asked)."""
        return "/" + (quote(site_path, safe="/") + "/" if site_path else "")

    def _static(self, route: Route, remainder: str, head: bool, last: bool) -> bool:
        self.directory = route.current.dir
        self.path = quote(remainder, safe="/")
        fs = self.translate_path(self.path)
        if not os.path.lexists(fs) and route.previous is not None and _HASHED.match(remainder):
            self.directory = route.previous.dir
            fs = self.translate_path(self.path)
            if not os.path.isfile(fs):
                self.directory = route.current.dir
                fs = self.translate_path(self.path)
        if not last and not os.path.lexists(fs) and (not os.path.isdir(route.current.dir) or self._stale(route)):
            return False  # the release was pruned after this request took its snapshot: look again
        if os.path.isdir(fs) and not remainder.endswith("/"):
            self._send(308, "text/plain", b"", head, location=self._site_url_local(route.site_path)
                       + quote(remainder.lstrip("/"), safe="/") + "/")
            return True
        if head:
            http.server.SimpleHTTPRequestHandler.do_HEAD(self)
        else:
            http.server.SimpleHTTPRequestHandler.do_GET(self)
        return True

    # --- store-level answers ----------------------------------------------------------------------

    def _index_page(self, head: bool) -> None:
        import html
        routes = self.store.table.routes()
        items = "".join(f'<li><a href="{html.escape(self._site_url_local(r.site_path), quote=True)}">'
                        f"{html.escape(r.site_path)}</a></li>" for r in routes)
        body = ("<!doctype html><meta charset=utf-8><title>buildzr sites</title><h1>buildzr sites</h1>"
                + (f"<ul>{items}</ul>" if items else "<p>This store has no sites yet.</p>")).encode()
        self._send(200, "text/html; charset=utf-8", body, head)

    def _sites(self, head: bool) -> None:
        sites = []
        state = []
        for r in self.store.table.routes():
            counts: dict[str, Any] = {"elements": None, "relationships": None}
            name: Optional[str] = None
            try:
                model = self._source(r).current().model
                counts = {"elements": len(model["elements"]), "relationships": len(model["relationships"])}
                ws = model.get("workspace")
                name = ws.get("name") if isinstance(ws, dict) and isinstance(ws.get("name"), str) else None
            except Exception:
                pass
            base = self._site_url(r.site_path)
            has_viewer = os.path.isfile(os.path.join(r.current.dir, "index.html"))
            sites.append({"sitePath": r.site_path, "name": name, "currentRelease": r.current.id, "modelHash": r.current.model_hash,
                          "previousModelHash": r.previous.model_hash if r.previous else None,
                          "elements": counts["elements"], "relationships": counts["relationships"],
                          "viewerUrl": base if has_viewer else None, "apiUrl": base + "api/v1/"})
            state.append([r.site_path, r.current.id, r.current.model_hash, r.previous.id if r.previous else None])
        etag = '"' + hashlib.sha256(json.dumps(state, separators=(",", ":")).encode()).hexdigest()[:32] + '"'
        if _etag_matches(self.headers.get("If-None-Match"), etag):
            self._send(304, "", b"", head, etag=etag)
            return
        body = json.dumps({"apiVersion": API_VERSION, "sites": sites}, ensure_ascii=False,
                          separators=(",", ":")).encode()
        self._send(200, "application/json", body, head, etag=etag)


def make_store_server(store: Store, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
                      cors_origins: Sequence[str] = ()) -> http.server.ThreadingHTTPServer:
    """A server bound to ``host:port`` serving every site of ``store`` read only (see ``docs/store.md``)."""
    handler = type("StoreSiteHandler", (StoreHandler,), {
        "store": store, "public_url": public_url, "cors_origins": tuple(cors_origins),
        "sources": {}, "sources_lock": threading.Lock(), "directory": store.dir})

    def make(*args: Any, **kw: Any) -> StoreHandler:
        h: StoreHandler = handler(*args, directory=store.dir, **kw)
        return h
    return Server((host, port), make)


def serve_store(directory: str, host: str = "127.0.0.1", port: int = 8000, public_url: Optional[str] = None,
                cors_origins: Sequence[str] = ()) -> None:
    """Serve the store in ``directory`` until interrupted (it must exist; see :meth:`Store.open`)."""
    store = Store.open(directory)
    srv = make_store_server(store, host, port, public_url, cors_origins)
    url = f"http://{host}:{srv.server_address[1]}/"
    print(f"Serving the store {os.path.abspath(directory)} ({len(store.table)} sites) at {url} (Ctrl+C to stop)")
    print(f"Site list at {(public_url + '/') if public_url else url}_buildzr/v1/sites (read only)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
