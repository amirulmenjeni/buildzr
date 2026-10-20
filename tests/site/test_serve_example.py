"""``buildzr serve --example``: the bundled, prebuilt example served from a temporary folder."""

from __future__ import annotations

import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

import buildzr.site.cli as cli
import buildzr.site.example as example
from buildzr.site.check import check_built
from buildzr.site.serve import make_server
from tests.site.test_cli import run

ROOT = Path(__file__).resolve().parents[2]
VIEWER_BUILT = (Path(example.STATIC_DIR) / "index.html").is_file()


@pytest.fixture
def fake_static(tmp_path_factory: pytest.TempPathFactory, monkeypatch: pytest.MonkeyPatch) -> Path:
    """A tiny stand-in for the viewer bundle (which is gitignored build output)."""
    static = tmp_path_factory.mktemp("viewer") / "static"
    (static / "assets").mkdir(parents=True)
    (static / "index.html").write_text('<!doctype html><div id="root"></div>', encoding="utf-8")
    (static / "assets" / "index.js").write_text("// viewer", encoding="utf-8")
    monkeypatch.setattr(example, "STATIC_DIR", str(static))
    return static


class Started:
    """What ``serve`` was started with, and what the staged folder held while it ran."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    @property
    def last(self) -> dict[str, Any]:
        return self.calls[-1]


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch, fake_static: Path) -> Started:
    rec = Started()

    def fake(directory: str, host: str, port: int, public_url: Optional[str], origins: list[str], **kw: Any) -> None:
        rec.calls.append({"dir": directory, "host": host, "port": port, "public_url": public_url, "origins": origins,
                          "shown": kw.get("shown"), "files": sorted(os.listdir(os.path.join(directory, "example")))})
    monkeypatch.setattr(cli, "serve", fake)
    return rec


# --- parsing and conflicts --------------------------------------------------------------------------------------


def test_example_is_a_flag_of_serve_only() -> None:
    ap = cli._parser()
    assert ap.parse_args(["serve", "--example"]).example is True
    assert ap.parse_args(["serve"]).example is False
    with pytest.raises(cli._Usage):
        ap.parse_args(["build", "--example"])


@pytest.mark.parametrize("extra,shown", [
    (["some/path"], "PATH"),
    (["--no-build"], "--no-build"),
    (["--rebuild"], "--rebuild"),
    (["-c", "x.yaml"], "-c/--config"),
    (["--config=x.yaml"], "-c/--config"),
    (["-v"], "-v/--verbose"),
])
def test_example_refuses_what_makes_no_sense_with_it(extra: list[str], shown: str, started: Started, tmp_path: Path,
                                                     monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(tmp_path, monkeypatch, capsys, "serve", "--example", *extra)
    assert code == 2 and out == ""
    assert f"buildzr: error: --example serves the bundled example, so it cannot be used with {shown}" in err
    assert started.calls == [] and list(tmp_path.iterdir()) == []


def test_example_conflict_does_not_need_the_path_to_exist(started: Started, tmp_path: Path,
                                                          monkeypatch: pytest.MonkeyPatch,
                                                          capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(tmp_path, monkeypatch, capsys, "serve", "missing-folder", "--example")
    assert code == 2 and "cannot be used with PATH" in err


def test_example_keeps_host_port_public_url_and_cors_origin(started: Started, tmp_path: Path,
                                                            monkeypatch: pytest.MonkeyPatch,
                                                            capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(tmp_path, monkeypatch, capsys, "serve", "--example", "-p", "9123", "--host", "0.0.0.0",
                       "--public-url", "https://arch.example.com/", "--cors-origin", "https://a.example.com")
    assert (code, err) == (0, "")
    got = started.last
    assert (got["host"], got["port"], got["public_url"], got["origins"]) == \
        ("0.0.0.0", 9123, "https://arch.example.com", ["https://a.example.com"])


def test_example_defaults_and_bad_values(started: Started, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                         capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path, monkeypatch, capsys, "serve", "--example")[0] == 0
    got = started.last
    assert (got["host"], got["port"], got["public_url"], got["origins"]) == ("127.0.0.1", 8000, None, [])
    code, _, err = run(tmp_path, monkeypatch, capsys, "serve", "--example", "-p", "70000")
    assert code == 2 and "--port" in err


# --- isolation from the current folder --------------------------------------------------------------------------


def test_example_ignores_the_project_of_the_current_folder(started: Started, tmp_path: Path,
                                                           monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    """A buildzr.yaml that would not even load, with ports and a workspaces folder of its own, changes nothing."""
    (tmp_path / "buildzr.yaml").write_text("serve: {port: 9999, host: 0.0.0.0}\nworkspaces: [\n", encoding="utf-8")
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "mine.py").write_text("raise SystemExit('must not run')\n", encoding="utf-8")
    before = sorted(p.name for p in tmp_path.rglob("*"))
    code, out, err = run(tmp_path, monkeypatch, capsys, "serve", "--example")
    assert (code, err) == (0, "")
    assert (started.last["host"], started.last["port"]) == ("127.0.0.1", 8000)
    assert started.last["shown"] == "the bundled example"
    assert sorted(p.name for p in tmp_path.rglob("*")) == before  # nothing created, nothing built


def test_example_creates_nothing_in_the_current_folder(started: Started, tmp_path: Path,
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    empty = tmp_path / "empty"
    empty.mkdir()
    (tmp_path / "tmp").mkdir()
    monkeypatch.setattr(tempfile, "tempdir", str(tmp_path / "tmp"))
    assert run(empty, monkeypatch, capsys, "serve", "--example")[0] == 0
    assert list(empty.iterdir()) == []
    assert not (empty / ".buildzr").exists()
    assert str(started.last["dir"]).startswith(str(tmp_path / "tmp"))  # staged under the temporary folder


# --- cleanup ----------------------------------------------------------------------------------------------------


def test_example_removes_its_temporary_folder_when_serving_ends(started: Started, tmp_path: Path,
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    assert run(tmp_path, monkeypatch, capsys, "serve", "--example")[0] == 0
    assert started.last["files"] == ["assets", "build.json", "data", "index.html"]
    assert not os.path.exists(started.last["dir"])


def test_example_removes_its_temporary_folder_when_the_port_is_taken(fake_static: Path, tmp_path: Path,
                                                                     monkeypatch: pytest.MonkeyPatch,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    dirs: list[str] = []

    def failing(directory: str, *a: Any, **kw: Any) -> None:
        dirs.append(directory)
        raise OSError(98, "Address already in use")
    monkeypatch.setattr(cli, "serve", failing)
    code, _, err = run(tmp_path, monkeypatch, capsys, "serve", "--example", "-p", "8123")
    assert code == 1 and "cannot serve on 127.0.0.1:8123: Address already in use" in err
    assert dirs and not os.path.exists(dirs[0])


def test_example_restores_the_sigterm_handler(started: Started, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    before = signal.getsignal(signal.SIGTERM)
    assert run(tmp_path, monkeypatch, capsys, "serve", "--example")[0] == 0
    assert signal.getsignal(signal.SIGTERM) is before


def test_example_without_a_viewer_bundle_says_so(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(example, "STATIC_DIR", str(tmp_path / "nope"))
    code, _, err = run(tmp_path, monkeypatch, capsys, "serve", "--example")
    assert code == 1 and "the viewer bundle is missing" in err


# --- the shipped resources --------------------------------------------------------------------------------------


def test_shipped_example_is_a_valid_built_workspace() -> None:
    folder = Path(example.EXAMPLE_DIR)
    info = json.loads((folder / "build.json").read_text(encoding="utf-8"))
    assert info["status"] == "ok" and info["name"] == example.EXAMPLE_NAME
    assert set(os.listdir(folder)) == {"build.json", "data"}  # the viewer is not duplicated here
    rep = check_built(str(folder / "data"), require_build_json=True)
    assert rep.errors == []
    index = json.loads((folder / "data" / "index.json").read_text(encoding="utf-8"))
    assert info["modelHash"] == index["modelHash"]


def test_shipped_example_shows_the_supported_view_kinds() -> None:
    index = json.loads((Path(example.EXAMPLE_DIR) / "data" / "index.json").read_text(encoding="utf-8"))
    model = json.loads(next((Path(example.EXAMPLE_DIR) / "data").glob("model.*.json")).read_text(encoding="utf-8"))
    kinds = {v["kind"] for v in model["views"]}
    assert kinds == {"systemLandscape", "systemContext", "container", "component", "dynamic", "deployment"}
    types = {e["type"] for e in model["elements"]}
    assert {"Person", "SoftwareSystem", "Container", "Component", "DeploymentNode", "ContainerInstance"} <= types
    assert not [t for t in types if "custom" in t.lower()] and "custom" not in kinds
    assert index["scenes"]


def test_stage_copies_the_viewer_and_the_example(fake_static: Path, tmp_path: Path) -> None:
    folder = Path(example.stage(str(tmp_path)))
    assert folder == tmp_path / "example"
    assert (folder / "index.html").is_file() and (folder / "assets" / "index.js").is_file()
    assert (folder / "build.json").is_file() and (folder / "data" / "index.json").is_file()
    assert check_built(str(folder / "data"), require_build_json=True).errors == []
    assert sorted(os.listdir(example.EXAMPLE_DIR)) == ["build.json", "data"]  # the package itself is not touched


def test_staged_example_is_served_with_a_viewer_and_a_model_endpoint(fake_static: Path, tmp_path: Path) -> None:
    example.stage(str(tmp_path))
    srv = make_server(str(tmp_path), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}"
    try:
        def get(path: str) -> tuple[int, bytes]:
            with urllib.request.urlopen(base + path, timeout=10) as r:  # redirects are followed
                return r.status, r.read()
        status, page = get("/")  # one workspace: / goes to it
        assert status == 200 and b'id="root"' in page
        assert get("/example/")[0] == 200
        status, body = get("/example/api/v1/")
        assert status == 200 and json.loads(body)["name"] == "example"
        status, body = get("/example/api/v1/views")
        assert status == 200 and len(json.loads(body)["items"]) == 6
        assert get("/_buildzr/v1/workspaces")[0] == 200
        status, body = get("/example/data/index.json")
        assert status == 200 and json.loads(body)["scenes"]
    finally:
        srv.shutdown()
        srv.server_close()


@pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"), reason="needs Node to lay out")
@pytest.mark.skipif(not (ROOT / "scripts" / "build_serve_example.py").exists(), reason="not in the sdist")
def test_shipped_example_is_up_to_date() -> None:
    r = subprocess.run([sys.executable, str(ROOT / "scripts" / "build_serve_example.py"), "--check"],
                       capture_output=True, text=True, cwd=ROOT)
    assert r.returncode == 0, r.stdout + r.stderr


# --- the real command, as a subprocess --------------------------------------------------------------------------


def _free_port() -> int:
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])


@pytest.fixture
def server(tmp_path: Path) -> Iterator[tuple[subprocess.Popen[str], int, Path, Path]]:
    cwd, tmp = tmp_path / "cwd", tmp_path / "tmp"
    cwd.mkdir()
    tmp.mkdir()
    (cwd / "buildzr.yaml").write_text("workspaces: [\n", encoding="utf-8")  # would fail to load: must be ignored
    port = _free_port()
    env = {**os.environ, "TMPDIR": str(tmp), "PYTHONPATH": str(ROOT)}
    proc = subprocess.Popen([sys.executable, "-m", "buildzr.site.cli", "serve", "--example", "-p", str(port)],
                            cwd=cwd, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
    try:
        for _ in range(100):
            try:
                urllib.request.urlopen(f"http://127.0.0.1:{port}/_buildzr/v1/workspaces", timeout=1).close()
                break
            except (urllib.error.URLError, ConnectionError, OSError):
                assert proc.poll() is None, proc.communicate()
                time.sleep(0.1)
        else:
            raise AssertionError("buildzr serve --example did not start")
        yield proc, port, cwd, tmp
    finally:
        if proc.poll() is None:
            proc.kill()
        proc.communicate()


@pytest.mark.skipif(not VIEWER_BUILT, reason="needs the viewer bundle (cd viewer && npm ci && npm run build)")
@pytest.mark.skipif(sys.platform == "win32", reason="stopped with SIGTERM")
def test_serve_example_process_serves_then_stops_cleanly(server: tuple[subprocess.Popen[str], int, Path, Path]) -> None:
    proc, port, cwd, tmp = server
    base = f"http://127.0.0.1:{port}"
    assert any(p.name.startswith("buildzr-example-") for p in tmp.iterdir())
    with urllib.request.urlopen(base + "/example/", timeout=10) as r:
        assert r.status == 200 and b'id="root"' in r.read()
    with urllib.request.urlopen(base + "/example/api/v1/", timeout=10) as r:
        assert r.status == 200
    proc.send_signal(signal.SIGTERM)
    out, err = proc.communicate(timeout=20)
    assert proc.returncode == 0, err
    assert f"{base}/example/" in out  # the usable URL is printed
    assert list(tmp.iterdir()) == []  # the temporary folder is gone
    assert [p.name for p in cwd.iterdir()] == ["buildzr.yaml"]  # nothing written to the current folder
