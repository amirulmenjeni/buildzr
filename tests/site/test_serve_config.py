"""The ``serve:`` section of ``buildzr.yaml``: each option wins over the file, the file over the default."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any, Optional

import pytest

import buildzr.site.cli as cli
from buildzr.site.serve import make_server
from tests.site.test_build_all import HEAD, tree, ws
from tests.site.test_cli import fake_built, project, run, stubbed  # noqa: F401  (fixture)

Json = dict[str, Any]


@pytest.fixture
def started(monkeypatch: pytest.MonkeyPatch) -> list[dict[str, Any]]:
    """Record what ``serve`` would be started with, instead of starting it."""
    calls: list[dict[str, Any]] = []

    def fake(directory: str, host: str, port: int, public_url: Optional[str], origins: list[str], **kw: Any) -> None:
        calls.append({"dir": directory, "host": host, "port": port, "public_url": public_url, "origins": origins})
    monkeypatch.setattr(cli, "serve", fake)
    return calls


def built_project(tmp_path: Path, yaml: str) -> Path:
    root = project(tmp_path, yaml, ws=False)
    fake_built(root / "out" / "w")
    return root


def test_defaults_without_a_serve_section(tmp_path: Path, started: list[Json], monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = built_project(tmp_path, "version: 1\n")
    assert run(root, monkeypatch, capsys, "serve", "out")[0] == 0
    assert started[-1] == {"dir": "out", "host": "127.0.0.1", "port": 8000, "public_url": None, "origins": []}


FILE = ("serve:\n  public_url: https://arch.example.com/\n  port: 8123\n  host: 0.0.0.0\n"
        "  cors_origins: [https://a.example.com, https://b.example.com]\n")


def test_the_file_beats_the_default(tmp_path: Path, started: list[Json], monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = built_project(tmp_path, FILE)
    assert run(root, monkeypatch, capsys, "serve", "out")[0] == 0
    assert started[-1] == {"dir": "out", "host": "0.0.0.0", "port": 8123, "public_url": "https://arch.example.com",
                           "origins": ["https://a.example.com", "https://b.example.com"]}


def test_each_option_beats_the_file(tmp_path: Path, started: list[Json], monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = built_project(tmp_path, FILE)
    assert run(root, monkeypatch, capsys, "serve", "out", "-p", "9001")[0] == 0
    assert (started[-1]["port"], started[-1]["host"]) == (9001, "0.0.0.0")
    assert run(root, monkeypatch, capsys, "serve", "out", "--host", "127.0.0.1")[0] == 0
    assert (started[-1]["port"], started[-1]["host"]) == (8123, "127.0.0.1")
    assert run(root, monkeypatch, capsys, "serve", "out", "--public-url", "http://localhost:9/x/")[0] == 0
    assert started[-1]["public_url"] == "http://localhost:9/x"
    # --cors-origin REPLACES the file's list; it does not add to it.
    assert run(root, monkeypatch, capsys, "serve", "out", "--cors-origin", "https://c.example.com")[0] == 0
    assert started[-1]["origins"] == ["https://c.example.com"]


def test_bad_values_stop_serve_with_the_option_wording(tmp_path: Path, started: list[Json],
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    root = built_project(tmp_path, "serve: {public_url: '${URL}', port: 70000}\n")
    code, _, err = run(root, monkeypatch, capsys, "serve", "out")
    assert code == 2 and started == []
    assert err == "buildzr.yaml:1: serve.port: expected a whole number from 1 to 65535, got the whole number 70000\n"
    (root / "buildzr.yaml").write_text("serve: {public_url: '${URL}'}\n")
    code, _, err = run(root, monkeypatch, capsys, "serve", "out")
    assert code == 2 and err == ('buildzr.yaml:1: serve.public_url: environment variable URL is not set '
                                 '(used in "${URL}")\n')
    monkeypatch.setenv("URL", "arch.example.com")
    code, _, err = run(root, monkeypatch, capsys, "serve", "out")
    assert code == 2 and err.startswith("buildzr.yaml:1: serve.public_url: expected an http:// or https:// URL")
    monkeypatch.setenv("URL", "https://pr-7.example.com")
    assert run(root, monkeypatch, capsys, "serve", "out")[0] == 0
    assert started[-1]["public_url"] == "https://pr-7.example.com"
    for argv, msg in ((["-p", "0"], "--port: expected a whole number from 1 to 65535, got 0"),
                      (["-p", "65536"], "--port: expected a whole number from 1 to 65535, got 65536")):
        code, _, err = run(root, monkeypatch, capsys, "serve", "out", *argv)
        assert (code, err) == (2, f"buildzr: error: {msg}\n")


@pytest.mark.usefixtures("stubbed")
def test_build_never_reads_the_serve_section(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\nserve: {public_url: '${NOT_SET_ANYWHERE}'}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    code, _, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")


@pytest.mark.usefixtures("stubbed")
def test_the_public_url_of_the_file_is_in_the_links(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "serve:\n  public_url: ${PUBLIC_URL:-https://arch.example.com}/\n"
                             "  cors_origins: [https://dash.example.com]\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Shop")})
    answers: dict[str, Any] = {}

    def real(directory: str, host: str, port: int, public_url: Optional[str], origins: list[str], **kw: Any) -> None:
        srv = make_server(directory, port=0, public_url=public_url, cors_origins=origins)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            for path in ("/_buildzr/v1/workspaces", "/shop/api/v1/"):
                req = urllib.request.Request(base + path, headers={"Origin": "https://dash.example.com"})
                with urllib.request.urlopen(req) as r:
                    answers[path] = (json.loads(r.read()), r.headers.get("Access-Control-Allow-Origin"))
        finally:
            srv.shutdown()
            srv.server_close()
    monkeypatch.setattr(cli, "serve", real)
    assert run(root, monkeypatch, capsys, "serve")[0] == 0
    listed, allow = answers["/_buildzr/v1/workspaces"]
    item = listed["workspaces"][0]
    assert (item["viewerUrl"], item["apiUrl"]) == ("https://arch.example.com/shop/", "https://arch.example.com/shop/api/v1/")
    assert allow == "https://dash.example.com"
    doc, _ = answers["/shop/api/v1/"]
    assert doc["viewerUrl"] == "https://arch.example.com/shop/" and doc["publicUrlConfigured"] is True
