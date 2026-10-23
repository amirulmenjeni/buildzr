"""``Workspace.save()`` is deprecated in favour of ``buildzr export`` but behaves exactly as before."""

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest

from buildzr.dsl import Person, SoftwareSystem, SystemContextView, Workspace

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def make() -> Workspace:
    with Workspace("Shop") as w:
        user = Person("User")
        app = SoftwareSystem("App")
        user >> "uses" >> app
        SystemContextView(app, key="ctx", description="ctx")
    return w


def test_save_warns_and_points_at_the_export_command(tmp_path: Path) -> None:
    w = make()
    with pytest.warns(DeprecationWarning, match=r"buildzr export") as record:
        w.save(path=tmp_path / "w.json")
    assert record[0].filename == __file__  # the warning blames the caller, not buildzr


def test_save_still_writes_and_returns_what_it_did(tmp_path: Path) -> None:
    w = make()
    with pytest.warns(DeprecationWarning):
        result = w.save(path=tmp_path / "out" / "w.json", pretty=True)
    assert result == str(tmp_path / "out" / "w.json")
    assert json.loads((tmp_path / "out" / "w.json").read_text()) == json.loads(w.to_json())


def test_save_default_path_and_errors_are_unchanged(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    w = make()
    with pytest.warns(DeprecationWarning):
        assert w.save() == str(tmp_path / "shop.json")
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="Unsupported format"):
        w.save(format="bogus")  # type: ignore[arg-type]
    with pytest.warns(DeprecationWarning), pytest.raises(ValueError, match="Unsupported layout"):
        w.save(layout="bogus")  # type: ignore[arg-type]


def test_export_json_equals_save_json(tmp_path: Path) -> None:
    """Migration check: ``buildzr export`` writes the same JSON ``save(pretty=True)`` wrote.

    One model file does both in one process, so the generated ids agree.
    """
    (tmp_path / "model.py").write_text(
        "import os\n"
        "from buildzr.dsl import *\n"
        "with Workspace('Shop') as w:\n"
        "    user = Person('User')\n"
        "    app = SoftwareSystem('App')\n"
        "    user >> 'uses' >> app\n"
        "    SystemContextView(app, key='ctx', description='ctx')\n"
        "w.save(path=os.environ['SAVED_TO'], pretty=True)\n"
    )
    env = dict(os.environ, PYTHONPATH=ROOT + os.pathsep + os.environ.get("PYTHONPATH", ""),
               SAVED_TO=str(tmp_path / "saved.json"))
    r = subprocess.run([sys.executable, "-m", "buildzr.site.cli", "export", "model.py", "--pretty"], cwd=tmp_path,
                       env=env, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    assert (tmp_path / "export" / "shop" / "workspace.json").read_text() == (tmp_path / "saved.json").read_text()
