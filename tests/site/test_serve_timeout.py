"""The reading listener of ``serve`` closes a connection that stays silent, so an idle client does
not hold a thread for ever. ``READ_TIMEOUT`` is 60 seconds; the tests make it 1 second."""

from __future__ import annotations

import http.client
import socket
import threading
import time
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

import buildzr.site.serve as serve
from buildzr.site.serve import make_workspace_server
from tests.site.test_cli import WS_TEXT, build, make_static

TIMEOUT = 1.0


@pytest.fixture(scope="module")
def base_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("servetimeoutbase")
    (tmp / "workspace.py").write_text(WS_TEXT)
    build(str(tmp / "workspace.py"), tmp / "site", make_static(tmp / "static"))
    return tmp / "site"


@pytest.fixture
def port(base_site: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[int]:
    monkeypatch.setattr(serve, "READ_TIMEOUT", TIMEOUT)
    srv: Any = make_workspace_server(str(base_site), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield int(srv.server_address[1])
    srv.shutdown()
    srv.server_close()


def closed_within(sock: socket.socket, seconds: float) -> bool:
    """True when the server closed the connection (EOF or reset) within ``seconds``."""
    sock.settimeout(seconds)
    try:
        while sock.recv(4096):
            pass
        return True
    except ConnectionResetError:
        return True
    except socket.timeout:
        return False


def test_a_silent_connection_is_closed(port: int) -> None:
    s = socket.create_connection(("127.0.0.1", port))
    try:
        start = time.monotonic()
        assert closed_within(s, 10 * TIMEOUT)
        assert time.monotonic() - start >= TIMEOUT * 0.5  # not closed at once
    finally:
        s.close()


def test_half_a_request_line_is_closed(port: int) -> None:
    s = socket.create_connection(("127.0.0.1", port))
    try:
        s.sendall(b"GET /api/v1/ HT")
        assert closed_within(s, 10 * TIMEOUT)
    finally:
        s.close()


def test_half_of_the_headers_is_closed(port: int) -> None:
    s = socket.create_connection(("127.0.0.1", port))
    try:
        s.sendall(b"GET /api/v1/ HTTP/1.1\r\nHost: 127.0.0.1\r\nX-Slow: ")
        assert closed_within(s, 10 * TIMEOUT)
    finally:
        s.close()


def test_a_normal_request_still_works(port: int) -> None:
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=5)
    try:
        conn.request("GET", "/api/v1/")
        r = conn.getresponse()
        assert r.status == 200 and b'"apiVersion"' in r.read()
    finally:
        conn.close()


def test_a_slow_but_complete_request_still_works(port: int) -> None:
    """The request takes longer than the timeout in all, but no pause between two parts does."""
    parts: list[Callable[[], bytes]] = [lambda: b"GET /api/v1/ HT", lambda: b"TP/1.1\r\nHost: 127.0.0.1\r\n",
                                        lambda: b"Connection: close\r\n", lambda: b"\r\n"]
    s = socket.create_connection(("127.0.0.1", port))
    try:
        start = time.monotonic()
        for i, part in enumerate(parts):
            if i:
                time.sleep(TIMEOUT * 0.4)
            s.sendall(part())
        assert time.monotonic() - start > TIMEOUT
        s.settimeout(5)
        data = b""
        while chunk := s.recv(65536):
            data += chunk
        assert data.startswith(b"HTTP/1.") and b" 200 " in data.split(b"\r\n", 1)[0] and b'"apiVersion"' in data
    finally:
        s.close()


def test_the_timeout_is_one_minute_by_default() -> None:
    assert serve.READ_TIMEOUT == 60
