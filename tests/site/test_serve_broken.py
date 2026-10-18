"""``buildzr serve`` and broken workspaces: what the index, the list, the Model API and the console show."""

from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any, Iterator

import pytest

import buildzr.site.build as build_mod
from buildzr.site.build import build_all
from tests.site.stub_layout import stub_layout
from tests.site.test_broken import Json, damaging, out_dir, static
from tests.site.test_build_all import HEAD, info, tree, ws
from tests.site.test_cli import WS_TEXT, project, run, served, stubbed  # noqa: F401  (fixtures)
from tests.site.test_serve import Server, files_run


@pytest.fixture
def counted(monkeypatch: pytest.MonkeyPatch) -> list[list[str]]:
    runs: list[list[str]] = []
    real = build_mod.run_export_all

    def spy(workspace: str, out: str, **kw: Any) -> int:
        runs.append([os.path.basename(workspace)])
        return real(workspace, out, **kw)
    monkeypatch.setattr(build_mod, "run_export_all", spy)
    return runs


@pytest.mark.usefixtures("stubbed", "served")
def test_serve_does_not_rebuild_the_same_broken_input(tmp_path: Path, counted: list[list[str]],
                                                      monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "b.py": "raise RuntimeError('boom in b')\n"})
    assert run(root, monkeypatch, capsys, "serve")[0] == 0
    assert files_run(counted) == ["a.py", "b.py"]
    code, out, err = run(root, monkeypatch, capsys, "serve")
    assert files_run(counted) == ["a.py", "b.py"]  # nothing ran again
    assert "up to date: a, b" in out and "buildzr: BROKEN: workspace b (workspaces/b.py) failed at the model step" in err
    assert run(root, monkeypatch, capsys, "serve", "--rebuild")[0] == 0
    assert files_run(counted) == ["a.py", "a.py", "b.py", "b.py"]
    (root / "workspaces" / "b.py").write_text(HEAD + ws("B"))  # fixed
    code, out, err = run(root, monkeypatch, capsys, "serve")
    assert "BROKEN" not in err and info(root, "b")["status"] == "ok"


# --- serve ---------------------------------------------------------------------------------------------


@pytest.fixture
def mixed(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> Iterator[Server]:
    """A build output with ``fine`` (ok), ``tangled`` (broken at the layout, no data) and ``small-fixture``
    (broken at the check, with data)."""
    monkeypatch.setenv("PYTHONPATH", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Fine") + ws("Tangled"), "small.py": WS_TEXT})

    def layout(levels: Json, model: Json, data_dir: str, k: int = 4) -> None:
        if model["workspace"]["name"] == "Tangled":
            raise ValueError("header band of x does not converge")
        stub_layout(levels, model, data_dir, k=k)
        if model["workspace"]["name"] == "Small fixture":
            damaging(data_dir)
    real = build_mod.check_workspace

    def check(data_dir: str) -> list[str]:  # the real checker for the small workspace, the only one the stub fits
        with open(os.path.join(data_dir, "index.json"), encoding="utf-8") as f:
            model_file = json.load(f)["model"]["file"]
        with open(os.path.join(data_dir, model_file), encoding="utf-8") as f:
            small = json.load(f)["workspace"]["name"] == "Small fixture"
        return real(data_dir) if small else []
    monkeypatch.setattr(build_mod, "check_workspace", check)
    result = build_all(str(root / "workspaces"), str(out_dir(root)), layout_fn=layout, static_dir=static(tmp_path))
    assert sorted(b.name for b in result.broken) == ["small-fixture", "tangled"]
    s = Server(out_dir(root))
    yield s
    s.close()


def test_the_index_marks_broken_workspaces(mixed: Server) -> None:
    st, _, body = mixed.get("/")
    page = body.decode()
    assert st == 200
    assert ('<li><a href="/tangled/">tangled</a> &middot; Tangled <strong class="broken">broken</strong> at the layout '
            "step: <code>ValueError: header band of x does not converge</code></li>") in page
    assert '<a href="/small-fixture/">small-fixture</a>' in page and "at the check step: <code>" in page
    assert '<a href="/fine/">fine</a> &middot; Fine <small>' in page
    assert page.count('class="broken"') == 2 and ".broken{color:#b00020}" in page


def test_the_list_has_status_stage_and_errors(mixed: Server) -> None:
    items = {w["name"]: w for w in mixed.json("/_buildzr/v1/workspaces")["workspaces"]}
    assert items["fine"]["status"] == "ok" and "stage" not in items["fine"] and "errors" not in items["fine"]
    t = items["tangled"]
    assert (t["status"], t["stage"], t["errors"], t["modelHash"]) == (
        "broken", "layout", ["ValueError: header band of x does not converge"], None)
    assert t["viewerUrl"] == "/tangled/"
    s = items["small-fixture"]
    assert (s["status"], s["stage"]) == ("broken", "check") and s["modelHash"].startswith("sha256:")
    assert 1 <= len(s["errors"]) <= 10


def test_a_broken_workspace_without_data_answers_503(mixed: Server) -> None:
    for path in ("/tangled/api/v1/", "/tangled/api/v1/elements", "/tangled/api/v1/element?id=x"):
        st, h, body = mixed.get(path)
        problem = json.loads(body)
        assert st == 503 and h["Content-Type"] == "application/problem+json"
        assert (problem["code"], problem["stage"], problem["errors"]) == (
            "workspace-broken", "layout", ["ValueError: header band of x does not converge"])
        assert problem["detail"] == ("building this workspace failed at the layout step, so it has no model data: "
                                     "ValueError: header band of x does not converge")
        assert "Traceback" not in body.decode() and "File " not in body.decode()
    st, _, body = mixed.get("/tangled/llms.txt")
    assert st == 503 and body.decode().startswith("Workspace broken: building this workspace failed at the layout step")
    st, _, body = mixed.get("/tangled/")
    assert st == 200  # the viewer, which shows the broken screen


def test_a_broken_workspace_with_data_says_so_in_its_api(mixed: Server) -> None:
    doc = mixed.json("/small-fixture/api/v1/")
    assert (doc["status"], doc["stage"]) == ("broken", "check") and doc["errors"]
    assert doc["notes"][-1].startswith("This workspace is broken: building it failed at the check step.")
    assert mixed.json("/small-fixture/api/v1/elements")["total"] > 0  # the data is still answered
    assert mixed.json("/fine/api/v1/")["status"] == "ok" and "errors" not in mixed.json("/fine/api/v1/")
    st, _, body = mixed.get("/small-fixture/llms.txt")
    assert st == 200 and "> WARNING: this workspace is broken" in body.decode()


@pytest.mark.usefixtures("stubbed")
def test_one_broken_workspace_still_redirects(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": "raise RuntimeError('boom')\n"})
    assert run(root, monkeypatch, capsys, "build")[0] == 1
    s = Server(out_dir(root))
    try:
        st, h, _ = s.get("/")
        assert (st, h["Location"]) == (302, "/a/api/v1/")  # data only: the API, which says it is broken
        assert s.get("/a/api/v1/")[0] == 503
    finally:
        s.close()


@pytest.mark.usefixtures("stubbed")
def test_serve_prints_the_block_for_a_prebuilt_broken_workspace(tmp_path: Path, served: list[Any],
                                                                monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "b.py": "raise RuntimeError('boom')\n"})
    assert run(root, monkeypatch, capsys, "build")[0] == 1
    code, out, err = run(root, monkeypatch, capsys, "serve", ".buildzr/build")
    assert code == 0 and served
    assert err == ("buildzr: BROKEN: workspace b (workspaces/b.py) failed at the model step\n"
                   "    RuntimeError: boom\n    b.py, line 1: raise RuntimeError('boom')\n"
                   "  this workspace is broken; the viewer says so\n")
