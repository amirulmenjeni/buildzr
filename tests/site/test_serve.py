"""``buildzr serve``: build what is stale, then serve every built workspace at ``/<name>/``."""

from __future__ import annotations

import json
import os
import shutil
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

import buildzr.site.build as build_mod
import buildzr.site.cli as cli
from buildzr.site.serve import make_server
from tests.site.test_build_all import HEAD, tree, ws
from tests.site.test_cli import fake_built, project, run, served, stubbed  # noqa: F401  (fixtures)

Json = dict[str, Any]


def out_dir(root: Path) -> Path:
    return root / ".buildzr" / "build"


def bj(root: Path, name: str) -> bytes:
    return (out_dir(root) / name / "build.json").read_bytes()


@pytest.fixture
def two(tmp_path: Path) -> Path:
    """A project with ``workspaces/a.py`` and ``workspaces/b.py`` (workspaces "A" and "B") and a helper."""
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "b.py": HEAD + ws("B"), "_helper.py": "X = 1\n"})
    return root


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    """Record which files each build runs (and so whether a build ran at all)."""
    runs: list[list[str]] = []
    real = build_mod.run_export_all

    def spy(workspace: str, out: str, **kw: Any) -> int:
        runs.append([os.path.basename(workspace)])
        return real(workspace, out, **kw)
    monkeypatch.setattr(build_mod, "run_export_all", spy)
    return runs


def files_run(runs: list[list[str]]) -> list[str]:
    return sorted(f for r in runs for f in r)


# --- build if stale ------------------------------------------------------------------------------------


@pytest.mark.usefixtures("stubbed")
def test_missing_then_unchanged_then_one_edited(two: Path, served: list[Any], counted: list[list[str]],
                                                monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(two, monkeypatch, capsys, "serve")
    assert (code, err) == (0, "")
    assert files_run(counted) == ["a.py", "b.py"] and "built .buildzr/build/a (" in out
    assert served == [(str(out_dir(two)), "127.0.0.1", 8000)]
    a_before, b_before = bj(two, "a"), bj(two, "b")

    counted.clear()
    with monkeypatch.context() as m:
        m.setattr(cli, "build_all", lambda *a, **kw: pytest.fail("nothing is stale; no build expected"))
        code, out, err = run(two, monkeypatch, capsys, "serve")
    assert (code, err, out.splitlines()[0]) == (0, "", "up to date: a, b") and counted == []

    (two / "workspaces" / "b.py").write_text(HEAD + ws("B", "Another system"))
    code, out, err = run(two, monkeypatch, capsys, "serve")
    assert (code, err) == (0, "")
    assert files_run(counted) == ["b.py"]
    assert out.splitlines()[0] == "up to date: a" and out.splitlines()[1].startswith("built .buildzr/build/b (")
    assert bj(two, "a") == a_before and bj(two, "b") != b_before


@pytest.mark.usefixtures("stubbed", "served")
def test_an_edited_helper_rebuilds_everything(two: Path, counted: list[list[str]], monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    counted.clear()
    (two / "workspaces" / "_helper.py").write_text("X = 2\n")
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    assert files_run(counted) == ["a.py", "b.py"]


@pytest.mark.usefixtures("stubbed", "served")
def test_a_new_version_or_option_rebuilds(two: Path, counted: list[list[str]], monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    counted.clear()
    monkeypatch.setattr(build_mod, "_version", lambda: "999.0")
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    assert files_run(counted) == ["a.py", "b.py"]
    counted.clear()
    (two / "buildzr.yaml").write_text("build: {viewer: false, k: 5}\n")
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    assert files_run(counted) == ["a.py", "b.py"]
    counted.clear()
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    assert counted == []


@pytest.mark.usefixtures("stubbed", "served")
def test_rebuild_and_no_build(two: Path, counted: list[list[str]], monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(two, monkeypatch, capsys, "serve", "--no-build")
    assert code == 1 and "nothing to serve" in err and counted == []
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    counted.clear()
    assert run(two, monkeypatch, capsys, "serve", "--rebuild")[0] == 0
    assert files_run(counted) == ["a.py", "b.py"]
    counted.clear()
    (two / "workspaces" / "a.py").write_text(HEAD + ws("A", "Changed"))
    assert run(two, monkeypatch, capsys, "serve", "--no-build")[0] == 0
    assert counted == []
    code, _, err = run(two, monkeypatch, capsys, "serve", "--no-build", "--rebuild")
    assert code == 2 and err == "buildzr: error: --no-build and --rebuild cannot be used together\n"


@pytest.mark.usefixtures("stubbed")
def test_a_failing_workspace_next_to_a_good_one(two: Path, served: list[Any], monkeypatch: pytest.MonkeyPatch,
                                                capfd: pytest.CaptureFixture[str]) -> None:
    (two / "workspaces" / "b.py").write_text("raise RuntimeError('boom in b')\n")
    monkeypatch.chdir(two)
    assert cli.main(["serve"]) == 0
    cap = capfd.readouterr()
    assert "built .buildzr/build/a (" in cap.out
    assert "boom in b" in cap.err and "buildzr: error: workspaces/b.py: running it failed (see the error above)" in cap.err
    assert served == [(str(out_dir(two)), "127.0.0.1", 8000)]
    (two / "workspaces" / "a.py").write_text("raise RuntimeError('boom in a')\n")
    shutil.rmtree(out_dir(two))
    assert cli.main(["serve"]) == 1
    cap = capfd.readouterr()
    assert cap.err.splitlines()[-1] == "buildzr: error: nothing to serve: .buildzr/build holds no built workspace"


@pytest.mark.usefixtures("stubbed")
def test_node_missing_is_one_line(two: Path, served: list[Any], monkeypatch: pytest.MonkeyPatch,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("BUILDZR_NODE", str(two / "no-node-here"))
    code, out, err = run(two, monkeypatch, capsys, "serve")
    assert code == 1
    assert err.splitlines() == [
        "buildzr: error: building needs Node.js 18 or newer, which was not found; install it (or set BUILDZR_NODE), "
        "or serve what is already built with --no-build",
        "buildzr: error: nothing to serve: .buildzr/build holds no built workspace"]
    assert served == []


def test_a_prebuilt_folder_needs_no_python_and_no_node(tmp_path: Path, served: list[Any],
                                                       monkeypatch: pytest.MonkeyPatch,
                                                       capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("BUILDZR_NODE", str(tmp_path / "no-node-here"))
    monkeypatch.setattr(cli, "build_all", lambda *a, **kw: pytest.fail("a built folder is served as it is"))
    fake_built(tmp_path / "public" / "shop")
    fake_built(tmp_path / "public" / "billing")
    code, out, err = run(tmp_path, monkeypatch, capsys, "serve", "public")
    assert (code, out, err) == (0, "", "") and served == [("public", "127.0.0.1", 8000)]


@pytest.mark.usefixtures("stubbed", "served")
def test_serve_one_file(two: Path, counted: list[list[str]], monkeypatch: pytest.MonkeyPatch,
                        capsys: pytest.CaptureFixture[str]) -> None:
    assert run(two, monkeypatch, capsys, "serve", "workspaces/a.py")[0] == 0
    assert files_run(counted) == ["a.py"]
    assert json.loads(bj(two, "a"))["input"]["file"] == "a.py"


@pytest.mark.usefixtures("stubbed", "served")
def test_serve_removes_nothing(two: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    tree(two / "workspaces", {"c.py": HEAD + ws("C") + ws("D")})
    assert run(two, monkeypatch, capsys, "serve")[0] == 0
    (two / "workspaces" / "b.py").unlink()
    (two / "workspaces" / "c.py").write_text(HEAD + ws("C"))
    for flags in ([], ["--rebuild"]):
        code, out, _ = run(two, monkeypatch, capsys, "serve", *flags)
        assert code == 0 and "removed" not in out
        assert sorted(os.listdir(out_dir(two))) == ["a", "b", "c", "d"]


# --- HTTP ----------------------------------------------------------------------------------------------


class Server:
    def __init__(self, folder: Path, **kw: Any) -> None:
        self.srv = make_server(str(folder), port=0, **kw)
        threading.Thread(target=self.srv.serve_forever, daemon=True).start()
        self.base = f"http://127.0.0.1:{self.srv.server_address[1]}"

    def get(self, path: str) -> tuple[int, dict[str, str], bytes]:
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *a: Any, **kw: Any) -> Optional[urllib.request.Request]:
                return None
        opener = urllib.request.build_opener(NoRedirect)
        try:
            with opener.open(self.base + path) as r:
                return r.status, dict(r.headers), r.read()
        except urllib.error.HTTPError as e:
            return e.code, dict(e.headers), e.read()

    def json(self, path: str) -> Json:
        st, _, body = self.get(path)
        assert st == 200, (path, st, body)
        data: Json = json.loads(body)
        return data

    def close(self) -> None:
        self.srv.shutdown()
        self.srv.server_close()


@pytest.fixture
def built_two(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
              stubbed: None) -> Path:  # noqa: F811
    """A build output with ``a`` (data only) and ``b`` (with a viewer), built for real with the stub layout."""
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "b.py": HEAD + ws("Big Bank")})
    static = tmp_path / "static"
    static.mkdir()
    (static / "index.html").write_text('<div id="root"></div>')
    monkeypatch.setattr(build_mod, "STATIC_DIR", str(static))
    monkeypatch.chdir(root)
    assert cli.main(["build", "-w", "workspaces/a.py"]) == 0
    from buildzr.site.build import build_all
    assert not build_all("workspaces/b.py", str(out_dir(root)), viewer=True, static_dir=str(static),
                         root=str(root / "workspaces")).failed
    capsys.readouterr()
    return out_dir(root)


@pytest.fixture
def server(built_two: Path) -> Iterator[Server]:
    s = Server(built_two)
    yield s
    s.close()


def test_two_workspaces_index_and_list(server: Server, built_two: Path) -> None:
    st, h, body = server.get("/")
    assert st == 200 and h["Content-Type"].startswith("text/html")
    assert b'href="/a/"' in body and b'href="/big-bank/"' in body and b"Big Bank" in body
    lst = server.json("/_buildzr/v1/workspaces")
    assert lst["apiVersion"] == "1"
    a, b = lst["workspaces"]
    assert (a["name"], a["path"], a["workspaceName"], a["source"]) == ("a", "/a/", "A", "a.py")
    assert a["viewerUrl"] is None and a["apiUrl"] == "/a/api/v1/" and a["llmsUrl"] == "/a/llms.txt"
    assert b["viewerUrl"] == "/big-bank/" and b["modelHash"].startswith("sha256:")
    assert a["builtAt"].endswith("Z")
    assert server.get("/_buildzr/v1/workspaces/")[0] == 200
    assert server.get("/_buildzr/v1/sites")[0] == 404


def test_each_workspace_has_its_api_and_llms(server: Server) -> None:
    doc = server.json("/a/api/v1/")
    assert doc["name"] == "A" and doc["endpoints"]["element"] == "/a/api/v1/element?id={id}"
    assert doc["viewerUrl"] is None and doc["notes"] == ["This workspace has no viewer, so viewerUrl is null everywhere."]
    assert server.json("/big-bank/api/v1/")["viewerUrl"] == "/big-bank/"
    st, _, body = server.get("/big-bank/llms.txt")
    assert st == 200 and b"/big-bank/api/v1/" in body
    assert server.get("/a/api/v1")[0] == 301 and server.get("/a")[0] == 308
    assert server.get("/a/api/v1/nope")[0] == 404
    assert server.get("/big-bank/")[0] == 200 and server.get("/a/")[0] == 404  # data only: no index.html


def test_one_workspace_redirects_and_none_is_an_empty_index(built_two: Path) -> None:
    shutil.rmtree(built_two / "big-bank")
    s = Server(built_two)
    try:
        st, h, _ = s.get("/")
        assert st == 302 and h["Location"] == "/a/"
        shutil.rmtree(built_two / "a")
        st, _, body = s.get("/")
        assert st == 200 and b"No built workspace here yet" in body
        assert s.json("/_buildzr/v1/workspaces")["workspaces"] == []
    finally:
        s.close()


def test_a_workspace_added_after_start_appears(server: Server, built_two: Path) -> None:
    assert server.get("/c/build.json")[0] == 404
    fake_built(built_two / "c")
    assert server.get("/c/build.json")[0] == 200  # an unknown name makes the server look again
    assert [w["name"] for w in server.json("/_buildzr/v1/workspaces")["workspaces"]] == ["a", "big-bank", "c"]
    shutil.rmtree(built_two / "c")
    assert [w["name"] for w in server.json("/_buildzr/v1/workspaces")["workspaces"]] == ["a", "big-bank"]


def test_a_half_written_workspace_is_not_served(server: Server, built_two: Path) -> None:
    half = built_two / "half"
    (half / "data").mkdir(parents=True)
    (half / "data" / "index.json").write_text("{}")  # no build.json yet
    assert server.get("/half/data/index.json")[0] == 404
    assert "half" not in [w["name"] for w in server.json("/_buildzr/v1/workspaces")["workspaces"]]
    (built_two / "a" / "build.json").rename(built_two / "a" / "build.json.moved")  # mid-replace
    assert server.get("/a/data/index.json")[0] == 404
    (built_two / "a" / "build.json.moved").rename(built_two / "a" / "build.json")
    assert server.get("/a/data/index.json")[0] == 200
    assert server.get("/.build-x/build.json")[0] == 404  # the build's temporary folders are never served


@pytest.mark.usefixtures("stubbed")
def test_a_rebuild_while_serving_swaps_the_workspace(server: Server, built_two: Path,
                                                     monkeypatch: pytest.MonkeyPatch) -> None:
    before = server.json("/a/api/v1/")["modelHash"]
    root = built_two.parent.parent
    (root / "workspaces" / "a.py").write_text(HEAD + ws("A", "Grown system") + "    SoftwareSystem('Second')\n")
    assert cli.main(["build", "-w", "workspaces/a.py"]) == 0
    after = server.json("/a/api/v1/")
    assert after["modelHash"] != before and after["counts"]["elements"] == 2


def test_public_url_is_the_base_of_the_links(built_two: Path) -> None:
    s = Server(built_two, public_url="https://arch.example.com/docs")
    try:
        b = s.json("/_buildzr/v1/workspaces")["workspaces"][1]
        assert b["viewerUrl"] == "https://arch.example.com/docs/big-bank/"
        assert b["apiUrl"] == "https://arch.example.com/docs/big-bank/api/v1/"
        assert s.json("/big-bank/api/v1/")["viewerUrl"] == "https://arch.example.com/docs/big-bank/"
        assert s.get("/")[0] == 200
    finally:
        s.close()


def test_the_list_is_read_only_and_cached(server: Server) -> None:
    st, h, _ = server.get("/_buildzr/v1/workspaces")
    req = urllib.request.Request(server.base + "/_buildzr/v1/workspaces", headers={"If-None-Match": h["ETag"]})
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req)
    assert ei.value.code == 304
    req = urllib.request.Request(server.base + "/_buildzr/v1/workspaces", data=b"{}", method="POST")
    with pytest.raises(urllib.error.HTTPError) as ei:
        urllib.request.urlopen(req)
    assert ei.value.code == 405 and ei.value.headers["Allow"] == "GET, HEAD"
    assert server.get("/_buildzr/v1/other")[0] == 404
