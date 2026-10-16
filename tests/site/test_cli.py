"""Stage 5: ``buildzr build`` / ``serve`` / ``deploy``."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

from buildzr.site.build import BuildError, build_site, read_config
from buildzr.site.cli import main
from buildzr.site.serve import make_server
from tests.site.stub_layout import stub_layout

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SMALL = os.path.join(ROOT, "tests", "site", "small_workspace.py")


def make_static(d: Path) -> Path:
    (d / "assets").mkdir(parents=True)
    (d / "index.html").write_text('<html><script src="assets/viewer.js"></script></html>\n')
    (d / "assets" / "viewer.js").write_text("console.log(1)\n")
    (d / "assets" / "viewer.css").write_text("body{}\n")
    (d / "assets" / "f.woff2").write_bytes(b"wOF2")
    return d


@pytest.fixture
def ws_file(tmp_path: Path) -> str:
    p = tmp_path / "ws" / "workspace.py"
    p.parent.mkdir()
    p.write_text("from tests.site.small_workspace import small_workspace\nw = small_workspace()\n")
    return str(p)


def build(ws: str, out: Path, static: Path, **kw: Any) -> dict[str, Any]:
    env = os.environ.get("PYTHONPATH", "")
    os.environ["PYTHONPATH"] = ROOT + os.pathsep + env  # the export subprocess imports tests.site
    try:
        return build_site(ws, str(out), layout_fn=stub_layout, static_dir=str(static), **kw)
    finally:
        os.environ["PYTHONPATH"] = env


def test_build_layout_and_build_json(tmp_path: Path, ws_file: str) -> None:
    static = make_static(tmp_path / "static")
    out = tmp_path / "site"
    info = build(ws_file, out, static)
    assert sorted(os.listdir(out)) == ["assets", "build.json", "data", "index.html"]
    assert (out / "data" / "model.json").is_file() and (out / "data" / "index.json").is_file()
    with open(out / "build.json", encoding="utf-8") as f:
        bj = json.load(f)
    assert bj == info
    assert bj["k"] == 4 and bj["textColor"] == "wcag" and bj["input"]["file"] == "workspace.py"
    assert bj["modelHash"] == json.load(open(out / "data" / "model.json"))["modelHash"]
    assert "time" not in json.dumps(bj).lower()
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".build-")]


def test_config_and_flag_precedence(tmp_path: Path, ws_file: str) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.buildzr]\nk = 7\ntext_color = "c4"\n')
    assert read_config(ws_file) == {"k": 7, "text_color": "c4"}
    static = make_static(tmp_path / "static")
    assert build(ws_file, tmp_path / "a", static)["k"] == 7
    info = build(ws_file, tmp_path / "b", static, k=2, text_color="wcag")
    assert (info["k"], info["textColor"]) == (2, "wcag")


def test_missing_viewer_and_no_viewer(tmp_path: Path, ws_file: str) -> None:
    with pytest.raises(BuildError, match="viewer bundle is missing"):
        build(ws_file, tmp_path / "s", tmp_path / "nostatic")
    build(ws_file, tmp_path / "s", tmp_path / "nostatic", viewer=False)
    assert sorted(os.listdir(tmp_path / "s")) == ["build.json", "data"]


def test_missing_layout_stage_message(tmp_path: Path, ws_file: str) -> None:
    try:
        import importlib
        importlib.import_module("buildzr.site.layout")
        pytest.skip("layout stage present")
    except ImportError:
        pass
    assert main(["build", "--workspace", ws_file, "--out", str(tmp_path / "o"), "--no-viewer"]) == 1


def test_build_failure_keeps_previous_output(tmp_path: Path, ws_file: str) -> None:
    static = make_static(tmp_path / "static")
    out = tmp_path / "site"
    build(ws_file, out, static)
    before = (out / "build.json").read_bytes()
    Path(ws_file).write_text("raise SystemExit(3)\n")
    with pytest.raises(BuildError):
        build(ws_file, out, static)
    assert (out / "build.json").read_bytes() == before


RUNNER = """
import sys
from buildzr.site.build import build_site
from tests.site.stub_layout import stub_layout
build_site(sys.argv[1], sys.argv[2], layout_fn=stub_layout, static_dir=sys.argv[3])
"""

SCRIPTS = {
    "synthetic-M": 'from tests.site.synthetic import synthetic\nw = synthetic("M")\n',
    "models-example": None,
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_build_byte_identical_across_hash_seeds(tmp_path: Path, name: str) -> None:
    static = make_static(tmp_path / "static")
    src = SCRIPTS[name]
    if src is None:
        ws = os.path.join(ROOT, "examples", "buildzr_models_example.py")
    else:
        ws = str(tmp_path / "ws.py")
        Path(ws).write_text(src)
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"out{seed}"
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=ROOT)
        subprocess.run([sys.executable, "-c", RUNNER, ws, str(out), str(static)], check=True, env=env,
                       cwd=str(tmp_path), capture_output=True)
        outs.append(out)
    r = subprocess.run(["diff", "-rq", str(outs[0]), str(outs[1])], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""


def get(url: str) -> tuple[int, bytes, str]:
    try:
        with urllib.request.urlopen(url) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "")
    except urllib.error.HTTPError as e:
        return e.code, b"", ""


@pytest.mark.parametrize("sub", ["", "sub/x"])
def test_serve_at_root_and_subpath(tmp_path: Path, ws_file: str, sub: str) -> None:
    static = make_static(tmp_path / "static")
    built = tmp_path / "built"
    build(ws_file, built, static)
    root = tmp_path / "served"
    dest = root / sub if sub else root
    dest.parent.mkdir(parents=True, exist_ok=True)
    import shutil
    shutil.copytree(built, dest)
    srv = make_server(str(root), port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}/" + (sub + "/" if sub else "")
        assert get(base + "index.html")[0] == 200
        assert get(base)[0] == 200
        st, body, ctype = get(base + "data/index.json")
        assert st == 200 and ctype == "application/json"
        index = json.loads(body)
        files = [index["model"]["file"], *[e["file"] for e in index["scenes"].values()]]
        assert len(files) >= 6
        for f in files:
            assert get(base + "data/" + f)[0] == 200, f
        assert get(base + "assets/viewer.js")[2].startswith("text/javascript")
        assert get(base + "assets/viewer.css")[2].startswith("text/css")
        assert get(base + "assets/f.woff2")[2] == "font/woff2"
        assert get(base + "build.json")[0] == 200
        # no listings, no escape
        assert get(base + "data/")[0] == 404
        assert get(base + "../../etc/passwd")[0] == 404
        assert get(base + "%2e%2e/%2e%2e/etc/passwd")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_serve_does_not_follow_symlink_out(tmp_path: Path) -> None:
    root = tmp_path / "root"
    root.mkdir()
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", root / "link.txt")
    (root / "index.html").write_text("x")
    srv = make_server(str(root), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert get(f"http://127.0.0.1:{srv.server_address[1]}/link.txt")[0] == 404
        assert get(f"http://127.0.0.1:{srv.server_address[1]}/index.html")[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()


def test_deploy_base_path(tmp_path: Path, ws_file: str, monkeypatch: pytest.MonkeyPatch) -> None:
    import buildzr.site.build as b
    monkeypatch.setattr(b, "_default_layout", lambda: stub_layout)
    monkeypatch.setenv("PYTHONPATH", ROOT)
    assert main(["deploy", "--workspace", ws_file, "--target", str(tmp_path / "t"), "--base-path", "pr/42",
                 "--no-viewer"]) == 0
    assert (tmp_path / "t" / "pr" / "42" / "data" / "index.json").is_file()
    assert main(["deploy", "--workspace", ws_file, "--target", str(tmp_path / "t"), "--base-path", "../x",
                 "--no-viewer"]) == 1
