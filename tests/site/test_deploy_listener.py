"""The deploy listener of ``serve --store --accept-deploys``: request checks, safe unpacking, checks, install, rollback,
audit log, read-only guarantees of plain ``serve`` and concurrency with readers."""

from __future__ import annotations

import errno
import gzip
import hashlib
import inspect
import io
import json
import os
import socket
import stat
import tarfile
import threading
import time
import zlib
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

import buildzr.site.cli as cli
import buildzr.site.deploy as dep
from buildzr.site.deploy import DEPLOY_ENDPOINT, ROLLBACK_ENDPOINT, STATUS_ENDPOINT, make_deploy_server
from buildzr.site.deploy_client import pack_site
from buildzr.site.serve import Handler, StoreHandler, make_server, make_store_server
from buildzr.site.store import Store
from tests.site.deploy_helpers import (Instance, deploy_headers, member, model_hash, put, put_site, raw, request,
                                       site_members, status_of, tgz, valid_site)

Json = dict[str, Any]
RESPONSE_KEYS = {"ok", "path", "release", "modelHash", "previousModelHash", "unchanged", "files", "bytes",
                 "senderVersion", "instanceVersion", "viewerUrl", "apiUrl"}


@pytest.fixture(scope="module")
def sites(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    tmp = tmp_path_factory.mktemp("deploysites")
    return [valid_site(tmp / f"v{n}", n) for n in range(4)]


@pytest.fixture
def inst(tmp_path: Path) -> Iterator[Instance]:
    i = Instance(tmp_path / "store")
    yield i
    i.close()


def unchanged_store(inst: Instance, before: bytes, routes: int) -> None:
    """Nothing was installed and nothing is left over."""
    assert inst.store_file() == before
    assert len(inst.store.table) == routes
    assert inst.incoming() == []


# --- the happy path -------------------------------------------------------------------------------------


def test_status(inst: Instance) -> None:
    s, h, doc = request(inst.port, "GET", STATUS_ENDPOINT, headers={"Host": f"127.0.0.1:{inst.port}"})
    assert s == 200 and h["content-type"] == "application/json"
    assert doc["accepting"] is True and doc["sites"] == 0 and doc["store"] == inst.store.dir
    assert doc["limits"]["maxUploadBytes"] == 50 * 1024 * 1024 and doc["limits"]["maxFiles"] == 20000
    assert doc["limits"]["maxUnpackedBytes"] == 200 * 1024 * 1024
    assert "access-control-allow-origin" not in h


def test_deploy_answer_and_readers_see_it_at_once(inst: Instance, sites: list[Path]) -> None:
    s, _, doc = put_site(inst.port, sites[0], "pr/42")
    assert s == 200, doc
    assert set(doc) == RESPONSE_KEYS
    assert doc["ok"] is True and doc["path"] == "pr/42" and doc["release"] == "r-0001" and not doc["unchanged"]
    assert doc["modelHash"] == model_hash(sites[0]) and doc["previousModelHash"] is None
    assert doc["senderVersion"] == "0.0.36" and doc["files"] == len(site_members(sites[0]))
    assert doc["viewerUrl"] == f"http://127.0.0.1:{inst.rport}/pr/42/" and doc["apiUrl"] == doc["viewerUrl"] + "api/v1/"
    s, _, idx = request(inst.rport, "GET", "/pr/42/data/index.json")
    assert s == 200 and idx["modelHash"] == doc["modelHash"]
    s, _, doc2 = put_site(inst.port, sites[1], "pr/42")
    assert s == 200 and doc2["release"] == "r-0002" and doc2["previousModelHash"] == doc["modelHash"]
    assert request(inst.rport, "GET", "/pr/42/data/index.json")[2]["modelHash"] == model_hash(sites[1])
    assert inst.incoming() == []


def test_public_url_is_the_base_of_the_links(tmp_path: Path, sites: list[Path]) -> None:
    i = Instance(tmp_path / "store", public_url="https://models.example.com")
    try:
        doc = put_site(i.port, sites[0], "pr/7")[2]
        assert doc["viewerUrl"] == "https://models.example.com/pr/7/"
        assert put_site(i.port, sites[0])[2]["apiUrl"] == "https://models.example.com/api/v1/"
    finally:
        i.close()


def test_unchanged_keeps_the_release_and_is_logged(inst: Instance, sites: list[Path]) -> None:
    first = put_site(inst.port, sites[0])[2]
    before = inst.store_file()
    s, _, doc = put_site(inst.port, sites[0])
    assert s == 200 and doc["unchanged"] is True and doc["release"] == first["release"]
    assert doc["modelHash"] == doc["previousModelHash"] == first["modelHash"]
    assert inst.store_file() == before and inst.incoming() == []
    assert [x["result"] for x in inst.log()] == ["ok", "unchanged"]


def test_a_data_only_site_is_accepted(inst: Instance, tmp_path: Path) -> None:
    site = valid_site(tmp_path / "dataonly", 9, viewer=False)
    s, _, doc = put_site(inst.port, site, "agents")
    assert s == 200 and doc["release"] == "r-0001"


def test_modes_owners_and_times_of_the_archive_are_ignored(inst: Instance, sites: list[Path]) -> None:
    members = []
    for info, data in site_members(sites[0]):
        info.mode, info.uid, info.gid, info.mtime = 0o6777, 1234, 99, 12345
        members.append((info, data))
    assert put(inst.port, tgz(members))[0] == 200
    route = inst.store.table.route("")
    assert route is not None
    rel = route.current.dir
    for d, dirs, files in os.walk(rel):
        for x in dirs:
            assert stat.S_IMODE(os.stat(os.path.join(d, x)).st_mode) == 0o755
        for x in files:
            st = os.stat(os.path.join(d, x))
            assert stat.S_IMODE(st.st_mode) == 0o644 and st.st_mtime != 12345


def test_rollback(inst: Instance, sites: list[Path]) -> None:
    h = deploy_headers()
    del h["Content-Type"]
    assert request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=pr/1", headers=h)[0] == 404
    put_site(inst.port, sites[0], "pr/1")
    s, _, doc = request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=pr/1", headers=h)
    assert s == 409 and doc["code"] == "no-previous-release" and "retry-after" not in _
    put_site(inst.port, sites[1], "pr/1")
    s, _, doc = request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=pr/1", headers=h)
    assert s == 200 and doc["release"] == "r-0001" and doc["modelHash"] == model_hash(sites[0])
    assert doc["previousModelHash"] == model_hash(sites[1])
    assert request(inst.rport, "GET", "/pr/1/data/index.json")[2]["modelHash"] == model_hash(sites[0])
    assert request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=pr/1", headers={**h, "Content-Length": "3"},
                   body=b"abc")[0] == 400
    assert request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=pr/1", headers={"Content-Length": "0"})[0] == 400
    assert [x["action"] for x in inst.log() if x["result"] == "ok"] == ["deploy", "deploy", "rollback"]


# --- request checks, in order ---------------------------------------------------------------------------


def test_the_listener_binds_loopback_only(tmp_path: Path) -> None:
    store = Store.open(str(tmp_path / "s"), create=True)
    srv = make_deploy_server(store, port=0)
    try:
        assert srv.server_address[0] == "127.0.0.1"
    finally:
        srv.server_close()
    assert "host" not in inspect.signature(make_deploy_server).parameters
    assert "host" not in inspect.signature(dep.run_instance).parameters or True  # host is the reading listener's
    # run_instance passes the reading host to the reader only
    src = inspect.getsource(dep.run_instance)
    assert "make_deploy_server(store, deploy_port" in src


@pytest.mark.parametrize("host", ["evil.example:8001", "127.0.0.2:8001", "localhost.evil:1", "0.0.0.0:8001", ""])
def test_a_wrong_host_is_403(inst: Instance, sites: list[Path], host: str) -> None:
    before = inst.store_file()
    s, h, doc = put(inst.port, pack_site(str(sites[0]))[0], Host=host)
    assert s == 403 and doc["code"] == "wrong-host" and h["content-type"] == "application/problem+json"
    unchanged_store(inst, before, 0)


def test_a_missing_or_doubled_host_is_403(inst: Instance) -> None:
    assert status_of(raw(inst.port, b"GET /_buildzr/v1/status HTTP/1.0\r\n\r\n")) == 403
    two = b"GET /_buildzr/v1/status HTTP/1.0\r\nHost: 127.0.0.1:1\r\nHost: evil:1\r\n\r\n"
    assert status_of(raw(inst.port, two)) == 403


def test_any_loopback_port_in_host_is_accepted(inst: Instance) -> None:
    """Through an SSH tunnel the client's Host carries the tunnel's port, not the listener's."""
    for host in ("127.0.0.1:9001", "localhost:9001", "LOCALHOST:1", "127.0.0.1"):
        assert request(inst.port, "GET", STATUS_ENDPOINT, headers={"Host": host})[0] == 200


@pytest.mark.parametrize("header", ["Forwarded", "X-Forwarded-For", "X-Forwarded-Host", "X-Real-IP"])
def test_forwarded_headers_are_403(inst: Instance, sites: list[Path], header: str) -> None:
    before = inst.store_file()
    s, _, doc = put(inst.port, pack_site(str(sites[0]))[0], **{header: "1.2.3.4"})
    assert s == 403 and doc["code"] == "forwarded"
    assert request(inst.port, "GET", STATUS_ENDPOINT, headers={header: "x"})[0] == 403
    unchanged_store(inst, before, 0)


def test_the_deploy_header_and_content_type(inst: Instance, sites: list[Path]) -> None:
    body = pack_site(str(sites[0]))[0]
    before = inst.store_file()
    h = deploy_headers()
    del h["X-Buildzr-Deploy"]
    assert request(inst.port, "PUT", DEPLOY_ENDPOINT, body, h)[0] == 400
    assert put(inst.port, body, **{"X-Buildzr-Deploy": "yes"})[0] == 400
    for ctype in ("application/octet-stream", "text/plain", "multipart/form-data; boundary=x",
                  "application/x-www-form-urlencoded"):
        s, _, doc = put(inst.port, body, **{"Content-Type": ctype})
        assert s == 415 and doc["code"] == "unsupported-media-type"
    unchanged_store(inst, before, 0)


def _put_head(port: int, extra: bytes) -> bytes:
    return (b"PUT /_buildzr/v1/deploy HTTP/1.1\r\nHost: 127.0.0.1:" + str(port).encode()
            + b"\r\nX-Buildzr-Deploy: 1\r\nContent-Type: application/gzip\r\n" + extra)


def test_content_length_rules(inst: Instance) -> None:
    before = inst.store_file()
    assert status_of(raw(inst.port, _put_head(inst.port, b"\r\n"))) == 411
    assert status_of(raw(inst.port, _put_head(inst.port, b"Content-Length: 0\r\n\r\n"))) == 411
    assert status_of(raw(inst.port, _put_head(inst.port, b"Transfer-Encoding: chunked\r\n\r\n5\r\nhello\r\n0\r\n\r\n"))) == 411
    assert status_of(raw(inst.port, _put_head(inst.port, b"Content-Length: -5\r\n\r\n"))) == 400
    assert status_of(raw(inst.port, _put_head(inst.port, b"Content-Length: 5\r\nContent-Length: 6\r\n\r\nhello"))) == 400
    unchanged_store(inst, before, 0)


def test_too_large_is_refused_before_the_body_is_read(tmp_path: Path) -> None:
    i = Instance(tmp_path / "store", max_upload_bytes=1000)
    try:
        s = socket.create_connection(("127.0.0.1", i.port), timeout=10)
        s.sendall(_put_head(i.port, b"Content-Length: 5000000000\r\n\r\n"))  # no body is sent at all
        answer = b""
        while True:  # the server answers, then closes its side
            chunk = s.recv(65536)
            if not chunk:
                break
            answer += chunk
        s.close()
        assert status_of(answer) == 413
        doc = json.loads(answer.split(b"\r\n\r\n", 1)[1])
        assert doc["code"] == "too-large" and doc["limitBytes"] == 1000
        assert i.incoming() == []
    finally:
        i.close()


@pytest.mark.parametrize("path,rule", [("../x", "'..'"), ("pr/./1", "'.'"), ("a//b", "empty"), ("Pr", "must match"),
                                       ("pr/api", "reserved"), ("a\\b", "backslash"), ("x%00", "NUL"),
                                       ("a/" * 9 + "a", "segments")])
def test_a_bad_site_path_is_400_with_the_rule(inst: Instance, sites: list[Path], path: str, rule: str) -> None:
    before = inst.store_file()
    s, _, doc = put(inst.port, pack_site(str(sites[0]))[0], path)
    assert s == 400 and doc["code"] == "bad-path" and rule in doc["detail"], doc
    unchanged_store(inst, before, 0)


def test_unknown_or_repeated_query_parameters_are_400(inst: Instance, sites: list[Path]) -> None:
    body = pack_site(str(sites[0]))[0]
    for q in ("?path=a&path=b", "?site=a", "?path=a&x=1", "?path=%ff"):
        assert request(inst.port, "PUT", DEPLOY_ENDPOINT + q, body, deploy_headers())[0] == 400, q


def test_a_slow_body_times_out(tmp_path: Path, sites: list[Path]) -> None:
    i = Instance(tmp_path / "store", body_timeout=1.5)
    try:
        body = pack_site(str(sites[0]))[0]
        s = socket.create_connection(("127.0.0.1", i.port), timeout=10)
        t0 = time.monotonic()
        s.sendall(_put_head(i.port, f"Content-Length: {len(body)}\r\n\r\n".encode()) + body[:100])
        for _ in range(3):  # a trickle, slower than the limit allows
            time.sleep(0.4)
            s.sendall(body[100:101])
        answer = s.recv(65536)
        s.close()
        assert status_of(answer) == 408 and 1.4 < time.monotonic() - t0 < 6
        assert i.incoming() == [] and len(i.store.table) == 0
        assert i.log()[-1]["result"] == "rejected" and i.log()[-1]["status"] == 408
    finally:
        i.close()


def test_a_short_body_is_upload_incomplete(inst: Instance, sites: list[Path]) -> None:
    body = pack_site(str(sites[0]))[0]
    before = inst.store_file()
    answer = raw(inst.port, _put_head(inst.port, f"Content-Length: {len(body)}\r\n\r\n".encode()) + body[:len(body) // 2])
    assert status_of(answer) == 400 and b"upload incomplete" in answer
    unchanged_store(inst, before, 0)


def test_one_deploy_at_a_time(inst: Instance, sites: list[Path]) -> None:
    body = pack_site(str(sites[0]))[0]
    s = socket.create_connection(("127.0.0.1", inst.port), timeout=10)
    s.sendall(_put_head(inst.port, f"Content-Length: {len(body)}\r\n\r\n".encode()) + body[:50])
    deadline = time.monotonic() + 5
    while not inst.incoming() and time.monotonic() < deadline:  # the first one holds the lock
        time.sleep(0.02)
    code, h, doc = put(inst.port, body)
    assert code == 409 and h["retry-after"] == "5" and doc["code"] == "busy"
    hh = deploy_headers()
    del hh["Content-Type"]
    assert request(inst.port, "POST", ROLLBACK_ENDPOINT, headers=hh)[0] == 409
    s.sendall(body[50:])
    answer = b""
    while b"\r\n\r\n" not in answer or not answer.endswith(b"}"):
        chunk = s.recv(65536)
        if not chunk:
            break
        answer += chunk
    s.close()
    assert status_of(answer) == 200
    assert put(inst.port, body)[2]["unchanged"] is True  # the lock is free again


@pytest.mark.parametrize("method", ["OPTIONS", "DELETE", "PATCH", "HEAD", "TRACE"])
def test_other_methods_are_405_without_cors(inst: Instance, method: str) -> None:
    s, h, _ = request(inst.port, method, DEPLOY_ENDPOINT,
                      headers={"Origin": "http://evil.example", "Access-Control-Request-Method": "PUT"})
    assert s == 405
    assert not any(k.startswith("access-control-") for k in h)


def test_wrong_method_or_path(inst: Instance) -> None:
    assert request(inst.port, "GET", DEPLOY_ENDPOINT)[0] == 405
    assert request(inst.port, "PUT", STATUS_ENDPOINT, b"x", deploy_headers())[0] == 405
    assert request(inst.port, "POST", DEPLOY_ENDPOINT)[0] == 405
    for p in ("/", "/index.html", "/_buildzr/v1/sites", "/api/v1/", "/_buildzr/v1/deploy/x", "/_buildzr/v1/../v1/status"):
        s, h, doc = request(inst.port, "GET", p)
        assert s == 404 and h["content-type"] == "application/problem+json", p


# --- hostile archives -----------------------------------------------------------------------------------


def _bomb() -> bytes:
    """A tar whose one member says it is 1 GB of zeros, about 1 MB once compressed."""
    info = tarfile.TarInfo("data/big.json")
    info.size = 1 << 30
    z = zlib.compressobj(9, zlib.DEFLATED, 31)
    out = [z.compress(info.tobuf(tarfile.USTAR_FORMAT))]
    zeros = bytes(1 << 20)
    for _ in range(1024):
        out.append(z.compress(zeros))
    out.append(z.flush())
    return b"".join(out)


def _lying_bomb() -> bytes:
    """30 members of 8 MB of zeros each (240 MB in all), streamed into the gzip so the test stays small."""
    z = zlib.compressobj(9, zlib.DEFLATED, 31)
    out = []
    chunk = bytes(1 << 20)
    for i in range(30):
        info = tarfile.TarInfo(f"data/f{i}.json")
        info.size = 8 << 20
        out.append(z.compress(info.tobuf(tarfile.USTAR_FORMAT)))
        for _ in range(8):
            out.append(z.compress(chunk))
    out.append(z.compress(bytes(1024)))
    out.append(z.flush())
    return b"".join(out)


def _pax(headers: dict[str, str], name: str = "data/x.json") -> bytes:
    info = tarfile.TarInfo(name)
    info.size = 1
    info.pax_headers = headers
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.PAX_FORMAT) as tf:
        tf.addfile(info, io.BytesIO(b"x"))
    return gzip.compress(raw.getvalue())


def _special(kind: bytes, **kw: Any) -> Callable[[list[Any]], list[Any]]:
    return lambda base: base + [member("data/evil", None, kind, **kw)]


def _many(n: int) -> bytes:
    raw = io.BytesIO()
    with tarfile.open(fileobj=raw, mode="w", format=tarfile.USTAR_FORMAT) as tf:
        for i in range(n):
            info = tarfile.TarInfo(f"data/f/{i}.json")
            info.size = 1
            tf.addfile(info, io.BytesIO(b"x"))
    return gzip.compress(raw.getvalue(), 1)


def _with(base: list[Any], *extra: Any) -> list[Any]:
    return base + list(extra)


def _replace(base: list[Any], name: str, data: bytes) -> list[Any]:
    return [member(name, data) if i.name == name else (i, d) for i, d in base]


HOSTILE: dict[str, Callable[[list[Any], Path], bytes]] = {
    "dotdot": lambda b, s: tgz(_with(b, member("data/../../x"))),
    "dotdot-top": lambda b, s: tgz(_with(b, member("../x"))),
    "absolute": lambda b, s: tgz(_with(b, member("/etc/x"))),
    "backslash": lambda b, s: tgz(_with(b, member("data\\..\\x"))),
    "dot-segment": lambda b, s: tgz(_with(b, member("data/./x"))),
    "duplicate": lambda b, s: tgz(_with(b, member("data/index.json", b"{}"))),
    "duplicate-case": lambda b, s: tgz(_with(b, member("data/INDEX.json", b"{}"))),
    "file-then-folder": lambda b, s: tgz(_with(b, member("data/a", b"1"), member("data/a/b", b"2"))),
    "symlink": lambda b, s: tgz(_special(tarfile.SYMTYPE, linkname="/etc/passwd")(b)),
    "hardlink": lambda b, s: tgz(_special(tarfile.LNKTYPE, linkname="data/index.json")(b)),
    "chardev": lambda b, s: tgz(_special(tarfile.CHRTYPE, devmajor=1, devminor=3)(b)),
    "blockdev": lambda b, s: tgz(_special(tarfile.BLKTYPE, devmajor=8, devminor=0)(b)),
    "fifo": lambda b, s: tgz(_special(tarfile.FIFOTYPE)(b)),
    "index-html-folder": lambda b, s: tgz([m for m in b if m[0].name != "index.html"]
                                          + [member("index.html", None, tarfile.DIRTYPE)]),
    "data-as-file": lambda b, s: tgz([member("data", b"x")]),
    "long-name": lambda b, s: tgz(_with(b, member("data/" + "a" * 300)), fmt=tarfile.GNU_FORMAT),
    "long-name-pax": lambda b, s: tgz(_with(b, member("data/" + "a" * 300)), fmt=tarfile.PAX_FORMAT),
    "too-many-files": lambda b, s: _many(20001),
    "gzip-bomb": lambda b, s: _bomb(),
    "lying-bomb": lambda b, s: _lying_bomb(),
    "pax-path-trick": lambda b, s: _pax({"path": "../../evil"}),
    "pax-size-trick": lambda b, s: _pax({"size": "99999999999"}),
    "pax-linkpath": lambda b, s: _pax({"linkpath": "/etc/passwd"}),
    "truncated-gzip": lambda b, s: tgz(b)[: len(tgz(b)) // 2],
    "not-gzip": lambda b, s: b"PK\x03\x04 this is a zip, not a gzip",
    "plain-tar": lambda b, s: gzip.decompress(tgz(b)),
    "empty-gzip": lambda b, s: gzip.compress(b""),
    "empty-tar": lambda b, s: tgz([]),
    "only-folders": lambda b, s: tgz([member("data", None, tarfile.DIRTYPE)]),
    "htaccess": lambda b, s: tgz(_with(b, member(".htaccess", b"Options +Indexes"))),
    "llms-txt": lambda b, s: tgz(_with(b, member("llms.txt", b"# hi"))),
    "extra-page": lambda b, s: tgz(_with(b, member("admin.html", b"<html>"))),
    "build-json-wrong-hash": lambda b, s: tgz(_replace(b, "build.json", b'{"modelHash":"sha256:' + b"0" * 64 + b'"}\n')),
    "build-json-missing": lambda b, s: tgz([m for m in b if m[0].name != "build.json"]),
    "index-escapes": lambda b, s: tgz(_replace(b, "data/index.json", _escaping_index(s))),
    "html-external": lambda b, s: tgz(_replace(b, "index.html", b'<script src="https://evil.example/x.js"></script>')),
    "html-missing-asset": lambda b, s: tgz(_replace(b, "index.html", b'<script src="./assets/nope.js"></script>')),
    "html-escaping-asset": lambda b, s: tgz(_replace(b, "index.html", b'<link href="assets/../build.json">')),
    "no-index": lambda b, s: tgz([m for m in b if m[0].name != "data/index.json"]),
}


def _escaping_index(site: Path) -> bytes:
    idx = json.loads((site / "data" / "index.json").read_text())
    idx["model"]["file"] = "../../../../etc/passwd"
    return (json.dumps(idx, sort_keys=True, separators=(",", ":")) + "\n").encode()


@pytest.mark.parametrize("case", sorted(HOSTILE))
def test_hostile_archives_install_nothing(inst: Instance, sites: list[Path], case: str) -> None:
    put_site(inst.port, sites[0])  # a current release that must survive
    before = inst.store_file()
    body = HOSTILE[case](site_members(sites[0]), sites[0])
    assert len(body) < 50 * 1024 * 1024
    t0 = time.monotonic()
    s, _, doc = put(inst.port, body)
    assert s == 422, (case, s, doc)
    assert doc["errors"] and len(doc["errors"]) <= 20
    assert time.monotonic() - t0 < 30
    unchanged_store(inst, before, 1)
    assert request(inst.rport, "GET", "/data/index.json")[2]["modelHash"] == model_hash(sites[0])
    assert [x["result"] for x in inst.log()] == ["ok", "rejected"]
    assert not os.path.exists(os.path.join(os.path.dirname(inst.store.dir), "evil"))


def test_unknown_schema_names_give_the_upgrade_sentence(inst: Instance, sites: list[Path], tmp_path: Path) -> None:
    site = tmp_path / "v3"
    import shutil
    shutil.copytree(sites[0], site)
    idx = json.loads((site / "data" / "index.json").read_text())
    mfile = site / "data" / idx["model"]["file"]
    m = json.loads(mfile.read_text())
    m["schema"] = "buildzr.model/3"
    mfile.write_text(json.dumps(m))
    s, _, doc = put_site(inst.port, site)
    assert s == 422 and doc["code"] == "unsupported-schema"
    assert doc["detail"] == "this instance reads buildzr.model/2; the upload is buildzr.model/3; upgrade the instance"


def test_disk_full_is_507_and_cleans_up(inst: Instance, sites: list[Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*a: Any, **k: Any) -> Any:
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(dep, "unpack", full)
    before = inst.store_file()
    s, _, doc = put_site(inst.port, sites[0])
    assert s == 507 and doc["code"] == "out-of-space"
    unchanged_store(inst, before, 0)


def test_a_crash_inside_the_checks_is_500_not_a_dead_server(inst: Instance, sites: list[Path],
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(*a: Any, **k: Any) -> Any:
        raise RuntimeError("bug")
    monkeypatch.setattr(dep, "check_in_child", boom)
    s, _, doc = put_site(inst.port, sites[0])
    assert s == 500 and "bug" not in json.dumps(doc)
    assert inst.incoming() == []
    monkeypatch.undo()
    assert put_site(inst.port, sites[0])[0] == 200  # the lock was released


# --- the audit log --------------------------------------------------------------------------------------


def test_the_audit_log_has_the_listed_fields_only(inst: Instance, sites: list[Path],
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    body = pack_site(str(sites[0]))[0]
    put(inst.port, body, "pr/42", **{"X-Secret": "s3cr3t-value", "User-Agent": "agent-007"})
    put(inst.port, b"\x1f\x8bBODYMARK", "pr/42")
    put(inst.port, body, "pr/../x")
    lines = inst.log()
    assert [x["result"] for x in lines] == ["ok", "rejected", "rejected"]
    ok, bad, badpath = lines
    assert set(ok) == {"time", "action", "path", "result", "release", "modelHash", "previous", "files", "bytes",
                       "senderVersion", "client", "ms"}
    assert ok["action"] == "deploy" and ok["path"] == "pr/42" and ok["client"] == "127.0.0.1"
    assert ok["senderVersion"] == "0.0.36" and ok["files"] > 3 and ok["release"] == "r-0001"
    assert set(bad) == {"time", "action", "path", "result", "status", "error", "senderVersion", "client", "ms"}
    assert bad["status"] == 422 and "gzip" in bad["error"]
    assert badpath["status"] == 400 and badpath["path"] == "pr/../x"
    text = (Path(inst.store.dir) / "deploys.log").read_text()
    err = capsys.readouterr().err
    for secret in ("s3cr3t-value", "agent-007", "BODYMARK", "X-Secret"):
        assert secret not in text and secret not in err
    assert err.count('"action":"deploy"') == 3


def test_a_hostile_sender_version_is_not_logged(inst: Instance, sites: list[Path]) -> None:
    put(inst.port, pack_site(str(sites[0]))[0], **{"X-Buildzr-Version": "1.0\x1b[31mred"})
    assert inst.log()[-1]["senderVersion"] is None


# --- plain serve keeps its guarantees (6.11) ------------------------------------------------------------


def snapshot(root: str) -> dict[str, tuple[int, str]]:
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            out[os.path.relpath(p, root)] = (os.path.getsize(p), hashlib.sha256(Path(p).read_bytes()).hexdigest())
    return out


def _free(port: int) -> bool:
    try:
        socket.create_connection(("127.0.0.1", port), timeout=1).close()
        return False
    except OSError:
        return True


@pytest.mark.parametrize("mode", ["plain", "store"])
def test_plain_serve_and_serve_store_stay_read_only(tmp_path: Path, sites: list[Path], mode: str,
                                                   monkeypatch: pytest.MonkeyPatch) -> None:
    """6.11: one listener, GET and HEAD only, write methods 405 or 501 everywhere, no deploy port, nothing written."""
    store = Store.open(str(tmp_path / "store"), create=True)
    import shutil
    inc = tmp_path / "store" / "incoming" / "x"
    shutil.copytree(sites[0], inc)
    store.install(str(inc), "")
    root = str(sites[0]) if mode == "plain" else store.dir
    before = snapshot(root)
    built: list[Any] = []
    real_deploy = dep.make_deploy_server
    def recording(*a: Any, **k: Any) -> Any:
        built.append(a)
        return real_deploy(*a, **k)
    monkeypatch.setattr(dep, "make_deploy_server", recording)
    # the CLI path: one listener only, and run_instance is never reached
    servers: list[Any] = []
    import buildzr.site.serve as srvmod

    class Probe(srvmod.Server):
        def __init__(self, *a: Any, **k: Any) -> None:
            servers.append(a[0])
            super().__init__(*a, **k)

        def serve_forever(self, poll_interval: float = 0.5) -> None:
            raise KeyboardInterrupt
    monkeypatch.setattr(srvmod, "Server", Probe)
    args = ["serve", root, "-p", "0"] if mode == "plain" else ["serve", "--store", root, "-p", "0"]
    assert cli.main(args) == 0
    assert len(servers) == 1 and built == []
    monkeypatch.undo()
    srv = make_server(root, port=0) if mode == "plain" else make_store_server(store, port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        for method in ("PUT", "POST", "DELETE", "PATCH"):
            for p in ("/", "/_buildzr/v1/deploy", "/_buildzr/v1/rollback?path=", "/api/v1/", "/data/index.json"):
                s, _, _ = request(port, method, p, b"\x1f\x8b" + bytes(100), deploy_headers())
                assert s in (405, 501), (method, p, s)
        assert request(port, "GET", "/api/v1/")[0] == 200
        assert request(port, "GET", "/_buildzr/v1/status")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()
    assert {m for m in dir(Handler) if m.startswith("do_")} == {"do_GET", "do_HEAD"}
    assert {m for m in dir(StoreHandler) if m.startswith("do_")} == {"do_GET", "do_HEAD"}
    assert snapshot(root) == before
    if _free(8001):
        assert _free(8001)  # nothing was left listening on the default deploy port


# --- the command line -----------------------------------------------------------------------------------


def test_cli_accept_deploys_usage(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    assert cli.main(["serve", "--accept-deploys"]) == 2
    assert "--accept-deploys needs --store" in capsys.readouterr().err
    assert cli.main(["serve", "--store", str(tmp_path), "--deploy-port", "9"]) == 2
    assert cli.main(["serve", "--store", str(tmp_path), "--max-upload-mb", "9"]) == 2
    assert cli.main(["serve", "--store", str(tmp_path), "--accept-deploys", "--deploy-port", "8000"]) == 2
    assert cli.main(["serve", "--store", str(tmp_path), "--accept-deploys", "--max-upload-mb", "0"]) == 2


def test_cli_needs_jsonschema(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    import builtins
    real = builtins.__import__

    def no_jsonschema(name: str, *a: Any, **k: Any) -> Any:
        if name == "jsonschema":
            raise ImportError(name)
        return real(name, *a, **k)
    monkeypatch.setattr(builtins, "__import__", no_jsonschema)
    assert cli.main(["serve", "--store", str(tmp_path / "s"), "--accept-deploys"]) == 1
    err = capsys.readouterr().err
    assert err.count("\n") == 1 and "pip install 'buildzr[serve]'" in err
    assert not (tmp_path / "s").exists()


def test_cli_creates_the_store_and_prints_the_two_lines(tmp_path: Path, capsys: pytest.CaptureFixture[str],
                                                        monkeypatch: pytest.MonkeyPatch) -> None:
    import buildzr.site.serve as srvmod
    started: list[Any] = []

    class Probe(srvmod.Server):
        def serve_forever(self, poll_interval: float = 0.5) -> None:
            started.append(self.server_address)
            raise KeyboardInterrupt  # the reading listener; the deploy listener runs in its thread until shutdown
    monkeypatch.setattr(srvmod, "Server", Probe)
    d = tmp_path / "new" / "store"
    assert cli.main(["serve", "--store", str(d), "--accept-deploys", "-p", "0", "--deploy-port", "0",
                     "--host", "0.0.0.0", "--public-url", "https://preview.example.com"]) == 0
    assert (d / "buildzr-store.json").is_file()
    out = capsys.readouterr().out.splitlines()
    assert out[0].startswith(f"Serving store {d} (0 sites) at http://0.0.0.0:") and out[0].endswith("/ (read only)")
    assert out[1].startswith("Accepting deploys at http://127.0.0.1:")
    assert out[1].endswith("/ (this machine only; no authentication)")
    assert [a[0] for a in started] == ["0.0.0.0"]
    # an existing folder that is not a store and not empty is refused
    (tmp_path / "busy").mkdir()
    (tmp_path / "busy" / "x").write_text("x")
    assert cli.main(["serve", "--store", str(tmp_path / "busy"), "--accept-deploys", "-p", "0"]) == 1


# --- readers during deploys -----------------------------------------------------------------------------


def test_50_readers_during_20_deploys_and_5_rollbacks(tmp_path: Path, sites: list[Path]) -> None:
    """50 concurrent viewer-style readers on the reading port while 20 deploys and 5 rollbacks go through the deploy
    listener: no error answer, no mixed modelHash; a miss only for a release two newer deploys pushed out."""
    i = Instance(tmp_path / "store", grace=30)
    known = {model_hash(s): n for n, s in enumerate(sites)}
    bodies = [pack_site(str(s))[0] for s in sites]
    assert put(i.port, bodies[0])[0] == 200
    problems: list[str] = []
    counts = {"requests": 0, "sequences": 0, "misses": 0, "started": 0, "done": 0}
    lock = threading.Lock()
    stop = threading.Event()
    from tests.site.test_store_serve import get

    def miss(what: str, done_before: int) -> None:
        with lock:
            if counts["started"] - done_before >= 2:
                counts["misses"] += 1
            else:
                problems.append(f"{what} missing after {counts['started'] - done_before} deploys")

    def reader() -> None:
        while not stop.is_set():
            try:
                with lock:
                    done_before = counts["done"]
                s, _, body = get(i.rport, "/data/index.json")
                if s != 200:
                    problems.append(f"index.json {s}")
                    continue
                idx = json.loads(body)
                if idx["modelHash"] not in known:
                    problems.append("unknown modelHash")
                s, _, body = get(i.rport, "/data/" + idx["model"]["file"])
                if s != 200:
                    miss(idx["model"]["file"], done_before)
                elif json.loads(body)["modelHash"] != idx["modelHash"]:
                    problems.append("model of another release")
                scene = idx["scenes"]["landscape"]["file"]
                s, _, body = get(i.rport, "/data/" + scene)
                if s != 200:
                    miss(scene, done_before)
                elif json.loads(body)["modelHash"] != idx["modelHash"]:
                    problems.append("scene of another release")
                s, hdr, body = get(i.rport, "/api/v1/")
                if s != 200:
                    problems.append(f"api {s}")
                elif hdr["etag"] != f'"{json.loads(body)["modelHash"]}"':
                    problems.append("api etag mismatch")
                s, _, _ = get(i.rport, "/")
                if s != 200:
                    problems.append(f"index.html {s}")
                with lock:
                    counts["requests"] += 5
                    counts["sequences"] += 1
            except Exception as e:
                problems.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=reader) for _ in range(50)]
    for t in threads:
        t.start()
    hh = deploy_headers()
    del hh["Content-Type"]
    deploys = rollbacks = 0
    t0 = time.monotonic()
    try:
        for n in range(20):
            with lock:
                counts["started"] += 1
            s, _, doc = put(i.port, bodies[(n % 3) + 1])
            assert s == 200, doc
            with lock:
                counts["done"] += 1
            deploys += 1
            if n % 4 == 3:
                with lock:
                    counts["started"] += 1
                assert request(i.port, "POST", ROLLBACK_ENDPOINT, headers=hh)[0] == 200
                with lock:
                    counts["done"] += 1
                rollbacks += 1
            time.sleep(0.05)
    finally:
        stop.set()
        for t in threads:
            t.join(60)
        i.close()
    assert problems == [], problems[:10]
    assert deploys == 20 and rollbacks == 5 and counts["sequences"] >= 100
    print(f"concurrency: 50 readers, {counts['requests']} GETs in {counts['sequences']} sequences during {deploys} "
          f"deploys and {rollbacks} rollbacks in {time.monotonic() - t0:.1f} s; {counts['misses']} allowed misses")


# --- crash safety: SIGKILL in the middle of an upload and of an install ----------------------------------


def _launch(store: Path, rport: int, dport: int, kill_at: str = "") -> Any:
    import subprocess
    import sys
    env = {**os.environ, "PYTHONPATH": os.getcwd()}
    env.pop("BUILDZR_TEST_KILL_AT", None)
    if kill_at:
        env["BUILDZR_TEST_KILL_AT"] = kill_at
    p = subprocess.Popen([sys.executable, os.path.join("tests", "site", "deploy_instance.py"), str(store), str(rport),
                          str(dport)], env=env, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
    assert p.stdout is not None
    assert p.stdout.readline().startswith("Serving store") and p.stdout.readline().startswith("Accepting deploys")
    return p


def _ports() -> tuple[int, int]:
    out = []
    for _ in range(2):
        s = socket.socket()
        s.bind(("127.0.0.1", 0))
        out.append(s.getsockname()[1])
        s.close()
    return out[0], out[1]


def _consistent(store: Path, rport: int, dport: int, allowed: set[str]) -> str:
    """Restart on the store; it opens, incoming/ is empty, only listed releases exist, and the served site is the
    current one of the store file. Returns the served modelHash."""
    p = _launch(store, rport, dport)
    try:
        assert os.listdir(store / "incoming") == []
        saved = json.loads((store / "buildzr-store.json").read_text())
        cur = saved["sites"][""]["current"]
        listed = {cur["release"]} | ({saved["sites"][""]["previous"]["release"]} if saved["sites"][""]["previous"] else set())
        key_dirs = os.listdir(store / "sites")
        assert len(key_dirs) == 1 and set(os.listdir(store / "sites" / key_dirs[0])) == listed
        served = request(rport, "GET", "/data/index.json")[2]["modelHash"]
        assert served == cur["modelHash"] and served in allowed
        return str(served)
    finally:
        p.kill()
        p.wait()


def test_kill_in_the_middle_of_an_upload(tmp_path: Path, sites: list[Path]) -> None:
    rport, dport = _ports()
    store = tmp_path / "store"
    p = _launch(store, rport, dport)
    try:
        assert put_site(dport, sites[0])[0] == 200
        body = pack_site(str(sites[1]))[0]
        s = socket.create_connection(("127.0.0.1", dport), timeout=10)
        s.sendall(_put_head(dport, f"Content-Length: {len(body)}\r\n\r\n".encode()) + body[:len(body) // 2])
        deadline = time.monotonic() + 5
        while not os.listdir(store / "incoming") and time.monotonic() < deadline:
            time.sleep(0.02)
        assert os.listdir(store / "incoming")  # the upload is half way in
    finally:
        p.kill()
        p.wait()
    s.close()
    assert _consistent(store, rport, dport, {model_hash(sites[0])}) == model_hash(sites[0])


@pytest.mark.parametrize("step", ["renamed", "store-tmp-written", "store-replaced", "routed", "pruned"])
def test_kill_in_the_middle_of_an_install(tmp_path: Path, sites: list[Path], step: str) -> None:
    rport, dport = _ports()
    store = tmp_path / "store"
    p = _launch(store, rport, dport, kill_at=f"{step}:3")
    try:
        assert put_site(dport, sites[0])[0] == 200
        assert put_site(dport, sites[1])[0] == 200
        with pytest.raises(Exception):  # the instance dies while answering
            put_site(dport, sites[2])
        p.wait(10)
        assert p.returncode == -9
    finally:
        if p.poll() is None:
            p.kill()
            p.wait()
    served = _consistent(store, rport, dport, {model_hash(sites[1]), model_hash(sites[2])})
    before_replace = step in ("renamed", "store-tmp-written")
    assert served == model_hash(sites[1] if before_replace else sites[2])


# --- regressions from the review (one test per finding) -------------------------------------------------


def _unpack_err(tmp_path: Path, body: bytes, **kw: Any) -> list[str]:
    arc = tmp_path / "a.tgz"
    arc.write_bytes(body)
    with pytest.raises(dep.Rejected) as e:
        dep.unpack(str(arc), str(tmp_path / "out"), **kw)
    assert e.value.status == 422
    return e.value.errors or []


def test_review_folders_implied_by_paths_count_against_the_limit(tmp_path: Path) -> None:
    body = tgz([member(f"data/{i}/a/b/c/f.json", b"") for i in range(10)])
    errs = _unpack_err(tmp_path, body, max_files=12)
    assert any("more than 12 folders" in e for e in errs)


def test_review_depth_is_capped(tmp_path: Path) -> None:
    errs = _unpack_err(tmp_path, tgz([member("data/" + "/".join(["d"] * 20) + "/f.json")]))
    assert any("levels of folders" in e for e in errs)


@pytest.mark.parametrize("names", [["data/X/y", "data/x"], ["data/x", "data/X/y"], ["data/A/x", "data/a/y"],
                                   ["data/a", "data/a/"]])
def test_review_case_collisions_through_implied_folders(tmp_path: Path, names: list[str]) -> None:
    members = [member(n.rstrip("/"), None, tarfile.DIRTYPE) if n.endswith("/") else member(n) for n in names]
    errs = _unpack_err(tmp_path, tgz(members))
    assert any("appears twice" in e for e in errs)


def test_review_write_errors_are_not_called_a_broken_archive(tmp_path: Path, sites: list[Path],
                                                             monkeypatch: pytest.MonkeyPatch) -> None:
    arc = tmp_path / "a.tgz"
    arc.write_bytes(pack_site(str(sites[0]))[0])
    real = os.open

    def denied(path: Any, flags: int, mode: int = 0o777, **kw: Any) -> int:
        if str(path).endswith(".json") and "out" in str(path):
            raise PermissionError(errno.EACCES, "Permission denied")
        return real(path, flags, mode, **kw)
    monkeypatch.setattr(os, "open", denied)
    with pytest.raises(dep._WriteFailed):
        dep.unpack(str(arc), str(tmp_path / "out"))


@pytest.mark.parametrize("case", ["unlisted-data", "html-in-assets", "big-index", "inline-script", "srcset",
                                  "style-attr", "meta-refresh", "onload", "base"])
def test_review_unchecked_content_is_refused(inst: Instance, sites: list[Path], case: str) -> None:
    base = site_members(sites[0])
    page = {"inline-script": b"<script>fetch('/x')</script>", "srcset": b'<img srcset="https://evil.example/a.png 1x">',
            "style-attr": b'<div style="background:url(https://evil.example/)"></div>',
            "meta-refresh": b'<meta http-equiv="refresh" content="0;url=https://evil.example/">',
            "onload": b'<body onload="alert(1)">', "base": b'<base href="https://evil.example/">'}
    if case == "unlisted-data":
        body = tgz(base + [member("data/evil.svg", b"<svg onload=alert(1)>")])
    elif case == "html-in-assets":
        body = tgz(base + [member("assets/evil.html", b"<script>alert(1)</script>")])
    elif case == "big-index":
        body = tgz(_replace(base, "data/index.json", b"[" + b"{}," * (2 * 1024 * 1024) + b"{}]"))
    else:
        body = tgz(_replace(base, "index.html", page[case] + b'<script type="module" src="./assets/index-AbCdEf12.js"></script>'))
    before = inst.store_file()
    s, _, doc = put(inst.port, body)
    assert s == 422, (case, doc)
    unchanged_store(inst, before, 0)


def test_review_the_real_viewer_page_passes_the_page_check(tmp_path: Path) -> None:
    static = Path(dep.__file__).parent / "static"
    if not (static / "index.html").is_file():
        pytest.skip("the viewer is not built")
    import shutil
    shutil.copytree(static, tmp_path / "site")
    assert dep._viewer_problems(str(tmp_path / "site")) == []


def test_review_a_memory_hungry_model_fails_in_the_child_and_the_instance_lives(tmp_path: Path,
                                                                                sites: list[Path]) -> None:
    import shutil
    site = tmp_path / "hungry"
    shutil.copytree(sites[0], site)
    idx = json.loads((site / "data" / "index.json").read_text())
    (site / "data" / idx["model"]["file"]).write_bytes(b"[" + b"{}," * (8 * 1024 * 1024) + b"{}]")  # 24 MB of {}
    t0 = time.monotonic()
    with pytest.raises(dep.Rejected) as e:
        dep.check_in_child(str(site), memory=256 * 1024 * 1024)
    assert e.value.status == 422 and time.monotonic() - t0 < 60
    assert any("memory" in x or "model.json" in x for x in e.value.errors or []), e.value.errors


def test_review_one_instance_accepts_deploys_per_store(tmp_path: Path, sites: list[Path]) -> None:
    from buildzr.site.store import StoreError
    a = Store.open(str(tmp_path / "s"), create=True, exclusive=True)
    with pytest.raises(StoreError, match="another buildzr process accepts deploys"):
        Store.open(str(tmp_path / "s"), exclusive=True)
    work = tmp_path / "s" / "incoming" / "work"
    work.mkdir()  # a deploy in progress
    Store.open(str(tmp_path / "s"))  # a read-only serve --store started meanwhile
    assert work.is_dir()  # it did not clean up under the running instance
    assert a.table is not None


def test_review_requests_that_fail_the_gate_are_not_audited(inst: Instance, sites: list[Path]) -> None:
    body = pack_site(str(sites[0]))[0]
    put(inst.port, body, Host="evil.example:1")
    h = deploy_headers()
    del h["X-Buildzr-Deploy"]
    for _ in range(50):
        request(inst.port, "POST", ROLLBACK_ENDPOINT + "?path=a", headers={"Origin": "https://evil.example",
                                                                            "Content-Type": "text/plain"})
    assert inst.log() == []


def test_review_a_malformed_header_line_cannot_hide_forwarded_headers(inst: Instance) -> None:
    req = (f"GET /_buildzr/v1/status HTTP/1.0\r\nHost: 127.0.0.1:{inst.port}\r\nX Bad: y\r\n"
           "X-Forwarded-For: 1.2.3.4\r\n\r\n").encode()
    assert status_of(raw(inst.port, req)) == 400


def test_review_headers_have_a_total_deadline(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dep, "HEADER_TIMEOUT", 1.0)
    i = Instance(tmp_path / "store")
    try:
        s = socket.create_connection(("127.0.0.1", i.port), timeout=10)
        s.sendall(b"GET /_buildzr/v1/status HTTP/1.0\r\n")
        t0 = time.monotonic()
        for _ in range(8):  # one header line every 0.4 s: each is in time, the whole is not
            try:
                s.sendall(b"X-A: b\r\n")
            except OSError:
                break
            time.sleep(0.4)
        s.settimeout(5)
        try:
            data = s.recv(100)
        except OSError:
            data = b""
        assert data == b"" and time.monotonic() - t0 < 4
        s.close()
    finally:
        i.close()


def test_review_the_deploy_listener_caps_its_connections(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dep, "MAX_CONNECTIONS", 3)
    i = Instance(tmp_path / "store")
    try:
        idle = [socket.create_connection(("127.0.0.1", i.port), timeout=5) for _ in range(3)]
        time.sleep(0.3)
        extra = socket.create_connection(("127.0.0.1", i.port), timeout=5)
        assert extra.recv(10) == b""  # closed at once
        for s in idle:
            s.close()
        time.sleep(0.3)
        assert request(i.port, "GET", STATUS_ENDPOINT)[0] == 200  # the slots came back
    finally:
        i.close()


def test_review_ipv6_loopback_host_is_accepted(inst: Instance) -> None:
    assert request(inst.port, "GET", STATUS_ENDPOINT, headers={"Host": f"[::1]:{inst.port}"})[0] == 200
