"""``buildzr serve``: a read-only server for a built site (standard library only).

Static files, plus the Model API of the site at ``/api/v1/`` and a generated ``/llms.txt`` (see
:mod:`buildzr.site.api`). Only GET and HEAD are answered; nothing is ever written.
"""

from __future__ import annotations

import http.server
import json
import mimetypes
import os
from typing import Any, Optional, Sequence

from buildzr.site.api import PARAMS, Api, ApiError, Source

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
