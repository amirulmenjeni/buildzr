"""The Run Code assets of the docs: the slim wheel (``scripts/build_docs_assets.py``) and the mkdocs hook that
refuses a docs build without them."""

from __future__ import annotations

import importlib.util
import os
import subprocess
import sys
import zipfile
from pathlib import Path
from types import ModuleType

import pytest

from tests.docs.blocks import DOCS, ROOT


def _load(name: str) -> ModuleType:
    spec = importlib.util.spec_from_file_location(name, os.path.join(ROOT, "scripts", name + ".py"))
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


assets = _load("build_docs_assets")


def test_slim_wheel_is_deterministic_and_slim(tmp_path: Path) -> None:
    (tmp_path / "a").mkdir()
    (tmp_path / "b").mkdir()
    name = assets.slim_wheel(str(tmp_path / "a"))
    assert assets.slim_wheel(str(tmp_path / "b")) == name
    a, b = (tmp_path / "a" / name).read_bytes(), (tmp_path / "b" / name).read_bytes()
    assert a == b
    assert len(a) < 400_000, f"the slim wheel grew to {len(a):,} bytes"
    with zipfile.ZipFile(tmp_path / "a" / name) as z:
        names = set(z.namelist())
        record = z.read(f"buildzr-{assets.version()}.dist-info/RECORD").decode()
    for needed in ("buildzr/site/browser.py", "buildzr/site/layout/passes.py", "buildzr/site/scene.py",
                   "buildzr/site/fonts/font_metrics.json", "buildzr/dsl/dsl.py", "buildzr/themes/themes.txt"):
        assert needed in names
    assert not [n for n in names if n.startswith(assets.DROP) or n.endswith((".jar", ".mjs", ".js"))]
    assert {line.split(",")[0] for line in record.splitlines()} == names


def test_slim_wheel_runs_a_snippet_without_the_repository(tmp_path: Path) -> None:
    """Only the slim wheel, pyhumps and typing-extensions on the path, as under Pyodide (no layout: that is ELK)."""
    name = assets.slim_wheel(str(tmp_path))
    with zipfile.ZipFile(tmp_path / name) as z:
        z.extractall(tmp_path / "lib")
    import humps
    import typing_extensions
    deps = {os.path.dirname(os.path.dirname(humps.__file__)), os.path.dirname(typing_extensions.__file__)}
    code = ("import sys; sys.path[:0] = sys.argv[1:]\n"
            "import buildzr.site.browser as b\n"
            "assert b.__file__.startswith(sys.argv[1]), b.__file__\n"
            "from buildzr.site.model import export_model\n"
            "from buildzr.site.levels import build_levels\n"
            "ws, _ = b.run_code(\"a = Person('A')\\nb = SoftwareSystem('B')\\na >> 'uses' >> b\\n\")\n"
            "print(len(build_levels(ws, export_model(ws))['levels']))\n")
    out = subprocess.run([sys.executable, "-S", "-c", code, str(tmp_path / "lib"), *sorted(deps)],
                         capture_output=True, text=True, cwd=tmp_path)
    assert out.returncode == 0, out.stderr
    assert int(out.stdout) >= 1


def test_pyhumps_is_the_locked_wheel() -> None:
    url, sha = assets.locked_wheel("pyhumps")
    assert url.endswith("/pyhumps-3.8.0-py3-none-any.whl") and len(sha) == 64


def test_docs_build_refuses_missing_assets(tmp_path: Path) -> None:
    hooks = _load("mkdocs_hooks")
    assert hooks.missing_runcode_assets(str(tmp_path)) == list(hooks.NEEDED)
    from mkdocs.exceptions import PluginError
    with pytest.raises(PluginError, match="build_docs_assets.py"):
        hooks.on_config({"docs_dir": str(tmp_path)})
    with open(os.path.join(ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        assert "scripts/mkdocs_hooks.py" in f.read()
    assert os.path.basename(DOCS) == "docs"
