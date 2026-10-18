"""The wheel ships the built package data (schemas, ELK vendor files, fonts, viewer bundle)."""

from __future__ import annotations

import glob
import os
import shutil
import subprocess
import zipfile
from pathlib import Path

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def test_wheel_contents(tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv not available")
    out = tmp_path / "dist"
    subprocess.run(["uv", "build", "--wheel", "-o", str(out)], cwd=ROOT, check=True, capture_output=True)
    (wheel,) = glob.glob(str(out / "*.whl"))
    names = set(zipfile.ZipFile(wheel).namelist())
    print(f"wheel size: {os.path.getsize(wheel)} bytes, {len(names)} files")

    def tree(sub: str) -> set[str]:
        base = os.path.join(ROOT, sub)
        return {os.path.relpath(os.path.join(d, f), ROOT).replace(os.sep, "/")
                for d, _, fs in os.walk(base) for f in fs if "__pycache__" not in d and not f.endswith(".pyc")}

    expected = {f for f in tree("buildzr/site/schema") if f.endswith(".json")}
    assert len(expected) >= 4
    expected |= {"buildzr/site/layout/runner.mjs", "buildzr/site/fonts/font_metrics.json",
                 "buildzr/site/fonts/OFL-1.1.txt"}
    vendor = tree("buildzr/site/layout/vendor")
    assert any(v.endswith("elk.bundled.js") for v in vendor)
    expected |= vendor
    expected |= tree("buildzr/site/static")  # gitignored build output, shipped when present
    missing = sorted(expected - names)
    assert missing == []
    assert not [n for n in names if "fixtures" in n or n.startswith("tests/")]
