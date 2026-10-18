"""Stage 5: ``buildzr build`` / ``serve``."""

from __future__ import annotations

import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import threading
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

import pytest

import buildzr.site.build as build_mod
import buildzr.site.cli as cli
from buildzr.site.build import BuildError, build_workspace
from buildzr.site.check import check_built
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
        return build_workspace(ws, str(out), layout_fn=stub_layout, static_dir=str(static), **kw)
    finally:
        os.environ["PYTHONPATH"] = env


def test_build_layout_and_build_json(tmp_path: Path, ws_file: str) -> None:
    static = make_static(tmp_path / "static")
    out = tmp_path / "built"
    info = build(ws_file, out, static)
    assert sorted(os.listdir(out)) == ["assets", "build.json", "data", "index.html"]
    index = json.loads((out / "data" / "index.json").read_text(encoding="utf-8"))
    model_file = out / "data" / index["model"]["file"]
    assert (out / "data" / "index.json").is_file() and model_file.is_file()
    assert not (out / "data" / "model.json").exists()
    digest = hashlib.sha256(model_file.read_bytes()).hexdigest()
    assert index["model"] == {"file": f"model.{digest[:8]}.json", "hash": "sha256:" + digest}
    with open(out / "build.json", encoding="utf-8") as f:
        bj = json.load(f)
    assert bj == info
    assert bj["k"] == 4 and bj["textColor"] == "wcag" and bj["input"]["file"] == "workspace.py"
    assert bj["modelHash"] == json.load(open(model_file))["modelHash"]
    assert "time" not in json.dumps(bj).lower()
    assert not [n for n in os.listdir(tmp_path) if n.startswith(".build-")]


def test_tool_buildzr_in_pyproject_is_ignored(tmp_path: Path, ws_file: str) -> None:
    (tmp_path / "pyproject.toml").write_text('[tool.buildzr]\nk = 7\ntext_color = "c4"\n')
    assert not hasattr(build_mod, "read_config")
    static = make_static(tmp_path / "static")
    info = build(ws_file, tmp_path / "a", static)
    assert (info["k"], info["textColor"]) == (4, "wcag")
    info = build(ws_file, tmp_path / "b", static, k=2, text_color="c4")
    assert (info["k"], info["textColor"]) == (2, "c4")


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
    assert main(["build", "--workspaces", ws_file, "--out", str(tmp_path / "o"), "--no-viewer"]) == 1


def test_build_failure_keeps_previous_output(tmp_path: Path, ws_file: str) -> None:
    static = make_static(tmp_path / "static")
    out = tmp_path / "built"
    build(ws_file, out, static)
    before = (out / "build.json").read_bytes()
    Path(ws_file).write_text("raise SystemExit(3)\n")
    with pytest.raises(BuildError):
        build(ws_file, out, static)
    assert (out / "build.json").read_bytes() == before


RUNNER = """
import sys
from buildzr.site.build import build_workspace
from tests.site.stub_layout import stub_layout
build_workspace(sys.argv[1], sys.argv[2], layout_fn=stub_layout, static_dir=sys.argv[3])
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


def test_serve_every_workspace_at_its_name(tmp_path: Path, ws_file: str) -> None:
    static = make_static(tmp_path / "static")
    out = tmp_path / "out"
    build(ws_file, out / "small-fixture", static)
    srv = make_server(str(out), port=0)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    try:
        root = f"http://127.0.0.1:{srv.server_address[1]}/"
        base = root + "small-fixture/"
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
        assert get(root + "index.html")[0] == 404  # nothing of a workspace at the top
        # no listings, no escape
        assert get(base + "data/")[0] == 404
        assert get(base + "../../etc/passwd")[0] == 404
        assert get(base + "%2e%2e/%2e%2e/etc/passwd")[0] == 404
        assert get(root + "nope/index.html")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()


def test_serve_does_not_follow_symlink_out(tmp_path: Path) -> None:
    root = tmp_path / "root"
    fake_built(root / "w")
    (tmp_path / "secret.txt").write_text("s")
    os.symlink(tmp_path / "secret.txt", root / "w" / "link.txt")
    (root / "w" / "index.html").write_text("x")
    srv = make_server(str(root), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        assert get(f"http://127.0.0.1:{srv.server_address[1]}/w/link.txt")[0] == 404
        assert get(f"http://127.0.0.1:{srv.server_address[1]}/w/index.html")[0] == 200
    finally:
        srv.shutdown()
        srv.server_close()


def fake_built(d: Path, name: str = "") -> None:
    """The smallest folder ``serve`` takes for a built workspace: ``build.json`` and ``data/index.json``."""
    (d / "data").mkdir(parents=True)
    (d / "data" / "index.json").write_text("{}")
    (d / "build.json").write_text(json.dumps({"modelHash": "sha256:00", **({"name": name} if name else {})}))


# --- commands: buildzr.yaml, flags, exit codes -------------------------------------------------------

needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")

WS_TEXT = "from tests.site.small_workspace import small_workspace\nw = small_workspace()\n"


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build with the stub layout (no Node), and let the export subprocess import ``tests.site``.

    The stub's scenes fit only the small workspace, so the data checker is replaced by one that passes; tests of the
    checker in the build use :func:`checked`.
    """
    monkeypatch.setattr(build_mod, "_default_layout", lambda: stub_layout)
    monkeypatch.setattr(build_mod, "check_workspace", lambda data_dir: [])
    monkeypatch.setenv("PYTHONPATH", ROOT)


def project(tmp_path: Path, yaml: str = "", ws: bool = True) -> Path:
    """A repository folder (``.git`` stops the config search) with ``ws/workspace.py`` and ``buildzr.yaml``."""
    root = tmp_path / "repo"
    (root / ".git").mkdir(parents=True)
    if ws:
        (root / "ws").mkdir()
        (root / "ws" / "workspace.py").write_text(WS_TEXT)
    if yaml:
        (root / "buildzr.yaml").write_text(yaml)
    return root


def run(root: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str], *argv: str
        ) -> tuple[int, str, str]:
    monkeypatch.chdir(root)
    code = main(list(argv))
    cap = capsys.readouterr()
    return code, cap.out, cap.err


def test_build_driven_by_the_file_with_no_flags(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws/workspace.py\nbuild: {k: 3, text_color: c4, viewer: false, out: out/built}\n")
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert out.startswith("built out/built/small-fixture (") and "modelHash sha256:" in out and "11 elements" in out
    bj = json.loads((root / "out" / "built" / "small-fixture" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (3, "c4")
    assert sorted(os.listdir(root / "out" / "built" / "small-fixture")) == ["build.json", "data"]


def runfd(root: Path, monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str], *argv: str
          ) -> tuple[int, str, str]:
    """Like ``run`` but also captures what the model-run child process writes (it has the same file descriptors)."""
    monkeypatch.chdir(root)
    code = main(list(argv))
    cap = capfd.readouterr()
    return code, cap.out, cap.err


SUMMARY = re.compile(r"^.*: \d+ elements, \d+ relationships, \d+ views, \d+ levels -> .*$", re.M)


def test_build_is_quiet_about_the_model_run_unless_verbose(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                                           capfd: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws/workspace.py\nbuild: {viewer: false}\n")
    code, out, err = runfd(root, monkeypatch, capfd, "build")
    assert (code, err) == (0, "")
    assert not SUMMARY.search(out)
    assert out.startswith("built .buildzr/build/small-fixture (") and out.count("\n") == 1
    for flag in ("-v", "--verbose"):
        code, out, err = runfd(root, monkeypatch, capfd, "build", flag)
        assert (code, err) == (0, "")
        lines = out.splitlines()
        assert len(lines) == 2 and SUMMARY.match(lines[0]) and "11 elements" in lines[0] and "(Small fixture)" in lines[0]
        assert lines[1].startswith("built .buildzr/build/small-fixture (")


@pytest.mark.parametrize("command", [["build"]])
@pytest.mark.parametrize("verbose", [False, True])
def test_a_failing_model_still_shows_its_error(tmp_path: Path, stubbed: None, command: list[str], verbose: bool,
                                               monkeypatch: pytest.MonkeyPatch, capfd: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws/workspace.py\nbuild: {viewer: false}\n")
    (root / "ws" / "workspace.py").write_text("import sys\nprint('model output')\nraise RuntimeError('boom in the model')\n")
    code, out, err = runfd(root, monkeypatch, capfd, *command, *(["-v"] if verbose else []))
    assert code == 1
    assert "boom in the model" in err and "RuntimeError" in err
    assert "model output" in out  # what the model file prints is not ours to hide
    # It failed before it made a workspace, so its broken workspace is named after the file.
    assert "buildzr: BROKEN: workspace workspace (ws/workspace.py) failed at the model step\n" in err
    assert "    RuntimeError: boom in the model\n    workspace.py, line 3: raise RuntimeError('boom in the model')\n" in err
    assert err.endswith("  this workspace is broken; the viewer says so\n")
    assert not SUMMARY.search(out)


def test_build_from_a_subfolder_uses_the_file_folder_for_relative_paths(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws/workspace.py\nbuild: {viewer: false}\n")
    (root / "deep" / "er").mkdir(parents=True)
    code, _, err = run(root / "deep" / "er", monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert (root / ".buildzr" / "build" / "small-fixture" / "data" / "index.json").is_file()  # next to the file


def test_flag_beats_file_beats_default(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: nope.py\nbuild: {k: 3, text_color: c4, viewer: false, out: from-file}\n")
    ws = str(root / "ws" / "workspace.py")
    code, _, err = run(root, monkeypatch, capsys, "build", "-w", ws, "--k", "2", "--text-color", "wcag",
                       "-o", "from-flag")
    assert (code, err) == (0, "")
    bj = json.loads((root / "from-flag" / "small-fixture" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (2, "wcag")
    assert not (root / "from-file").exists()
    # the file beats the default ...
    code, _, _ = run(root, monkeypatch, capsys, "build", "-w", ws)
    assert code == 0
    bj = json.loads((root / "from-file" / "small-fixture" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (3, "c4")
    # ... and with no file the defaults apply
    bare = project(tmp_path / "bare")
    code, _, _ = run(bare, monkeypatch, capsys, "build", "-w", str(bare / "ws" / "workspace.py"), "--no-viewer")
    assert code == 0
    bj = json.loads((bare / ".buildzr" / "build" / "small-fixture" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (4, "wcag")


def test_no_viewer_flag_and_viewer_false_both_mean_data_only(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws/workspace.py\n")  # build.viewer defaults to true
    code, _, _ = run(root, monkeypatch, capsys, "build", "--no-viewer", "-o", "a")
    assert code == 0 and sorted(os.listdir(root / "a" / "small-fixture")) == ["build.json", "data"]
    (root / "buildzr.yaml").write_text("workspaces: ws/workspace.py\nbuild: {viewer: false}\n")
    code, _, _ = run(root, monkeypatch, capsys, "build", "-o", "b")
    assert code == 0 and sorted(os.listdir(root / "b" / "small-fixture")) == ["build.json", "data"]


def test_build_without_a_workspaces_folder_is_a_usage_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                             capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(project(tmp_path), monkeypatch, capsys, "build")
    assert code == 2 and out == ""
    assert err == ("buildzr: error: workspaces not found; create the workspaces folder, pass -w PATH "
                   "or set workspaces: in buildzr.yaml\n")


def test_config_problems_are_printed_as_the_loader_formats_them(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build:\n  k: four\n  token: abc\n")
    code, out, err = run(root, monkeypatch, capsys, "build", "-w", "x.py")
    assert code == 2 and out == ""
    assert err.splitlines()[0] == 'buildzr.yaml:2: build.k: expected a whole number of at least 1, got the text "four"'
    assert 'build: unknown key "token"' in err and "buildzr: error:" not in err


def test_missing_config_file_flag_and_misnamed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    code, _, err = run(root, monkeypatch, capsys, "build", "-c", "nope.yaml")
    assert code == 2 and err == "buildzr: error: config file not found: nope.yaml\n"
    (root / "buildzr.yml").write_text("workspaces: x.py\n")
    code, _, err = run(root, monkeypatch, capsys, "build")
    assert code == 2 and err == "found buildzr.yml; the config file must be named buildzr.yaml\n"


def test_explicit_config_flag(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: nope.py\n")  # discovered file would fail
    other = root / "other.yaml"
    other.write_text("workspaces: ws/workspace.py\nbuild: {viewer: false, out: o}\n")
    code, _, err = run(root, monkeypatch, capsys, "build", "-c", str(other))
    assert (code, err) == (0, "")
    assert (root / "o" / "small-fixture" / "data" / "index.json").is_file()


def test_missing_path_exits_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, "build", "-w", "missing.py", "--no-viewer")
    assert code == 2 and err.startswith("buildzr: error: missing.py not found;")


@pytest.mark.parametrize("argv", [[], ["frobnicate"], ["build", "--nope"], ["build", "--text-color", "red"],
                                  ["serve", "-p", "x"], ["deploy"]])
def test_argparse_problems_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                  argv: list[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, *argv)
    assert code == 2 and "buildzr: error: " in err


def test_k_must_be_at_least_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, "build", "-w", "x.py", "--k", "0")
    assert code == 2 and err == "buildzr: error: --k: expected a whole number of at least 1\n"


def test_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["build", "--help"]) == 0
    assert "--no-viewer" in capsys.readouterr().out


def test_deploy_is_gone(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deploy"]) == 2
    assert "invalid choice: 'deploy'" in capsys.readouterr().err


# --- serve: what it serves -------------------------------------------------------------------------------


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(cli, "serve", lambda d, host, port, *a, **kw: calls.append((d, host, port)))
    return calls


def test_serve_default_is_build_out_of_the_nearest_config(
        tmp_path: Path, stubbed: None, served: list[tuple[str, str, int]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: ws\nbuild: {out: public/built, viewer: false}\n")
    (root / "sub").mkdir()
    code, out, err = run(root / "sub", monkeypatch, capsys, "serve", "-p", "9123")
    assert (code, err) == (0, "")
    assert served == [(str(root / "public" / "built"), "127.0.0.1", 9123)]
    assert f"built {root / 'public' / 'built' / 'small-fixture'} (" in out


def test_serve_without_a_workspaces_folder(tmp_path: Path, served: list[tuple[str, str, int]],
                                           monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, ws=False)
    code, _, err = run(root, monkeypatch, capsys, "serve")
    assert code == 2
    assert err == ("buildzr: error: workspaces not found; create the workspaces folder, pass PATH, set workspaces: "
                   "in buildzr.yaml, or serve .buildzr/build as it is with --no-build\n")
    code, _, err = run(root, monkeypatch, capsys, "serve", "--no-build")
    assert code == 1 and err == "buildzr: error: nothing to serve: .buildzr/build holds no built workspace\n"
    fake_built(root / ".buildzr" / "build" / "w")
    code, _, _ = run(root, monkeypatch, capsys, "serve", "--no-build", "--host", "0.0.0.0")
    assert code == 0 and served == [(str(root / ".buildzr" / "build"), "0.0.0.0", 8000)]
    assert served and served[-1][0] == str(root / ".buildzr" / "build")


def test_serve_a_built_folder_reads_only_the_serve_settings_of_the_config(
        tmp_path: Path, served: list[tuple[str, str, int]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "serve: {port: 8123}\n")
    fake_built(root / "copied" / "w")
    code, _, err = run(root, monkeypatch, capsys, "serve", "copied")
    assert (code, err) == (0, "") and served == [("copied", "127.0.0.1", 8123)]
    fake_built(root / "one")  # one built workspace, not a folder of them
    code, _, err = run(root, monkeypatch, capsys, "serve", "one")
    assert (code, err) == (0, "") and served[-1] == ("one", "127.0.0.1", 8123)
    code, _, err = run(root, monkeypatch, capsys, "serve", "copied", "--rebuild")
    assert code == 2 and "--rebuild needs the workspaces folder" in err
    (root / "buildzr.yaml").write_text("build: {k: four}\n")  # the file is read, so its problems stop serve
    code, _, err = run(root, monkeypatch, capsys, "serve", "copied")
    assert code == 2 and "build.k" in err


def test_serve_port_in_use_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    fake_built(root / "s" / "w")
    busy = make_server(str(root / "s"), port=0)
    try:
        port = busy.server_address[1]
        code, _, err = run(root, monkeypatch, capsys, "serve", "s", "-p", str(port))
        assert code == 1 and err.startswith(f"buildzr: error: cannot serve on 127.0.0.1:{port}:")
    finally:
        busy.server_close()


def test_serve_has_no_deploy_flags(capsys: pytest.CaptureFixture[str]) -> None:
    for flag in ("--accept-deploys", "--deploy-port", "--max-upload-mb", "--store"):
        assert main(["serve", flag]) == 2


def test_serve_stays_read_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    fake_built(root / "w")
    srv = make_server(str(root), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/w/data/index.json"
        assert get(url)[0] == 200
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            req = urllib.request.Request(url, data=b"{}", method=method)
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(req)
            assert ei.value.code == 501
    finally:
        srv.shutdown()
        srv.server_close()


# --- real layout (Node): the checker accepts what build writes ------------------------------------------


@needs_node
def test_real_build_passes_the_checker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PYTHONPATH", ROOT)
    root = project(tmp_path, "workspaces: ws/workspace.py\nbuild: {viewer: false, out: out/built}\n")
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, ""), err
    built = root / "out" / "built" / "small-fixture"
    assert (built / "data" / "index.json").is_file()
    assert check_built(str(built / "data"), require_build_json=True).errors == []
    index = json.loads((built / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["model"]["file"].startswith("model.") and (built / "data" / index["model"]["file"]).is_file()
    assert not (built / "data" / "model.json").exists()


REAL_RUNNER = """
import sys
from buildzr.site.build import build_workspace
build_workspace(sys.argv[1], sys.argv[2], viewer=False)
"""


@needs_node
@pytest.mark.parametrize("name", ["synthetic-M", "models-example"])
def test_real_build_byte_identical_across_hash_seeds(tmp_path: Path, name: str) -> None:
    if name == "models-example":
        ws = os.path.join(ROOT, "examples", "buildzr_models_example.py")
    else:
        ws = str(tmp_path / "ws.py")
        Path(ws).write_text(SCRIPTS["synthetic-M"] or "")
    outs = []
    for seed in ("1", "2"):
        out = tmp_path / f"out{seed}"
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=ROOT)
        subprocess.run([sys.executable, "-c", REAL_RUNNER, ws, str(out)], check=True, env=env,
                       cwd=str(tmp_path), capture_output=True)
        outs.append(out)
    r = subprocess.run(["diff", "-rq", str(outs[0]), str(outs[1])], capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout == ""
    model_files = [n for n in os.listdir(outs[0] / "data") if n.startswith("model.")]
    assert len(model_files) == 1 and model_files[0] != "model.json"
