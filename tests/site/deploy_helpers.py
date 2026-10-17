"""Shared helpers of the deploy tests: valid sites that pass the checker, archives, and an instance in this process."""

from __future__ import annotations

import gzip
import hashlib
import http.client
import io
import json
import os
import shutil
import socket
import tarfile
import threading
from pathlib import Path
from typing import Any, Iterable, Optional

from buildzr.site import canonical
from buildzr.site.deploy import DEPLOY_ENDPOINT, make_deploy_server
from buildzr.site.deploy_client import pack_site
from buildzr.site.serve import make_store_server
from buildzr.site.store import Store

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
FIXTURE = os.path.join(ROOT, "tests", "site", "fixtures", "small")
Json = dict[str, Any]


def valid_site(dest: Path, n: int = 0, viewer: bool = True) -> Path:
    """A built site that passes ``check_site``: the small fixture as ``data/``, renamed to variant ``n`` (its own
    workspace name and so its own ``modelHash``), every file named with its hash like the real layout, ``build.json``
    and, with ``viewer``, a tiny viewer whose ``index.html`` refers to its ``assets/``."""
    data = dest / "data"
    shutil.copytree(FIXTURE, data)
    (data / "levels.json").unlink()
    index: Json = json.loads((data / "index.json").read_text())
    model: Json = json.loads((data / index["model"]["file"]).read_text())
    (data / index["model"]["file"]).unlink()
    model["workspace"]["name"] = f"Small v{n}"
    model["modelHash"] = canonical.model_hash(model)
    mh = model["modelHash"]
    mbytes = canonical.dumps(model).encode()
    mname = f"model.{hashlib.sha256(mbytes).hexdigest()[:8]}.json"
    (data / mname).write_bytes(mbytes)
    index["model"] = {"file": mname, "hash": "sha256:" + hashlib.sha256(mbytes).hexdigest()}
    for key, entry in index["scenes"].items():
        f = data / entry["file"]
        scene: Json = json.loads(f.read_text())
        f.unlink()
        scene["modelHash"] = mh
        sbytes = canonical.dumps(scene).encode()
        sh = hashlib.sha256(sbytes).hexdigest()
        rel = entry["file"][:-len(".json")] + "." + sh[:8] + ".json"
        (data / rel).write_bytes(sbytes)
        index["scenes"][key] = {"file": rel, "hash": "sha256:" + sh}
    index["modelHash"] = mh
    canonical.write(str(data / "index.json"), index)
    canonical.write(str(dest / "build.json"), {"buildzr": "0.0.35", "modelHash": mh})
    if viewer:
        (dest / "assets").mkdir()
        (dest / "assets" / "index-AbCdEf12.js").write_text("console.log('viewer')\n")
        (dest / "index.html").write_text('<!doctype html><script type="module" src="./assets/index-AbCdEf12.js">'
                                          "</script>\n")
    return dest


def model_hash(site: Path) -> str:
    h: str = json.loads((site / "build.json").read_text())["modelHash"]
    return h


def tgz(members: Iterable[tuple[tarfile.TarInfo, Optional[bytes]]], fmt: int = tarfile.USTAR_FORMAT) -> bytes:
    """A gzip-compressed tar of exactly these members (for hostile archives)."""
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=fmt) as tf:
        for info, data in members:
            tf.addfile(info, io.BytesIO(data) if data is not None else None)
    return gzip.compress(raw.getvalue(), mtime=0)


def member(name: str, data: Optional[bytes] = b"x", kind: bytes = tarfile.REGTYPE, **kw: Any) -> tuple[tarfile.TarInfo, Optional[bytes]]:
    info = tarfile.TarInfo(name)
    info.type = kind
    if kind == tarfile.REGTYPE and data is not None:
        info.size = len(data)
    else:
        data = None
    for k, v in kw.items():
        setattr(info, k, v)
    return info, data


def site_members(site: Path) -> list[tuple[tarfile.TarInfo, Optional[bytes]]]:
    """The members of a valid site as :func:`tgz` takes them (files only)."""
    out = []
    for d, _dirs, files in sorted(os.walk(site)):
        for f in sorted(files):
            full = os.path.join(d, f)
            out.append(member(os.path.relpath(full, site), Path(full).read_bytes()))
    return out


class Instance:
    """A store with its reading listener and its deploy listener, both in this process."""

    def __init__(self, store_dir: Path, **kw: Any) -> None:
        self.store = Store.open(str(store_dir), create=True, grace=kw.pop("grace", 0.0))
        self.reader = make_store_server(self.store, port=0)
        self.rport = self.reader.server_address[1]
        self.deployer = make_deploy_server(self.store, port=0, reader_base=f"http://127.0.0.1:{self.rport}", **kw)
        self.port = self.deployer.server_address[1]
        self.url = f"http://127.0.0.1:{self.port}"
        for s in (self.reader, self.deployer):
            threading.Thread(target=s.serve_forever, daemon=True).start()

    def close(self) -> None:
        for s in (self.deployer, self.reader):
            s.shutdown()
            s.server_close()

    def store_file(self) -> bytes:
        return (Path(self.store.dir) / "buildzr-store.json").read_bytes()

    def incoming(self) -> list[str]:
        return os.listdir(Path(self.store.dir) / "incoming")

    def log(self) -> list[Json]:
        p = Path(self.store.dir) / "deploys.log"
        return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def request(port: int, method: str, target: str, body: Optional[bytes] = None,
            headers: Optional[dict[str, str]] = None, timeout: float = 30) -> tuple[int, dict[str, str], Any]:
    """One request; the answer's JSON (or raw bytes when it is not JSON)."""
    conn = http.client.HTTPConnection("127.0.0.1", port, timeout=timeout)
    try:
        conn.request(method, target, body=body, headers=headers or {})
        r = conn.getresponse()
        data = r.read()
        hdrs = {k.lower(): v for k, v in r.getheaders()}
        try:
            return r.status, hdrs, json.loads(data)
        except ValueError:
            return r.status, hdrs, data
    finally:
        conn.close()


def deploy_headers(**extra: str) -> dict[str, str]:
    h = {"X-Buildzr-Deploy": "1", "X-Buildzr-Version": "0.0.36", "Content-Type": "application/gzip"}
    h.update(extra)
    return h


def put(port: int, body: bytes, path: str = "", **extra: str) -> tuple[int, dict[str, str], Any]:
    return request(port, "PUT", DEPLOY_ENDPOINT + "?path=" + path, body, deploy_headers(**extra))


def put_site(port: int, site: Path, path: str = "") -> tuple[int, dict[str, str], Any]:
    return put(port, pack_site(str(site))[0], path)


def raw(port: int, data: bytes, timeout: float = 10, shut: bool = True) -> bytes:
    """Send raw bytes on a new connection and read the whole answer (for requests http.client will not send)."""
    s = socket.create_connection(("127.0.0.1", port), timeout=timeout)
    try:
        s.sendall(data)
        if shut:
            s.shutdown(socket.SHUT_WR)
        out = b""
        while True:
            try:
                chunk = s.recv(65536)
            except (ConnectionResetError, socket.timeout):
                break
            if not chunk:
                break
            out += chunk
        return out
    finally:
        s.close()


def status_of(answer: bytes) -> int:
    return int(answer.split(b" ", 2)[1])
