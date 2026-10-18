"""``buildzr deploy`` to ``url:`` targets: packing, addresses, every failure of table 6.9, and an end-to-end run with the
real CLI (instance in a subprocess, the real layout and the real viewer in Chromium; needs Node)."""

from __future__ import annotations

import errno
import gzip
import http.server
import io
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tarfile
import threading
import time
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

import buildzr.site.deploy as dep
import buildzr.site.deploy_client as dc
from buildzr.site.cli import main
from buildzr.site.deploy_client import DeployFailed, pack_site, parse_address
from tests.site.deploy_helpers import ROOT, Instance, model_hash, put, request, valid_site

Json = dict[str, Any]


@pytest.fixture(scope="module")
def sites(tmp_path_factory: pytest.TempPathFactory) -> list[Path]:
    tmp = tmp_path_factory.mktemp("clientsites")
    return [valid_site(tmp / f"v{n}", n) for n in range(3)]


@pytest.fixture
def inst(tmp_path: Path) -> Iterator[Instance]:
    i = Instance(tmp_path / "store")
    yield i
    i.close()


def free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port: int = s.getsockname()[1]
    s.close()
    return port


def repo(tmp_path: Path, url: str, path: str = "pr/42", extra: str = "") -> Path:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    (root / "buildzr.yaml").write_text(f'targets:\n  preview: {{url: "{url}", path: "{path}"{extra}}}\n')
    return root


def run(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
        ) -> tuple[int, str, str]:
    monkeypatch.chdir(root)
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


# --- packing --------------------------------------------------------------------------------------------


def test_the_archive_is_deterministic(sites: list[Path], tmp_path: Path) -> None:
    a, files, size = pack_site(str(sites[0]))
    copy = tmp_path / "copy"
    shutil.copytree(sites[0], copy)
    for d, _dirs, names in os.walk(copy):
        for n in names:
            os.utime(os.path.join(d, n), (1e9, 1e9))
            os.chmod(os.path.join(d, n), 0o600)
    assert pack_site(str(copy))[0] == a
    assert a[:2] == b"\x1f\x8b" and a[4:8] == bytes(4) and not a[3] & 0x08  # gzip mtime 0, no file name
    tf = tarfile.open(fileobj=io.BytesIO(gzip.decompress(a)))
    members = tf.getmembers()
    assert [m.name for m in members] == sorted(m.name for m in members)
    assert all(m.mtime == 0 and m.uid == 0 and m.gid == 0 and m.uname == "" and m.gname == "" for m in members)
    assert all((m.mode == 0o755) if m.isdir() else (m.mode == 0o644 and m.isreg()) for m in members)
    assert all(not m.pax_headers for m in members)
    assert files == sum(1 for m in members if m.isreg()) and size == sum(m.size for m in members)


def test_packing_refuses_what_the_instance_would(sites: list[Path], tmp_path: Path) -> None:
    extra = tmp_path / "extra"
    shutil.copytree(sites[0], extra)
    (extra / "llms.txt").write_text("x")
    with pytest.raises(DeployFailed, match="llms.txt is not part of a built site"):
        pack_site(str(extra))
    link = tmp_path / "link"
    shutil.copytree(sites[0], link)
    os.symlink("/etc/passwd", link / "data" / "x.json")
    with pytest.raises(DeployFailed, match="symbolic link"):
        pack_site(str(link))


@pytest.mark.parametrize("url,ok", [("http://127.0.0.1:8001", True), ("http://localhost:9001/", True),
                                    ("http://[::1]:8001", True), ("https://127.0.0.1:8001", True),
                                    ("http://10.0.0.5:8001", False), ("http://example.com:8001", False),
                                    ("http://127.0.0.2:8001", False), ("http://127.0.0.1.nip.io:8001", False),
                                    ("http://127.0.0.1:8001/deploy", False), ("http://u:p@127.0.0.1:8001", False),
                                    ("ftp://127.0.0.1", False), ("http://127.0.0.1:99999", False)])
def test_only_loopback_addresses(url: str, ok: bool) -> None:
    if ok:
        assert parse_address(url).host in ("127.0.0.1", "localhost", "::1")
    else:
        with pytest.raises(DeployFailed) as e:
            parse_address(url)
        assert e.value.code == 2


# --- the CLI against an instance in this process ------------------------------------------------------


def test_no_open_line_for_a_site_without_a_viewer(inst: Instance, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    root = repo(tmp_path, inst.url)
    only = [valid_site(tmp_path / f"only{n}", n, viewer=False) for n in (1, 2)]
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(only[0]))
    assert code == 0, err
    assert "open:" not in out and out.splitlines()[-1] == f"api:  http://127.0.0.1:{inst.rport}/pr/42/api/v1/"
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(only[0]))
    assert code == 0 and "unchanged pr/42" in out and "open:" not in out and "api:  " in out
    run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(only[1]))
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--rollback")
    assert code == 0, err
    assert out.startswith("rolled back pr/42") and "open:" not in out and "api:  " in out


def test_deploy_unchanged_and_rollback_through_the_cli(inst: Instance, sites: list[Path], tmp_path: Path,
                                                      monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    root = repo(tmp_path, inst.url)
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[0]))
    assert code == 0, err
    lines = out.splitlines()
    assert lines[0].startswith("using ") and "modelHash sha256:" in lines[0]
    assert lines[1].startswith("uploading 10 files, ") and lines[1].endswith(f" KB to {inst.url} (path pr/42)")
    assert lines[2] == f"deployed pr/42: release r-0001, modelHash {model_hash(sites[0])[:19]}…"
    assert lines[3] == f"open: http://127.0.0.1:{inst.rport}/pr/42/"
    assert lines[4] == f"api:  http://127.0.0.1:{inst.rport}/pr/42/api/v1/"
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[1]))
    assert code == 0
    assert (f"deployed pr/42: release r-0002, modelHash {model_hash(sites[1])[:19]}… "
            f"(previous {model_hash(sites[0])[:19]}…)") in out
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[1]))
    assert code == 0 and "unchanged pr/42: release r-0002 already has these files" in out
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--rollback")
    assert code == 0 and out.startswith("rolled back pr/42: release r-0001 is current again")
    assert request(inst.rport, "GET", "/pr/42/data/index.json")[2]["modelHash"] == model_hash(sites[0])
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--rollback", "--from", str(sites[0]))
    assert code == 2 and "--from cannot be used with --rollback" in err
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--path", "pr/api")
    assert code == 2 and "reserved" in err


def test_dry_run_sends_nothing(tmp_path: Path, sites: list[Path], monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    port = free_port()  # nothing listens there: any request would fail
    root = repo(tmp_path, f"http://127.0.0.1:{port}")
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[0]), "--dry-run")
    assert code == 0, err
    assert "packed 10 files" in out
    assert out.splitlines()[-1].startswith(f"dry run: would upload 10 files, ")
    assert out.splitlines()[-1].endswith(f"to http://127.0.0.1:{port} (path pr/42); nothing was sent")
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--rollback", "--dry-run")
    assert code == 0 and "nothing was sent" in out


def test_dry_run_against_a_live_instance_leaves_it_alone(inst: Instance, sites: list[Path], tmp_path: Path,
                                                         monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    root = repo(tmp_path, inst.url)
    before = inst.store_file()
    assert run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[0]), "--dry-run")[0] == 0
    assert inst.store_file() == before and inst.log() == []


# --- table 6.9, row by row ------------------------------------------------------------------------------


class Fake(http.server.BaseHTTPRequestHandler):
    """A server that looks like a deploy listener for the status request and then misbehaves on the upload."""

    mode = "cut"

    def log_message(self, *a: Any) -> None:
        pass

    def do_GET(self) -> None:
        if self.mode == "html":
            body = b"<html>hello</html>"
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
        else:
            body = json.dumps({"instanceVersion": "0.0.36", "accepting": True,
                               "limits": {"maxUploadBytes": 1 << 30}}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_PUT(self) -> None:
        if self.mode == "late":  # the whole body arrives, then the instance goes away without answering
            self.rfile.read(int(self.headers["Content-Length"]))
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        self.rfile.read(10)
        if self.mode == "cut":
            self.connection.shutdown(socket.SHUT_RDWR)
            return
        doc = {"type": "urn:buildzr:problem:" + self.mode, "code": self.mode, "status": 400, "detail": "x"}
        if self.mode == "too-large":
            doc.update(status=413, limitBytes=50 << 20, uploadBytes=63 << 20)
        body = json.dumps(doc).encode()
        self.send_response(int(str(doc["status"])))
        self.send_header("Content-Type", "application/problem+json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def fake(mode: str) -> tuple[str, Any]:
    h = type("F", (Fake,), {"mode": mode})
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), h)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return f"http://127.0.0.1:{srv.server_address[1]}", srv


def deploy_err(site: Path, url: str, timeout: float = 10) -> DeployFailed:
    with pytest.raises(DeployFailed) as e:
        dc.deploy(str(site), url, "pr/42", timeout, out=lambda s: None)
    return e.value


def test_row_upload_interrupted(sites: list[Path]) -> None:
    url, srv = fake("cut")  # cut while sending; a small body may already be in the socket buffers, then it is "late"
    try:
        e = deploy_err(sites[0], url)
        assert e.code == 3 and (str(e).startswith("upload interrupted, nothing changed")
                                or "may still have installed it" in str(e))
    finally:
        srv.shutdown()
    url, srv = fake("late")
    try:
        e = deploy_err(sites[0], url)
        assert e.code == 3 and "may still have installed it" in str(e)
    finally:
        srv.shutdown()
    url, srv = fake("upload-incomplete")
    try:
        e = deploy_err(sites[0], url)
        assert e.code == 3 and str(e).startswith("upload interrupted, nothing changed")
    finally:
        srv.shutdown()


def test_row_invalid_site(inst: Instance, sites: list[Path], tmp_path: Path) -> None:
    bad = tmp_path / "bad"
    shutil.copytree(sites[0], bad)
    (bad / "build.json").write_text('{"modelHash":"sha256:' + "0" * 64 + '"}\n')
    e = deploy_err(bad, inst.url)
    assert e.code == 1 and str(e).startswith("the instance rejected the site") and any("build.json" in d for d in e.details)
    assert len(inst.store.table) == 0


def test_row_too_large(tmp_path: Path, sites: list[Path]) -> None:
    i = Instance(tmp_path / "store", max_upload_bytes=1000)
    try:
        e = deploy_err(sites[0], i.url)
        assert e.code == 1 and str(e).endswith(", the instance accepts 1000 B (--max-upload-mb)")
        assert str(e).startswith("site is ")
        assert i.log() == []  # refused before uploading
    finally:
        i.close()
    url, srv = fake("too-large")  # the instance's own 413
    try:
        with pytest.raises(DeployFailed) as ex:
            dc.Client(parse_address(url), 10).send("PUT", "/_buildzr/v1/deploy", b"x" * 100, {})
        assert ex.value.code == 1 and "the instance accepts 50 MB (--max-upload-mb)" in str(ex.value)
    finally:
        srv.shutdown()


def test_row_disk_full(inst: Instance, sites: list[Path], monkeypatch: pytest.MonkeyPatch) -> None:
    def full(*a: Any, **k: Any) -> Any:
        raise OSError(errno.ENOSPC, "No space left on device")
    monkeypatch.setattr(dep, "unpack", full)
    e = deploy_err(sites[0], inst.url)
    assert e.code == 3 and str(e) == "instance is out of disk space; nothing changed"
    assert inst.incoming() == []


def test_row_nothing_listening(sites: list[Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    port = free_port()
    root = repo(tmp_path, f"http://127.0.0.1:{port}")
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(sites[0]))
    assert code == 3
    assert f"buildzr: error: nothing is listening at http://127.0.0.1:{port}; start the instance with" in err
    assert "--accept-deploys" in err


def test_row_wrong_url(inst: Instance, sites: list[Path]) -> None:
    for url in (f"http://127.0.0.1:{inst.rport}",):  # the reading port of a store
        e = deploy_err(sites[0], url)
        assert e.code == 1 and "is not a buildzr deploy address" in str(e)
    url, srv = fake("html")  # another web server
    try:
        e = deploy_err(sites[0], url)
        assert e.code == 1 and "is not a buildzr deploy address" in str(e)
    finally:
        srv.shutdown()
    plain = http.server.ThreadingHTTPServer(("127.0.0.1", 0), http.server.SimpleHTTPRequestHandler)
    threading.Thread(target=plain.serve_forever, daemon=True).start()
    try:
        e = deploy_err(sites[0], f"http://127.0.0.1:{plain.server_address[1]}")
        assert e.code == 1 and "is not a buildzr deploy address" in str(e)
    finally:
        plain.shutdown()


def test_row_busy_waits_then_succeeds_or_gives_up(inst: Instance, sites: list[Path],
                                                  monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(dep, "RETRY_AFTER", 1)
    lock = inst.deployer.RequestHandlerClass.busy  # type: ignore[attr-defined]
    lock.acquire()
    threading.Timer(1.5, lock.release).start()
    said: list[str] = []
    assert dc.deploy(str(sites[0]), inst.url, "pr/42", 20, out=said.append) == 0
    assert any("busy with another deploy; trying again in 1 s" in s for s in said)
    lock.acquire()
    try:
        t0 = time.monotonic()
        e = deploy_err(sites[1], inst.url, timeout=2.5)
        assert e.code == 3 and "busy with another deploy" in str(e) and time.monotonic() - t0 < 6
    finally:
        lock.release()


def test_https_to_the_listener_hints_and_fails(inst: Instance, sites: list[Path]) -> None:
    said: list[str] = []
    with pytest.raises(DeployFailed) as e:
        dc.deploy(str(sites[0]), f"https://127.0.0.1:{inst.port}", "", 10, out=lambda x: None, warn=said.append)
    assert said and "plain http" in said[0]
    assert e.value.code == 3


# --- end to end with the real CLI (needs Node, the built viewer and Playwright) ---------------------------

STATIC = os.path.join(ROOT, "buildzr", "site", "static", "index.html")
PLAYWRIGHT = os.path.join(ROOT, "viewer", "node_modules", "playwright")
e2e = pytest.mark.skipif(not (shutil.which("node") and os.path.isfile(STATIC) and os.path.isdir(PLAYWRIGHT)),
                         reason="needs Node, the built viewer (buildzr/site/static) and Playwright")


def cli(*args: str, cwd: Path, env: Optional[dict[str, str]] = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run([sys.executable, "-m", "buildzr.site.cli", *args], cwd=cwd, env=env, text=True,
                          capture_output=True, timeout=300)


@e2e
def test_end_to_end_with_the_real_cli_and_viewer(tmp_path: Path) -> None:
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    shutil.copy(os.path.join(ROOT, "examples", "buildzr_models_example.py"), root / "model.py")
    (root / "synthetic.py").write_text("from tests.site.synthetic import synthetic\nw = synthetic('S')\n")
    rport, dport = free_port(), free_port()
    (root / "buildzr.yaml").write_text(
        f'workspace: model.py\ntargets:\n  preview: {{url: "http://127.0.0.1:{dport}", path: "pr/${{PR_NUMBER}}"}}\n')
    env = {**os.environ, "PR_NUMBER": "42", "PYTHONPATH": ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")}
    store = tmp_path / "store"
    srv = subprocess.Popen([sys.executable, "-m", "buildzr.site.cli", "serve", "--store", str(store), "--accept-deploys",
                            "-p", str(rport), "--deploy-port", str(dport)], env=env, text=True,
                           stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    try:
        assert srv.stdout is not None
        first = srv.stdout.readline()
        second = srv.stdout.readline()
        assert first == f"Serving store {store} (0 sites) at http://127.0.0.1:{rport}/ (read only)\n"
        assert second == f"Accepting deploys at http://127.0.0.1:{dport}/ (this machine only; no authentication)\n"
        r1 = cli("deploy", "-t", "preview", cwd=root, env=env)
        assert r1.returncode == 0, r1.stderr
        out = [x for x in r1.stdout.splitlines() if not x.startswith(str(root))]  # the build's progress line
        assert out[0].startswith("built (13 elements, 6 relationships, 1 view; modelHash sha256:")
        assert out[1].startswith("uploading ") and out[1].endswith(f"to http://127.0.0.1:{dport} (path pr/42)")
        assert out[2].startswith("deployed pr/42: release r-0001, modelHash sha256:")
        assert out[3] == f"open: http://127.0.0.1:{rport}/pr/42/"
        r2 = cli("deploy", "-t", "preview", "-w", "synthetic.py", cwd=root, env=env)
        assert r2.returncode == 0, r2.stderr
        assert "release r-0002" in r2.stdout and "(previous sha256:" in r2.stdout
        r3 = cli("deploy", "-t", "preview", "-w", "synthetic.py", cwd=root, env=env)
        assert r3.returncode == 0 and "unchanged pr/42: release r-0002" in r3.stdout, r3.stdout + r3.stderr
        log_before = (store / "deploys.log").read_text()
        r4 = cli("deploy", "-t", "preview", "--dry-run", cwd=root, env=env)
        assert r4.returncode == 0 and "nothing was sent" in r4.stdout
        assert (store / "deploys.log").read_text() == log_before
        r5 = cli("deploy", "-t", "preview", "--rollback", cwd=root, env=env)
        assert r5.returncode == 0 and "release r-0001 is current again" in r5.stdout
        # an invalid site: refused locally by the CLI, and refused by the instance when sent anyway
        site = tmp_path / "broken"
        assert cli("build", "-o", str(site), cwd=root, env=env).returncode == 0
        (site / "build.json").write_text('{"modelHash":"sha256:' + "0" * 64 + '"}\n')
        r6 = cli("deploy", "-t", "preview", "--from", str(site), cwd=root, env=env)
        assert r6.returncode == 1 and "build.json" in r6.stderr
        before = (store / "buildzr-store.json").read_bytes()
        s, _, doc = put(dport, pack_site(str(site))[0], "pr/42")
        assert s == 422 and any("build.json" in e for e in doc["errors"])
        assert (store / "buildzr-store.json").read_bytes() == before
        assert os.listdir(store / "incoming") == []
        # the deployed site in Chromium through an element's viewerUrl
        el = request(rport, "GET", "/pr/42/api/v1/element?id=e-commerce-system/web-app")[2]["element"]
        script = os.path.join(ROOT, "viewer", "tests", "opendeployed.mjs")
        r = subprocess.run(["node", script, f"http://127.0.0.1:{rport}{el['viewerUrl']}", el["id"]], cwd=root,
                           text=True, capture_output=True, timeout=120)
        assert r.returncode == 0, r.stdout + r.stderr
        res = json.loads(r.stdout.strip().splitlines()[-1])
        assert res == {"selected": 1, "onCanvas": 1, "errors": []}, res
        log = [json.loads(x) for x in (store / "deploys.log").read_text().splitlines()]
        assert [(x["action"], x["result"]) for x in log] == [("deploy", "ok"), ("deploy", "ok"), ("deploy", "unchanged"),
                                                            ("rollback", "ok"), ("deploy", "rejected")]
        print(f"end to end: {len(log)} audit lines, r1 {out[1]}")
    finally:
        srv.send_signal(signal.SIGINT)
        try:
            srv.wait(10)
        except subprocess.TimeoutExpired:
            srv.kill()
    assert srv.returncode == 0
    for p in (rport, dport):  # both listeners are gone
        with pytest.raises(OSError):
            socket.create_connection(("127.0.0.1", p), timeout=1).close()


# --- regressions from the review ------------------------------------------------------------------------


def test_review_from_with_a_special_file_is_one_line(sites: list[Path], tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    site = tmp_path / "s"
    shutil.copytree(sites[0], site)
    os.mkfifo(site / "data" / "pipe")
    root = repo(tmp_path, f"http://127.0.0.1:{free_port()}")
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview", "--from", str(site))
    assert code == 1 and err == f"buildzr: error: {site}: data/pipe is not a regular file\n"


def test_review_rollback_of_an_unknown_site(inst: Instance) -> None:
    with pytest.raises(DeployFailed) as e:
        dc.rollback(inst.url, "pr/43", 10, out=lambda s: None)
    assert e.value.code == 1 and "no site at pr/43" in str(e.value)


def test_review_a_server_that_is_not_http_is_not_a_deploy_address(sites: list[Path]) -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def answer() -> None:
        while True:
            try:
                c, _ = srv.accept()
            except OSError:
                return
            c.sendall(b"SSH-2.0-OpenSSH_9.0\r\n")
            c.close()
    threading.Thread(target=answer, daemon=True).start()
    try:
        e = deploy_err(sites[0], f"http://127.0.0.1:{srv.getsockname()[1]}")
        assert e.code == 1 and "is not a buildzr deploy address" in str(e)
    finally:
        srv.close()


def test_review_the_timeout_is_a_total_limit(sites: list[Path]) -> None:
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(5)

    def trickle() -> None:
        try:
            c, _ = srv.accept()
            c.recv(65536)
            for b in b"HTTP/1.0 200 OK\r\nContent-Type: application/json\r\n" + b"X: " + b"y" * 1000:
                c.sendall(bytes([b]))
                time.sleep(0.05)
        except OSError:
            pass
    threading.Thread(target=trickle, daemon=True).start()
    t0 = time.monotonic()
    try:
        with pytest.raises(DeployFailed) as e:
            dc.Client(parse_address(f"http://127.0.0.1:{srv.getsockname()[1]}"), 2).status()
        assert e.value.code in (1, 3) and time.monotonic() - t0 < 5
    finally:
        srv.close()


def test_review_port_0_and_stray_characters_are_refused() -> None:
    for url in ("http://127.0.0.1:0", "http://127.0.0.1:1/?", "http://127.0.0.1:1/#", "http://127.0.0.1:1\t"):
        with pytest.raises(DeployFailed) as e:
            parse_address(url)
        assert e.value.code == 2, url
    assert parse_address("http://localhost:9001/").url == "http://localhost:9001"


def test_review_a_corrupt_gzip_inside_a_member_is_422(tmp_path: Path) -> None:
    import tarfile as tf_
    raw = io.BytesIO()
    with tf_.open(fileobj=raw, mode="w", format=tf_.USTAR_FORMAT) as t:
        info = tf_.TarInfo("data/index.json")
        data = os.urandom(200_000)
        info.size = len(data)
        t.addfile(info, io.BytesIO(data))
    body = gzip.compress(raw.getvalue()[:100_000]) + b"XXXXXXXX"
    arc = tmp_path / "a.tgz"
    arc.write_bytes(body)
    with pytest.raises(dep.Rejected) as e:
        dep.unpack(str(arc), str(tmp_path / "out"))
    assert e.value.status == 422


def test_review_the_check_child_ignores_the_current_folder(tmp_path: Path, sites: list[Path],
                                                           monkeypatch: pytest.MonkeyPatch) -> None:
    fake_pkg = tmp_path / "cwd" / "buildzr" / "site"
    fake_pkg.mkdir(parents=True)
    (tmp_path / "cwd" / "buildzr" / "__init__.py").write_text("")
    (fake_pkg / "__init__.py").write_text("")
    (fake_pkg / "deploy.py").write_text("def _child_main(a):\n    print('{\"ok\": true}')\n    return 0\n")
    monkeypatch.chdir(tmp_path / "cwd")
    bad = tmp_path / "bad"
    shutil.copytree(sites[0], bad)
    (bad / "build.json").write_text('{"modelHash":"sha256:' + "0" * 64 + '"}\n')
    with pytest.raises(dep.Rejected):
        dep.check_in_child(str(bad))  # the real checker ran, not the fake one in the current folder


def test_review_a_failed_exclusive_open_releases_the_lock(tmp_path: Path) -> None:
    from buildzr.site.store import Store, StoreError
    Store.open(str(tmp_path / "s"), create=True)
    good = (tmp_path / "s" / "buildzr-store.json").read_text()
    (tmp_path / "s" / "buildzr-store.json").write_text("{not json")
    with pytest.raises(StoreError):
        Store.open(str(tmp_path / "s"), exclusive=True)
    (tmp_path / "s" / "buildzr-store.json").write_text(good)
    assert Store.open(str(tmp_path / "s"), exclusive=True) is not None
