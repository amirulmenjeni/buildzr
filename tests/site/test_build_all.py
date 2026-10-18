"""``buildzr build`` over a workspaces folder: every workspace of every file, the naming rule, collisions, failures."""

from __future__ import annotations

import json
import os
from pathlib import Path

import pytest

from buildzr.site.build import RESERVED_NAMES, check_name, find_helpers, find_sources, safe_name
from tests.site.test_cli import project, run, stubbed  # noqa: F401  (fixture)

pytestmark = pytest.mark.usefixtures("stubbed")


def ws(name: str, system: str = "System") -> str:
    """Python text that creates one small workspace called ``name``."""
    return (f"with Workspace({name!r}) as w:\n"
            f"    SoftwareSystem({system!r})\n")


HEAD = "from buildzr.dsl import Workspace, SoftwareSystem\n"


def tree(root: Path, files: dict[str, str]) -> None:
    for rel, text in files.items():
        p = root / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(text)


def built(root: Path, out: str = ".buildzr/build") -> list[str]:
    d = root / out
    return sorted(n for n in os.listdir(d) if not n.startswith(".")) if d.is_dir() else []


def info(root: Path, name: str) -> dict[str, object]:
    data: dict[str, object] = json.loads((root / ".buildzr" / "build" / name / "build.json").read_text(encoding="utf-8"))
    return data


def test_every_workspace_of_every_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {
        "two.py": HEAD + ws("Shop") + ws("Billing"),
        "nested/deeper/three.py": HEAD + ws("Payments Platform"),
    })
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert built(root) == ["billing", "payments-platform", "shop"]
    assert [l.split(" (")[0] for l in out.splitlines()] == [
        "built .buildzr/build/payments-platform", "built .buildzr/build/shop", "built .buildzr/build/billing"]
    bj = info(root, "billing")
    assert bj["input"] == {"file": "two.py", "sha256": bj["input"]["sha256"]}  # type: ignore[index]
    assert (bj["name"], bj["workspace"], bj["workspaces"]) == ("billing", "Billing", ["shop", "billing"])
    assert str(bj["fingerprint"]).startswith("sha256:")
    assert info(root, "payments-platform")["input"]["file"] == "nested/deeper/three.py"  # type: ignore[index]


def test_helpers_and_files_without_a_workspace(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {
        "_shared.py": "raise SystemExit('a helper is never run on its own')\n",
        ".hidden.py": "raise SystemExit('hidden')\n",
        "_private/model.py": "raise SystemExit('folders starting with _ are skipped')\n",
        "notes.py": "NOTE = 'creates nothing'\n",
        "shop.py": "import sys, os\nsys.path.insert(0, os.path.dirname(__file__))\n"
                   "from _shared_names import NAME\n" + HEAD + "with Workspace(NAME) as w:\n    SoftwareSystem('S')\n",
        "_shared_names.py": "NAME = 'Shop'\n",
    })
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert built(root) == ["shop"]
    assert "skipped workspaces/notes.py: it creates no workspace\n" in out


def test_a_folder_with_no_workspace_at_all_fails(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    tree(root / "workspaces", {"notes.py": "x = 1\n"})
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 1
    assert err == "buildzr: error: no workspace found in workspaces: no .py file there creates a Workspace\n"


def test_two_workspaces_with_one_name_stop_the_build(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Shop"), "b/c.py": HEAD + ws("SHOP"), "d.py": HEAD + ws("Other")})
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 1 and out == ""
    assert err == ('buildzr: error: two workspaces would both be built as "shop": "Shop" in a.py and "SHOP" in b/c.py '
                   f"(paths in {root / 'workspaces'}); rename one of them\n")
    assert built(root) == []  # nothing written


def test_reserved_names_fail_that_workspace_only(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("API") + ws("Shop")})
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 1
    assert built(root) == ["shop"]
    assert err.startswith('buildzr: error: workspaces/a.py (workspace "API"): the name "api" is reserved')


def test_a_failing_file_next_to_a_good_one(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           capfd: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"good.py": HEAD + ws("Good"), "bad.py": HEAD + ws("Bad")})
    monkeypatch.chdir(root)
    from buildzr.site.cli import main
    assert main(["build"]) == 0
    before = (root / ".buildzr" / "build" / "bad" / "build.json").read_bytes()
    good_before = (root / ".buildzr" / "build" / "good" / "build.json").read_bytes()
    capfd.readouterr()
    (root / "workspaces" / "bad.py").write_text("raise RuntimeError('boom in bad')\n")
    (root / "workspaces" / "good.py").write_text(HEAD + ws("Good", "Changed system"))
    assert main(["build"]) == 1
    cap = capfd.readouterr()
    assert "boom in bad" in cap.err and "buildzr: error: workspaces/bad.py: running it failed (see the error above)" in cap.err
    assert "built .buildzr/build/good (" in cap.out
    assert (root / ".buildzr" / "build" / "bad" / "build.json").read_bytes() == before  # untouched
    assert (root / ".buildzr" / "build" / "good" / "build.json").read_bytes() != good_before  # rebuilt


def test_a_renamed_workspace_replaces_its_old_folder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                     capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("Old"), "b.py": HEAD + ws("Kept")})
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    (root / "workspaces" / "a.py").write_text(HEAD + ws("New"))
    assert run(root, monkeypatch, capsys, "build")[0] == 0
    assert built(root) == ["kept", "new"]


def test_one_file_with_w(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {viewer: false}\n", ws=False)
    tree(root / "workspaces", {"a.py": HEAD + ws("A"), "sub/b.py": HEAD + ws("B")})
    code, out, _ = run(root, monkeypatch, capsys, "build", "-w", "workspaces/sub/b.py")
    assert code == 0 and built(root) == ["b"]
    assert info(root, "b")["input"]["file"] == "sub/b.py"  # type: ignore[index]  # relative to the workspaces folder


@pytest.mark.parametrize("name, expected", [
    ("Shop", "shop"), ("Big Bank plc", "big-bank-plc"), ("  --Über Café", "ber-caf-"), ("a.b_c-d", "a.b_c-d"),
    ("", "stem"), ("!!!", "stem"), ("x" * 80, "x" * 64), ("_buildzr", "buildzr"),
])
def test_safe_name(name: str, expected: str) -> None:
    assert safe_name(name, "stem") == expected


def test_reserved_names() -> None:
    for name in RESERVED_NAMES:
        assert check_name(name) is not None
    assert check_name("shop") is None
    assert safe_name("", "_") == "workspace"


def test_sources_and_helpers(tmp_path: Path) -> None:
    tree(tmp_path, {"b.py": "", "a/z.py": "", "a/_h.py": "", "_x.py": "", ".h/y.py": "", "__pycache__/c.py": "",
                    "a/__init__.py": "", "notes.txt": ""})
    assert [os.path.relpath(p, tmp_path) for p in find_sources(str(tmp_path))] == ["a/z.py", "b.py"]
    assert [os.path.relpath(p, tmp_path) for p in find_helpers(str(tmp_path))] == ["_x.py", "a/__init__.py", "a/_h.py"]
