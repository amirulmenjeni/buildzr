"""THIRD_PARTY_NOTICES.txt: present, accurate for what the package ships, and shipped in the wheel and the sdist."""

from __future__ import annotations

import glob
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tarfile
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
NOTICES = ROOT / "THIRD_PARTY_NOTICES.txt"
VIEWER = ROOT / "viewer"
TYPE_ONLY = re.compile(r"^(@types/.+|csstype)$")
# The woff2 files of @fontsource/inter 5.3.0 (identical to the files of the npm package locked in
# viewer/package-lock.json, checked when they were added), as the viewer bundles them.
FONT_SHA256 = {
    "inter-latin-400-normal.woff2": "8909904ab6c872eb994093482a88a28eca2cd95912d7b6fecd72103b0dc07edc",
    "inter-latin-700-normal.woff2": "6f56409fd3d64bb85f7d070bce20749db2d66b6d63cec586cc22d1c761be2491",
}


def notices() -> str:
    return NOTICES.read_text(encoding="utf-8")


def bundled_packages() -> list[tuple[str, str, str]]:
    lock_file = VIEWER / "package-lock.json"
    if not lock_file.exists():
        pytest.skip("viewer/package-lock.json is not in this tree (sdist)")
    lock = json.loads(lock_file.read_text(encoding="utf-8"))["packages"]
    found = []
    for key, pkg in lock.items():
        name = key.split("node_modules/")[-1]
        if key and not pkg.get("dev") and not TYPE_ONLY.match(name):
            found.append((name, pkg["version"], pkg["license"]))
    return found


def test_notices_file_is_plain_text_and_well_formed() -> None:
    text = notices()
    assert text.startswith("buildzr third-party notices\n")
    assert "\r" not in text and text.endswith("\n") and not text.endswith("\n\n")
    assert "MIT License (LICENSE.md)" in text


def test_notices_carry_the_inter_font_licence_and_copyright() -> None:
    text = notices()
    ofl = (VIEWER / "src" / "fonts" / "OFL.txt")
    if not ofl.exists():
        ofl = ROOT / "buildzr" / "site" / "fonts" / "OFL-1.1.txt"
    body = ofl.read_text(encoding="utf-8").replace("\r\n", "\n").strip("\n")
    assert body in text, "the full OFL text, exactly as shipped with the font"
    assert "Copyright 2016 The Inter Project Authors (https://github.com/rsms/inter)" in text
    assert "SIL OPEN FONT LICENSE Version 1.1" in text
    assert "@fontsource/inter 5.3.0" in text
    # the two copies of the licence in the repository stay identical
    assert (ROOT / "buildzr/site/fonts/OFL-1.1.txt").read_text(encoding="utf-8") == ofl.read_text(encoding="utf-8")


def test_bundled_font_files_are_the_verified_inter_release() -> None:
    folder = VIEWER / "src" / "fonts"
    if not folder.exists():
        pytest.skip("viewer sources are not in this tree (sdist)")
    found = {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.glob("*.woff2")}
    assert found == FONT_SHA256


def test_notices_list_every_package_linked_into_the_viewer() -> None:
    text = notices()
    packages = bundled_packages()
    assert {n for n, _, _ in packages} >= {"react", "react-dom", "@xyflow/react", "zustand", "d3-zoom"}
    for name, version, spdx in packages:
        assert re.search(rf"^  {re.escape(name)} {re.escape(version)}  \({re.escape(spdx)}\)", text, re.M), \
            f"{name} {version} ({spdx}) is missing from THIRD_PARTY_NOTICES.txt"
    # a copyright line for each distinct author in the packages' licences
    for holder in ("Meta Platforms, Inc. and affiliates", "Paul Henschel", "webkid GmbH", "Mike Bostock", "Jorge Bucaran"):
        assert holder in text


def test_notices_cover_elkjs() -> None:
    text = notices()
    vendored = (ROOT / "buildzr/site/layout/vendor/NOTICE").read_text(encoding="utf-8")
    version = re.search(r'npm package "elkjs" (\d+(?:\.\d+)+)', vendored)
    assert version and f"elkjs {version.group(1)}" in text
    assert "Eclipse Public License - v 2.0" in text
    assert (ROOT / "buildzr/site/layout/vendor/LICENSE-EPL-2.0.md").read_text(encoding="utf-8").strip() in text


def test_notices_are_up_to_date_with_the_generator() -> None:
    if not (VIEWER / "node_modules").exists() or not (ROOT / "scripts" / "gen_third_party_notices.py").exists():
        pytest.skip("needs `npm ci` in viewer/ and the repository scripts")
    done = subprocess.run([sys.executable, str(ROOT / "scripts" / "gen_third_party_notices.py"), "--check"],
                          capture_output=True, text=True)
    assert done.returncode == 0, done.stderr


def test_pyproject_ships_the_notices_as_licence_files() -> None:
    pyproject = ROOT / "pyproject.toml"
    if not pyproject.exists():
        pytest.skip("pyproject.toml is not in this tree")
    text = pyproject.read_text(encoding="utf-8")
    match = re.search(r"^license-files = \[(.*?)\]", text, re.M)
    assert match and {"LICENSE.md", "THIRD_PARTY_NOTICES.txt"} <= set(re.findall(r'"([^"]+)"', match.group(1)))


def test_viewer_bundle_ships_the_notices_for_its_about_view() -> None:
    assets = ROOT / "buildzr" / "site" / "static" / "assets"
    if not assets.exists():
        pytest.skip("the viewer is not built")
    (shipped,) = glob.glob(str(assets / "THIRD_PARTY_NOTICES-*.txt"))
    assert Path(shipped).read_text(encoding="utf-8") == notices()
    assert sorted(p.name.rsplit("-", 1)[0] for p in (assets / "fonts").glob("*.woff2")) == [
        "inter-latin-400-normal", "inter-latin-700-normal"]


@pytest.mark.parametrize("kind", ["wheel", "sdist"])
def test_built_package_contains_the_notices(kind: str, tmp_path: Path) -> None:
    if shutil.which("uv") is None:
        pytest.skip("uv not available")
    if not (ROOT / "hatch_build.py").exists():
        pytest.skip("not a source checkout")
    subprocess.run(["uv", "build", f"--{kind}", "-o", str(tmp_path)], cwd=ROOT, check=True, capture_output=True)
    if kind == "wheel":
        (wheel,) = glob.glob(str(tmp_path / "*.whl"))
        z = zipfile.ZipFile(wheel)
        (path,) = [n for n in z.namelist() if n.endswith(".dist-info/licenses/THIRD_PARTY_NOTICES.txt")]
        assert z.read(path).decode("utf-8") == notices()
        assert any(n.endswith(".dist-info/licenses/LICENSE.md") for n in z.namelist())
        meta = z.read([n for n in z.namelist() if n.endswith(".dist-info/METADATA")][0]).decode("utf-8")
        assert "License-File: THIRD_PARTY_NOTICES.txt" in meta
    else:
        (sdist,) = glob.glob(str(tmp_path / "*.tar.gz"))
        with tarfile.open(sdist) as t:
            (path,) = [n for n in t.getnames() if n.count("/") == 1 and n.endswith("/THIRD_PARTY_NOTICES.txt")]
            assert t.extractfile(path).read().decode("utf-8") == notices()
