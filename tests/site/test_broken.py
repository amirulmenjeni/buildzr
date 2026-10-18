"""Broken workspaces: the build checks its own output, writes a broken built workspace when the workspace is at
fault and keeps the old output when the machine is. ``test_serve_broken`` covers what ``serve`` shows."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

import buildzr.site.build as build_mod
from buildzr.site.build import build_all
from buildzr.site.layout.elk import ElkEnvironmentError
from tests.site.stub_layout import stub_layout
from tests.site.test_build_all import HEAD, built, info, tree, ws
from tests.site.test_cli import WS_TEXT, project, run, stubbed  # noqa: F401  (fixture)

Json = dict[str, Any]
SCHEMA = json.loads((Path(build_mod.__file__).parent / "schema" / "build.schema.json").read_text(encoding="utf-8"))


def out_dir(root: Path) -> Path:
    return root / ".buildzr" / "build"


def static(tmp_path: Path) -> str:
    d = tmp_path / "static"
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text('<div id="root"></div>')
    (d / "assets" / "v.js").write_text("1")
    return str(d)


def errors_of(root: Path, name: str) -> list[str]:
    errors = info(root, name)["errors"]
    assert isinstance(errors, list)
    return [str(e) for e in errors]


def schema_errors(data: Json) -> list[str]:
    return [e.message for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(data)]


def small_project(tmp_path: Path) -> Path:
    """A project whose ``workspaces/small.py`` makes the small workspace: the stub layout fits it, so it passes."""
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"small.py": WS_TEXT})
    return root


def damaging(data_dir: str) -> None:
    """Break the laid-out data the way a layout bug would: a scene loses its landscape entry."""
    with open(os.path.join(data_dir, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    del index["scenes"]["landscape"]
    with open(os.path.join(data_dir, "index.json"), "w", encoding="utf-8") as f:
        json.dump(index, f)


@pytest.fixture
def real_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """The stub layout and the REAL checker, for the small workspace only."""
    monkeypatch.setattr(build_mod, "_default_layout", lambda: stub_layout)
    monkeypatch.setenv("PYTHONPATH", os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))


# --- the three stages ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("real_check")
def test_a_check_failure_writes_the_data_and_replaces_the_old_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                     capsys: pytest.CaptureFixture[str]) -> None:
    root = small_project(tmp_path)
    code, out, err = run(root, monkeypatch, capsys, "build", "--no-viewer")
    assert (code, err) == (0, "") and info(root, "small-fixture")["status"] == "ok"
    old_hash = info(root, "small-fixture")["modelHash"]

    def bad_layout(levels: Json, model: Json, data_dir: str, k: int = 4) -> None:
        stub_layout(levels, model, data_dir, k=k)
        damaging(data_dir)
    monkeypatch.setattr(build_mod, "_default_layout", lambda: bad_layout)
    code, out, err = run(root, monkeypatch, capsys, "build", "--no-viewer")
    assert code == 1 and "built " not in out
    bj = info(root, "small-fixture")
    assert (bj["status"], bj["stage"]) == ("broken", "check")
    assert "index.json: no landscape scene" in errors_of(root, "small-fixture")
    assert all("/tmp" not in e and ".build-" not in e for e in errors_of(root, "small-fixture"))
    assert bj["modelHash"] == old_hash  # same model; the data is there to look at
    assert (out_dir(root) / "small-fixture" / "data" / "index.json").is_file()
    assert schema_errors(bj) == []
    assert err.startswith("buildzr: BROKEN: workspace small-fixture (workspaces/small.py) failed at the check step\n")
    assert "    index.json: no landscape scene\n" in err
    assert err.endswith("  this workspace is broken; the viewer says so\n")


@pytest.mark.usefixtures("stubbed")
def test_a_layout_failure_breaks_that_workspace_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Fine") + ws("Tangled")})

    def layout(levels: Json, model: Json, data_dir: str, k: int = 4) -> None:
        if model["workspace"]["name"] == "Tangled":
            raise ValueError("header band of x does not converge")
        stub_layout(levels, model, data_dir, k=k)
    monkeypatch.setattr(build_mod, "_default_layout", lambda: layout)
    out = out_dir(root)
    result = build_all(str(root / "workspaces"), str(out), static_dir=static(tmp_path))
    assert [b.name for b in result.built] == ["fine"] and [b.name for b in result.broken] == ["tangled"]
    assert result.failed == []
    bj = info(root, "tangled")
    assert (bj["status"], bj["stage"], bj["errors"]) == ("broken", "layout", ["ValueError: header band of x does not converge"])
    assert "modelHash" not in bj and schema_errors(bj) == []
    assert sorted(os.listdir(out / "tangled")) == ["assets", "build.json", "index.html"]  # the viewer, no data
    assert info(root, "fine")["status"] == "ok" and (out / "fine" / "data" / "index.json").is_file()
    code, _, err = run(root, monkeypatch, capsys, "build")
    assert code == 1 and "failed at the layout step" in err


@pytest.mark.usefixtures("stubbed")
def test_a_model_error_with_and_without_the_viewer(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Shop")})
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    (root / "workspaces" / "a.py").write_text(HEAD + "raise KeyError('no such system')\n")
    assert run(root, monkeypatch, capsys, "build")[0] == 1
    assert sorted(os.listdir(out_dir(root) / "shop")) == ["assets", "build.json", "index.html"]
    bj = info(root, "shop")
    assert (bj["status"], bj["stage"], bj["workspace"]) == ("broken", "model", "Shop")
    assert bj["errors"] == ["KeyError: 'no such system'", "a.py, line 2: raise KeyError('no such system')"]
    assert schema_errors(bj) == []
    assert run(root, monkeypatch, capsys, "build", "--no-viewer")[0] == 1
    assert os.listdir(out_dir(root) / "shop") == ["build.json"]


@pytest.mark.usefixtures("stubbed")
def test_errors_are_capped(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Shop")})
    monkeypatch.setattr(build_mod, "check_workspace", lambda d: [f"scene {i}: " + "x" * 900 for i in range(70)])
    code, _, err = run(root, monkeypatch, capsys, "build", "--no-viewer")
    errors = errors_of(root, "shop")
    assert code == 1 and len(errors) == 50 and all(len(e) == 500 for e in errors)
    assert err.count("\n    scene ") == 10 and "    ... and 40 more in .buildzr/build/shop/build.json\n" in err


# --- the machine at fault ------------------------------------------------------------------------------


@pytest.mark.usefixtures("stubbed")
def test_node_missing_keeps_the_old_output_and_writes_no_broken_workspace(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("One") + ws("Two")})
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    before = {n: (out_dir(root) / n / "build.json").read_bytes() for n in ("one", "two")}
    tree(root / "workspaces", {"a.py": HEAD + ws("One", "Changed") + ws("Two", "Changed")})
    calls: list[str] = []

    def no_node(levels: Json, model: Json, data_dir: str, k: int = 4) -> None:
        calls.append(model["workspace"]["name"])
        raise ElkEnvironmentError("Node.js was not found")
    monkeypatch.setattr(build_mod, "_default_layout", lambda: no_node)
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 1 and out == "" and "BROKEN" not in err
    assert calls == ["One"]  # the second workspace is not tried: it would fail the same way
    assert err.splitlines() == [
        f'buildzr: error: workspaces/a.py (workspace "{n}"): ElkEnvironmentError: Node.js was not found; nothing was '
        "written and the previous output is kept" for n in ("One", "Two")]
    assert {n: (out_dir(root) / n / "build.json").read_bytes() for n in ("one", "two")} == before


@pytest.mark.usefixtures("stubbed")
def test_a_full_disk_keeps_the_old_output(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                          capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("One")})
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    before = (out_dir(root) / "one" / "build.json").read_bytes()

    def full(*a: Any, **kw: Any) -> None:
        raise OSError(28, "No space left on device")
    monkeypatch.setattr(build_mod, "_publish", full)
    code, _, err = run(root, monkeypatch, capsys, "build")
    assert code == 1 and "No space left on device" in err and "BROKEN" not in err
    assert (out_dir(root) / "one" / "build.json").read_bytes() == before
    assert [n for n in os.listdir(out_dir(root)) if n.startswith(".")] == []  # no temporary folder left


# --- the orphan guard ----------------------------------------------------------------------------------


@pytest.mark.usefixtures("stubbed")
def test_a_build_of_another_folder_never_removes_this_folders_workspaces(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A")})
    tree(root / "other" / "folder", {"x.py": HEAD + ws("X")})
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    assert info(root, "a")["workspacesFolder"] == "../../workspaces"
    # Seen from other/folder, "a.py" does not exist; the guard keeps "a" because it was built from workspaces/.
    code, out, _ = run(root, monkeypatch, capsys, "build", "-w", "other/folder")
    assert code == 0 and "removed" not in out and built(root) == ["a", "x"]
    assert info(root, "x")["workspacesFolder"] == "../../other/folder"
    shutil.rmtree(root / "other")
    code, out, _ = run(root, monkeypatch, capsys, "build")  # and the real folder never removes "x" either
    assert code == 0 and "removed" not in out and built(root) == ["a", "x"]


# --- build.json ----------------------------------------------------------------------------------------


GOOD: Json = {"buildzr": "0.0.35", "elkjs": "0.11.0", "k": 4, "textColor": "wcag", "name": "shop", "workspace": "Shop",
              "workspaces": ["shop"], "input": {"file": "shop.py", "sha256": "sha256:" + "a" * 64},
              "fingerprint": "sha256:" + "b" * 64, "workspacesFolder": "../../workspaces", "status": "ok",
              "modelHash": "sha256:" + "c" * 64}


@pytest.mark.parametrize("change, valid", [
    ({}, True),
    ({"status": "broken", "stage": "check", "errors": ["x"]}, True),
    ({"status": "broken", "stage": "model", "errors": ["x"], "modelHash": None}, True),
    ({"status": "broken", "stage": "model", "errors": ["x"]}, False),  # no data, so no modelHash
    ({"status": "broken", "stage": "check"}, False),  # errors are required
    ({"status": "broken", "stage": "check", "errors": []}, False),
    ({"status": "broken", "stage": "check", "errors": ["x"] * 51}, False),
    ({"status": "broken", "stage": "check", "errors": ["x" * 501]}, False),
    ({"status": "broken", "stage": "deploy", "errors": ["x"]}, False),
    ({"stage": "check"}, False),  # ok has no stage
    ({"status": "fine"}, False),
    ({"modelHash": None}, False),  # ok needs modelHash
    ({"workspacesFolder": None}, False),
    ({"extra": 1}, False),
])
def test_build_json_schema(change: Json, valid: bool) -> None:
    data = {k: v for k, v in {**GOOD, **change}.items() if v is not None}
    assert (schema_errors(data) == []) is valid, schema_errors(data)


@pytest.mark.usefixtures("real_check")
def test_an_ok_build_json_matches_the_schema(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    root = small_project(tmp_path)
    assert run(root, monkeypatch, capsys, "build", "--no-viewer")[0] == 0
    bj = info(root, "small-fixture")
    assert bj["status"] == "ok" and schema_errors(bj) == []
