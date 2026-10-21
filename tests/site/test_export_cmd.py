"""``buildzr export``: the workspaces of a model file as JSON, PlantUML, SVG and PNG files."""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from buildzr.site import export_files

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

ONE = """\
from buildzr.dsl import *
with Workspace('Shop', implied_relationships=True) as w:
    user = Person('User')
    app = SoftwareSystem('App')
    user >> 'uses' >> app
    SystemContextView(app, key='ctx', description='ctx')
"""

TWO = ONE + """\
with Workspace('Billing') as b:
    SoftwareSystem('Ledger')
with Workspace('Shop') as again:
    SoftwareSystem('Other')
"""


def cli(*argv: str, cwd: Path, env: dict[str, str] | None = None) -> subprocess.CompletedProcess[str]:
    """Run ``buildzr`` the way a shell does, in ``cwd``, and capture both streams."""
    e = dict(os.environ)
    e["PYTHONPATH"] = ROOT + os.pathsep + e.get("PYTHONPATH", "")
    e.update(env or {})
    return subprocess.run([sys.executable, "-m", "buildzr.site.cli", *argv], cwd=cwd, env=e,
                          capture_output=True, text=True)


@pytest.fixture
def model(tmp_path: Path) -> Path:
    p = tmp_path / "model.py"
    p.write_text(ONE)
    return p


@pytest.fixture
def many(tmp_path: Path) -> Path:
    p = tmp_path / "many.py"
    p.write_text(TWO)
    return p


def names(out: Path) -> list[str]:
    return sorted(p.name for p in out.iterdir())


# --- JSON, the default format ---------------------------------------------------------------------------------------


def test_json_is_the_default_and_goes_into_a_folder_per_workspace(tmp_path: Path, model: Path) -> None:
    r = cli("export", "model.py", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    data = json.loads((tmp_path / "export" / "shop" / "workspace.json").read_text())
    assert data["name"] == "Shop"
    assert data["views"]["systemContextViews"][0]["key"] == "ctx"
    assert r.stdout.splitlines()[-1] == f"wrote {os.path.join('export', 'shop', 'workspace.json')}"


def test_json_matches_to_json_and_pretty_indents(tmp_path: Path, model: Path) -> None:
    assert cli("export", "model.py", "-o", "compact", cwd=tmp_path).returncode == 0
    assert cli("export", "model.py", "-o", "pretty", "--pretty", cwd=tmp_path).returncode == 0
    compact = (tmp_path / "compact" / "shop" / "workspace.json").read_text()
    pretty = (tmp_path / "pretty" / "shop" / "workspace.json").read_text()
    assert "\n" not in compact.strip()
    assert pretty.count("\n") > 10
    assert json.loads(compact) == json.loads(pretty)


# --- which workspaces -----------------------------------------------------------------------------------------------


def test_every_workspace_of_the_file_is_exported_and_shared_names_are_numbered(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    out = tmp_path / "export"
    assert names(out) == ["billing", "shop", "shop-2"]
    assert json.loads((out / "shop-2" / "workspace.json").read_text())["model"]["softwareSystems"][0]["name"] == "Other"


def test_workspace_by_name(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "--workspace", "Billing", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert names(tmp_path / "export") == ["billing"]


def test_workspace_by_index(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "--index", "2", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert names(tmp_path / "export") == ["shop"]
    data = json.loads((tmp_path / "export" / "shop" / "workspace.json").read_text())
    assert data["model"]["softwareSystems"][0]["name"] == "Other"


def test_unknown_workspace_lists_what_the_file_creates(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "--workspace", "Nope", cwd=tmp_path)
    assert r.returncode == 2
    assert "0: Shop, 1: Billing, 2: Shop" in r.stderr
    assert not (tmp_path / "export").exists()


def test_a_name_two_workspaces_share_needs_an_index(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "--workspace", "Shop", cwd=tmp_path)
    assert r.returncode == 2
    assert "--index" in r.stderr
    assert not (tmp_path / "export").exists()


def test_index_out_of_range(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "--index", "3", cwd=tmp_path)
    assert r.returncode == 2
    assert "creates 3 workspaces" in r.stderr


def test_workspace_and_index_conflict_and_negative_index(tmp_path: Path, many: Path) -> None:
    assert cli("export", "many.py", "--workspace", "Billing", "--index", "1", cwd=tmp_path).returncode == 2
    assert cli("export", "many.py", "--index", "-1", cwd=tmp_path).returncode == 2


# --- problems with the file -----------------------------------------------------------------------------------------


def test_missing_file_and_folder_are_usage_errors(tmp_path: Path) -> None:
    r = cli("export", "nope.py", cwd=tmp_path)
    assert (r.returncode, "nope.py not found" in r.stderr) == (2, True)
    (tmp_path / "dir").mkdir()
    r = cli("export", "dir", cwd=tmp_path)
    assert (r.returncode, "is a folder" in r.stderr) == (2, True)


def test_a_file_without_a_workspace_fails(tmp_path: Path) -> None:
    (tmp_path / "empty.py").write_text("x = 1\n")
    r = cli("export", "empty.py", cwd=tmp_path)
    assert r.returncode == 1
    assert "creates no workspace" in r.stderr
    assert not (tmp_path / "export").exists()


def test_a_file_that_raises_writes_nothing(tmp_path: Path) -> None:
    (tmp_path / "bad.py").write_text(ONE + "raise RuntimeError('boom')\n")
    r = cli("export", "bad.py", cwd=tmp_path)
    assert r.returncode == 1
    assert "RuntimeError: boom" in r.stderr
    assert "nothing was exported" in r.stderr
    assert not (tmp_path / "export").exists()


def test_a_model_file_that_still_calls_save_neither_writes_into_the_project_nor_warns(tmp_path: Path) -> None:
    (tmp_path / "old.py").write_text(ONE + "w.save(path='legacy.json')\n")
    r = cli("export", "old.py", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert not (tmp_path / "legacy.json").exists()
    assert "deprecated" not in r.stderr.lower()


def test_unknown_format_is_a_usage_error(tmp_path: Path, model: Path) -> None:
    r = cli("export", "model.py", "-f", "pdf", cwd=tmp_path)
    assert r.returncode == 2
    assert "invalid choice" in r.stderr


# --- the help and the unit helpers ----------------------------------------------------------------------------------


def test_help_lists_every_option(tmp_path: Path) -> None:
    out = cli("export", "--help", cwd=tmp_path).stdout
    for text in ("--format", "--out", "--workspace", "--index", "--layout", "--pretty", "json, plantuml, svg or png"):
        assert text in out


def test_folder_names_are_safe_and_unique() -> None:
    class M:
        def __init__(self, name: str) -> None:
            self.name = name

    class W:
        def __init__(self, name: str) -> None:
            self.model = M(name)

    got = export_files.folder_names([W("My Shop!"), W("my shop!"), W(""), W("")], "stem")
    assert got == ["my-shop-", "my-shop--2", "stem", "stem-2"]


# --- PlantUML, SVG and PNG (need jpype1 and Java; svg and png also Graphviz unless smetana) -------------------------


def have_plantuml() -> bool:
    try:
        import jpype  # type: ignore  # noqa: F401
    except ImportError:
        return False
    return shutil.which("java") is not None


needs_plantuml = pytest.mark.skipif(not have_plantuml(), reason="jpype1 and Java are not available")


@needs_plantuml
def test_plantuml_writes_one_puml_per_view_for_each_workspace(tmp_path: Path, many: Path) -> None:
    r = cli("export", "many.py", "-f", "plantuml", "-f", "json", "--workspace", "Billing", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert names(tmp_path / "export" / "billing") == ["workspace.json"]  # Billing has no view
    assert "has no views" in r.stderr
    r = cli("export", "many.py", "-f", "plantuml", "--index", "0", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    assert "@startuml" in (tmp_path / "export" / "shop" / "ctx.puml").read_text()


@needs_plantuml
def test_svg_and_png_render_with_smetana(tmp_path: Path, model: Path) -> None:
    r = cli("export", "model.py", "-f", "svg", "-f", "png", "--layout", "smetana", cwd=tmp_path)
    assert r.returncode == 0, r.stderr
    folder = tmp_path / "export" / "shop"
    assert (folder / "ctx.svg").read_text().lstrip().startswith(("<?xml", "<svg"))
    assert (folder / "ctx.png").read_bytes().startswith(b"\x89PNG")


@needs_plantuml
def test_missing_graphviz_fails_before_anything_is_written(tmp_path: Path, model: Path) -> None:
    r = cli("export", "model.py", "-f", "json", "-f", "svg", cwd=tmp_path, env={"GRAPHVIZ_DOT": "/no/such/dot"})
    assert r.returncode == 1
    assert "--layout smetana" in r.stderr
    assert not (tmp_path / "export").exists()


def test_diagram_formats_without_jpype_name_the_extra(tmp_path: Path, model: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """The preflight reports the missing extra, and writes no JSON either."""
    import builtins

    real: Any = builtins.__import__

    def fake(name: str, *a: Any, **kw: Any) -> Any:
        if name.startswith("buildzr.sinks.plantuml_sink"):
            raise ImportError("jpype")
        return real(name, *a, **kw)

    monkeypatch.setattr(builtins, "__import__", fake)
    with pytest.raises(export_files.ExportError, match=r"buildzr\[export-plantuml\]"):
        export_files._preflight(["json", "svg"], "smetana")
