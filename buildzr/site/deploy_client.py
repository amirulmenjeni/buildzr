"""The client side of ``buildzr deploy`` for ``url:`` targets: pack a built site and send it to a deploy listener.

Standard library only (``tarfile``, ``gzip``, ``http.client``). The archive is deterministic: sorted names, mtime 0,
owner 0, modes 0644/0755, plain ustar headers. Exit codes as in ``docs/deploy.md``: 0 ok or unchanged, 1 rejected or
not a deploy address, 2 usage, 3 unreachable, interrupted, busy or out of space (worth retrying).
"""

from __future__ import annotations

import gzip
import http.client
import io
import json
import os
import ssl
import sys
import socket
import tarfile
import threading
import time
from dataclasses import dataclass
from typing import Any, Callable, Optional
from urllib.parse import quote, urlsplit

from buildzr.__about__ import VERSION
from buildzr.site.deploy import DEPLOY_ENDPOINT, PROBLEM, ROLLBACK_ENDPOINT, STATUS_ENDPOINT

LOOPBACK_HOSTS = ("127.0.0.1", "localhost", "::1")
TOP_LEVEL = ("assets", "build.json", "data", "index.html")
MAX_ANSWER = 1024 * 1024
TUNNEL_HINT = ("v1 deploys have no authentication, so the deploy listener only listens on 127.0.0.1 of the instance. "
               "Reach a remote instance through an SSH tunnel, for example: ssh -N -L 9001:127.0.0.1:8001 HOST, "
               "then url: http://127.0.0.1:9001")


class DeployFailed(Exception):
    """The deploy did not happen; ``code`` is the exit code, the message is printed as ``buildzr: error: ...``."""

    def __init__(self, message: str, code: int, details: Optional[list[str]] = None) -> None:
        super().__init__(message)
        self.code = code
        self.details = details or []


@dataclass(frozen=True)
class Address:
    scheme: str
    host: str
    port: int
    url: str


def parse_address(url: str) -> Address:
    """The deploy address of a ``url:`` target; :class:`DeployFailed` (exit 2) unless it is loopback http(s)."""
    try:
        u = urlsplit(url)
        host, port = u.hostname, u.port
    except ValueError as e:
        raise DeployFailed(f"{url}: not a valid URL ({e})", 2) from None
    if u.scheme not in ("http", "https") or not host:
        raise DeployFailed(f"{url}: the deploy address must be http://127.0.0.1:PORT", 2)
    if host.lower() not in LOOPBACK_HOSTS:
        raise DeployFailed(f"{url}: {host} is not this machine. {TUNNEL_HINT}", 2)
    if u.path not in ("", "/") or u.query or u.fragment or u.username or u.password or "?" in url or "#" in url \
            or any(c.isspace() for c in url):
        raise DeployFailed(f"{url}: the deploy address is just the scheme, host and port (no path, query or user)", 2)
    if port == 0:
        raise DeployFailed(f"{url}: port 0 is not a deploy address", 2)
    if port is None:
        port = 443 if u.scheme == "https" else 80
    shown = f"[{host}]" if ":" in host else host
    return Address(u.scheme, host, port, f"{u.scheme}://{shown}:{port}")


# --- packing -------------------------------------------------------------------------------------------------


def check_tree(site: str, shown: Optional[str] = None) -> None:
    """Refuse (exit 1) a site folder with entries the instance would refuse, naming them under ``shown``."""
    shown = shown or site
    for name in sorted(os.listdir(site)):
        if name not in TOP_LEVEL:
            raise DeployFailed(f"{shown}: {name} is not part of a built site (only {', '.join(TOP_LEVEL)} are sent)", 1)
    for d, dirs, files in os.walk(site):
        for n in dirs + files:
            full = os.path.join(d, n)
            rel = os.path.relpath(full, site).replace(os.sep, "/")
            if os.path.islink(full):
                raise DeployFailed(f"{shown}: {rel} is a symbolic link; a site is sent as plain files", 1)
            if not (os.path.isdir(full) or os.path.isfile(full)):
                raise DeployFailed(f"{shown}: {rel} is not a regular file", 1)
            if os.path.isfile(full) and not os.access(full, os.R_OK):
                raise DeployFailed(f"{shown}: {rel} cannot be read", 1)


def pack_site(site: str, shown: Optional[str] = None) -> tuple[bytes, int, int]:
    """A deterministic ``.tar.gz`` of the site's contents; ``(archive, files, unpacked bytes)``.

    Only ``index.html``, ``assets/``, ``data/`` and ``build.json`` are packed; anything else at the top, a symbolic
    link or a special file is refused (:class:`DeployFailed`, exit 1), because the instance would refuse it too.
    """
    check_tree(site, shown)
    entries: list[tuple[str, str]] = []
    for d, dirs, files in os.walk(site):
        dirs.sort()
        for n in dirs + files:
            full = os.path.join(d, n)
            entries.append((os.path.relpath(full, site).replace(os.sep, "/"), full))
    entries.sort()
    raw = io.BytesIO()
    n_files = size = 0
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for rel, full in entries:
            info = tarfile.TarInfo(rel)
            info.mtime = 0
            info.uid = info.gid = 0
            info.uname = info.gname = ""
            if os.path.isdir(full):
                info.type = tarfile.DIRTYPE
                info.mode = 0o755
                try:
                    tf.addfile(info)
                except ValueError as e:
                    raise DeployFailed(f"{shown or site}: {rel}: cannot be packed ({e})", 1) from None
                continue
            info.mode = 0o644
            info.size = os.path.getsize(full)
            n_files += 1
            size += info.size
            with open(full, "rb") as f:
                try:
                    tf.addfile(info, f)
                except ValueError as e:
                    raise DeployFailed(f"{shown or site}: {rel}: cannot be packed ({e})", 1) from None
    out = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=out, mtime=0, compresslevel=9) as gz:
        gz.write(raw.getvalue())
    return out.getvalue(), n_files, size


# --- talking to the instance -------------------------------------------------------------------------------------


def _json_doc(heads: dict[str, str], data: bytes) -> Optional[dict[str, Any]]:
    if heads.get("content-type", "").split(";")[0].strip() not in ("application/json", "application/problem+json"):
        return None
    try:
        parsed = json.loads(data)
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _cut(conn: http.client.HTTPConnection) -> None:
    try:
        if conn.sock is not None:
            conn.sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass


def _human(n: int) -> str:
    if n < 1024:
        return f"{n} B"
    if n < 1024 * 1024:
        return f"{n / 1024:.0f} KB"
    return f"{n / (1024 * 1024):.0f} MB"


@dataclass
class Answer:
    status: int
    headers: dict[str, str]
    doc: Optional[dict[str, Any]]


class Client:
    """Requests to one deploy address, with the overall ``timeout`` (seconds) of the target."""

    def __init__(self, address: Address, timeout: float, out: Callable[[str], None] = print) -> None:
        self.a, self.timeout, self.out = address, timeout, out

    def _conn(self, timeout: float) -> http.client.HTTPConnection:
        if self.a.scheme == "https":
            return http.client.HTTPSConnection(self.a.host, self.a.port, timeout=timeout,
                                               context=ssl.create_default_context())
        return http.client.HTTPConnection(self.a.host, self.a.port, timeout=timeout)

    def request(self, method: str, target: str, body: Optional[bytes] = None,
                headers: Optional[dict[str, str]] = None, timeout: Optional[float] = None) -> Answer:
        total = timeout if timeout is not None else self.timeout
        conn = self._conn(total)
        # the socket timeout is per operation; this cuts a server that answers one byte at a time. Not for an upload:
        # the instance may legitimately take long to check it, and cutting it then would hide a finished deploy.
        watchdog = threading.Timer(total, lambda: _cut(conn))
        watchdog.daemon = True
        if body is None:
            watchdog.start()
        hdrs = {"Host": f"{'[' + self.a.host + ']' if ':' in self.a.host else self.a.host}:{self.a.port}"}
        hdrs.update(headers or {})
        try:
            try:
                conn.request(method, target, body=body, headers=hdrs)
            except ConnectionRefusedError:
                raise DeployFailed(f"nothing is listening at {self.a.url}; start the instance with "
                                   "buildzr serve --store DIR --accept-deploys (or open the SSH tunnel)", 3) from None
            except (BrokenPipeError, ConnectionResetError) as e:
                try:  # the instance may have answered early and closed; its answer may still be readable
                    r0 = conn.getresponse()
                    data0 = r0.read(MAX_ANSWER)
                    heads0 = {k.lower(): v for k, v in r0.getheaders()}
                    return Answer(r0.status, heads0, _json_doc(heads0, data0))
                except (http.client.HTTPException, OSError):
                    raise DeployFailed("upload interrupted, nothing changed "
                                       f"(the connection to {self.a.url} failed while sending: {e})", 3) from None
            except ssl.SSLError as e:
                raise DeployFailed(f"cannot talk https to {self.a.url} ({e.reason}); the v1 deploy listener speaks "
                                   "plain http: use http://127.0.0.1:PORT", 3) from None
            except OSError as e:
                raise DeployFailed(f"cannot reach {self.a.url}: {e.strerror or e}", 3) from None
            try:
                r = conn.getresponse()
                data = r.read(MAX_ANSWER + 1)
                if len(data) > MAX_ANSWER:
                    raise self._not_ours()
            except (http.client.BadStatusLine, http.client.LineTooLong, http.client.UnknownProtocol) as e:
                if isinstance(e, http.client.RemoteDisconnected):
                    if body:
                        raise self._lost(e) from None
                    raise DeployFailed(f"no answer from {self.a.url} ({type(e).__name__}: {e})", 3) from None
                raise self._not_ours() from None
            except (http.client.HTTPException, OSError) as e:
                if body:
                    raise self._lost(e) from None
                raise DeployFailed(f"no answer from {self.a.url} ({type(e).__name__}: {e})", 3) from None
            heads = {k.lower(): v for k, v in r.getheaders()}
            return Answer(r.status, heads, _json_doc(heads, data))
        finally:
            watchdog.cancel()
            conn.close()

    def _lost(self, e: BaseException) -> DeployFailed:
        """No answer to an upload: a cut while sending changed nothing; a cut after all of it was sent may not have."""
        return DeployFailed(f"no answer from {self.a.url} after the upload ({type(e).__name__}: {e}); the instance "
                            "may still have installed it: deploy again (an unchanged site answers \"unchanged\") or "
                            "look at /_buildzr/v1/sites of the instance", 3)

    def _ours(self, a: Answer) -> bool:
        """Whether the answer comes from a buildzr deploy listener."""
        if a.doc is None:
            return False
        if a.status == 200:
            return "instanceVersion" in a.doc
        t = a.doc.get("type")
        return isinstance(t, str) and t.startswith(PROBLEM) and (a.status != 404 or a.doc.get("code") == "no-site")

    def _not_ours(self) -> DeployFailed:
        return DeployFailed(f"{self.a.url} is not a buildzr deploy address (is it the reading port, or another "
                            "server?); the deploy listener is the --deploy-port of an instance started with "
                            "--accept-deploys", 1)

    def status(self) -> dict[str, Any]:
        a = self.request("GET", STATUS_ENDPOINT, timeout=min(self.timeout, 30))
        if a.status != 200 or not self._ours(a) or a.doc is None or a.doc.get("accepting") is not True:
            if a.doc is not None and self._ours(a):
                raise self._rejected(a)
            raise self._not_ours()
        return a.doc

    def _rejected(self, a: Answer, upload_bytes: Optional[int] = None) -> DeployFailed:
        doc = a.doc or {}
        code = doc.get("code")
        detail = str(doc.get("detail", ""))
        if code == "too-large":
            limit = int(doc.get("limitBytes") or 0)
            size = upload_bytes if upload_bytes is not None else int(doc.get("uploadBytes") or 0)
            return DeployFailed(f"site is {_human(size)}, the instance accepts {_human(limit)} (--max-upload-mb)", 1)
        if code == "out-of-space":
            return DeployFailed("instance is out of disk space; nothing changed", 3)
        if code in ("upload-incomplete", "upload-too-slow"):
            return DeployFailed(f"upload interrupted, nothing changed ({detail})", 3)
        if code == "busy":
            return DeployFailed("the instance is busy with another deploy and did not get free within the timeout "
                                f"({self.timeout:g} s); nothing changed", 3)
        if code == "no-site":
            return DeployFailed(f"the instance has no site at {doc.get('detail', '').rsplit(' ', 1)[-1]} "
                                "to roll back", 1)
        if code == "no-previous-release":
            return DeployFailed(f"nothing to roll back to: {detail}", 1)
        if code in ("invalid-site", "unsupported-schema"):
            errs = [str(e) for e in doc.get("errors") or []]
            return DeployFailed(f"the instance rejected the site ({len(errs)} problem(s)):", 1, errs)
        return DeployFailed(f"the instance refused the request ({a.status} {code}): {detail}", 1)

    def send(self, method: str, target: str, body: Optional[bytes], headers: dict[str, str]) -> dict[str, Any]:
        """Send, retrying a busy (409 with ``Retry-After``) answer until the timeout; the 200 answer's JSON."""
        deadline = time.monotonic() + self.timeout
        while True:
            left = deadline - time.monotonic()
            a = self.request(method, target, body, headers, timeout=self.timeout if body else max(left, 1.0))
            if a.status == 200 and self._ours(a) and a.doc is not None and a.doc.get("ok") is True:
                return a.doc
            if not self._ours(a):
                raise self._not_ours()
            if a.status == 409 and a.doc is not None and a.doc.get("code") == "busy":
                try:
                    wait = float(a.headers.get("retry-after", "5"))
                except ValueError:
                    wait = 5.0
                wait = min(max(wait, 0.1), 60.0)
                if time.monotonic() + wait >= deadline:
                    raise self._rejected(a, len(body) if body else None)
                self.out(f"the instance is busy with another deploy; trying again in {wait:g} s")
                time.sleep(wait)
                continue
            raise self._rejected(a, len(body) if body else None)


def _headers(extra: Optional[dict[str, str]] = None) -> dict[str, str]:
    h = {"X-Buildzr-Deploy": "1", "X-Buildzr-Version": VERSION}
    h.update(extra or {})
    return h


def _where(path: str) -> str:
    return f"path {path}" if path else "the root site"


def _short(h: Optional[str]) -> str:
    return (h[:19] + "…") if h else "none"


def _stderr(line: str) -> None:
    print(line, file=sys.stderr)


def deploy(site: str, url: str, path: str, timeout: float, dry_run: bool = False,
           out: Callable[[str], None] = print, warn: Callable[[str], None] = _stderr, shown: Optional[str] = None) -> int:
    """Pack ``site`` and upload it to the deploy address ``url`` as the site ``path``. Returns the exit code.

    ``shown`` is the folder name used in messages about the site's files (the user's ``--from`` folder)."""
    address = parse_address(url)
    if address.scheme == "https":
        warn(f"buildzr: warning: {url} uses https; the v1 deploy listener speaks plain http (use it through "
            "localhost or an SSH tunnel), so this will most likely fail")
    archive, files, size = pack_site(site, shown)
    target = DEPLOY_ENDPOINT + "?path=" + quote(path, safe="/")
    if dry_run:
        out(f"packed {files} files, {_human(size)} ({_human(len(archive))} compressed)")
        out(f"dry run: would upload {files} files, {_human(size)} to {address.url} ({_where(path)}); nothing was sent")
        return 0
    client = Client(address, timeout, out)
    st = client.status()
    limit = int((st.get("limits") or {}).get("maxUploadBytes") or 0)
    if limit and len(archive) > limit:
        raise DeployFailed(f"site is {_human(len(archive))}, the instance accepts {_human(limit)} (--max-upload-mb)", 1)
    out(f"uploading {files} files, {_human(size)} to {address.url} ({_where(path)})")
    doc = client.send("PUT", target, archive, _headers({"Content-Type": "application/gzip"}))
    shown = doc.get("path") or "/"
    if doc.get("unchanged"):
        out(f"unchanged {shown}: release {doc.get('release')} already has these files "
            f"(modelHash {_short(doc.get('modelHash'))})")
    else:
        prev = doc.get("previousModelHash")
        out(f"deployed {shown}: release {doc.get('release')}, modelHash {_short(doc.get('modelHash'))}"
            + (f" (previous {_short(prev)})" if prev else ""))
    out(f"open: {doc.get('viewerUrl')}")
    out(f"api:  {doc.get('apiUrl')}")
    return 0


def rollback(url: str, path: str, timeout: float, dry_run: bool = False, out: Callable[[str], None] = print) -> int:
    """Ask the instance at ``url`` to make the previous release of ``path`` current again. Returns the exit code."""
    address = parse_address(url)
    if dry_run:
        out(f"dry run: would roll back {_where(path)} at {address.url}; nothing was sent")
        return 0
    client = Client(address, timeout, out)
    client.status()
    doc = client.send("POST", ROLLBACK_ENDPOINT + "?path=" + quote(path, safe="/"), None,
                      _headers({"Content-Length": "0"}))
    out(f"rolled back {doc.get('path') or '/'}: release {doc.get('release')} is current again, modelHash "
        f"{_short(doc.get('modelHash'))} (was {_short(doc.get('previousModelHash'))})")
    out(f"open: {doc.get('viewerUrl')}")
    out(f"api:  {doc.get('apiUrl')}")
    return 0


def report(e: DeployFailed) -> int:
    """Print ``e`` as the CLI does and return its exit code."""
    print(f"buildzr: error: {e}", file=sys.stderr)
    for d in e.details:
        print(f"  {d}", file=sys.stderr)
    return e.code
