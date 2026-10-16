"""``buildzr serve``: a read-only static file server for a built site (standard library only)."""

from __future__ import annotations

import functools
import http.server
import mimetypes
import os
from typing import Any

MIME = {".json": "application/json", ".js": "text/javascript", ".mjs": "text/javascript",
        ".css": "text/css", ".woff2": "font/woff2", ".svg": "image/svg+xml", ".html": "text/html"}


class Handler(http.server.SimpleHTTPRequestHandler):
    """GET and HEAD only; no directory listings; nothing outside the served directory."""

    extensions_map = {**mimetypes.types_map, **MIME}

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


def make_server(directory: str, host: str = "127.0.0.1", port: int = 8000) -> http.server.ThreadingHTTPServer:
    """A server bound to ``host:port`` (port 0 picks a free one) serving ``directory``."""
    return http.server.ThreadingHTTPServer((host, port), functools.partial(Handler, directory=os.path.abspath(directory)))


def serve(directory: str, host: str = "127.0.0.1", port: int = 8000) -> None:
    """Serve ``directory`` until interrupted."""
    srv = make_server(directory, host, port)
    print(f"Serving {os.path.abspath(directory)} at http://{host}:{srv.server_address[1]}/ (Ctrl+C to stop)")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        srv.server_close()
