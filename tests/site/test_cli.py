"""Stage 5: ``buildzr build`` / ``serve`` / ``deploy``."""

from __future__ import annotations

import hashlib
import json
import os
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
from buildzr.site.build import BuildError, build_site
from buildzr.site.check import Report, check_site
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


# --- commands: buildzr.yaml, flags, targets, exit codes -----------------------------------------------

needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")

WS_TEXT = "from tests.site.small_workspace import small_workspace\nw = small_workspace()\n"


@pytest.fixture
def stubbed(monkeypatch: pytest.MonkeyPatch) -> None:
    """Build with the stub layout (no Node), and let the export subprocess import ``tests.site``."""
    monkeypatch.setattr(build_mod, "_default_layout", lambda: stub_layout)
    monkeypatch.setenv("PYTHONPATH", ROOT)


@pytest.fixture
def checks(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, dict[str, Any]]]:
    """Replace the checker (the stub layout does not draw a checkable site); record how it is called."""
    calls: list[tuple[str, dict[str, Any]]] = []

    def fake(data_dir: str, **kw: Any) -> Report:
        calls.append((data_dir, kw))
        return Report()
    monkeypatch.setattr(cli, "check_site", fake)
    return calls


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
    root = project(tmp_path, "workspace: ws/workspace.py\nbuild: {k: 3, text_color: c4, viewer: false, out: out/site}\n")
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert out.startswith("built out/site (") and "modelHash sha256:" in out and "11 elements" in out
    bj = json.loads((root / "out" / "site" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (3, "c4")
    assert sorted(os.listdir(root / "out" / "site")) == ["build.json", "data"]


def test_build_from_a_subfolder_uses_the_file_folder_for_relative_paths(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspace: ws/workspace.py\nbuild: {viewer: false}\n")
    (root / "deep" / "er").mkdir(parents=True)
    code, _, err = run(root / "deep" / "er", monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert (root / ".buildzr" / "site" / "data" / "index.json").is_file()  # the default out, next to the file


def test_flag_beats_file_beats_default(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspace: nope.py\nbuild: {k: 3, text_color: c4, viewer: false, out: from-file}\n")
    ws = str(root / "ws" / "workspace.py")
    code, _, err = run(root, monkeypatch, capsys, "build", "-w", ws, "--k", "2", "--text-color", "wcag",
                       "-o", "from-flag")
    assert (code, err) == (0, "")
    bj = json.loads((root / "from-flag" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (2, "wcag")
    assert not (root / "from-file").exists()
    # the file beats the default ...
    code, _, _ = run(root, monkeypatch, capsys, "build", "-w", ws)
    assert code == 0
    bj = json.loads((root / "from-file" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (3, "c4")
    # ... and with no file the defaults apply
    bare = project(tmp_path / "bare")
    code, _, _ = run(bare, monkeypatch, capsys, "build", "-w", str(bare / "ws" / "workspace.py"), "--no-viewer")
    assert code == 0
    bj = json.loads((bare / ".buildzr" / "site" / "build.json").read_text(encoding="utf-8"))
    assert (bj["k"], bj["textColor"]) == (4, "wcag")


def test_no_viewer_flag_and_viewer_false_both_mean_data_only(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspace: ws/workspace.py\n")  # build.viewer defaults to true
    code, _, _ = run(root, monkeypatch, capsys, "build", "--no-viewer", "-o", "a")
    assert code == 0 and sorted(os.listdir(root / "a")) == ["build.json", "data"]
    (root / "buildzr.yaml").write_text("workspace: ws/workspace.py\nbuild: {viewer: false}\n")
    code, _, _ = run(root, monkeypatch, capsys, "build", "-o", "b")
    assert code == 0 and sorted(os.listdir(root / "b")) == ["build.json", "data"]


def test_build_without_a_workspace_is_a_usage_error(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(project(tmp_path), monkeypatch, capsys, "build")
    assert code == 2 and out == ""
    assert err == "buildzr: error: no workspace given; pass --workspace FILE or set workspace: in buildzr.yaml\n"


def test_config_problems_are_printed_as_the_loader_formats_them(
        tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build:\n  k: four\ntargets:\n  prod: {dir: x, token: abc}\n")
    code, out, err = run(root, monkeypatch, capsys, "build", "-w", "x.py")
    assert code == 2 and out == ""
    assert err.splitlines()[0] == 'buildzr.yaml:2: build.k: expected a whole number of at least 1, got the text "four"'
    assert 'targets.prod: unknown key "token"' in err and "buildzr: error:" not in err


def test_missing_config_file_flag_and_misnamed_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    code, _, err = run(root, monkeypatch, capsys, "build", "-c", "nope.yaml")
    assert code == 2 and err == "buildzr: error: config file not found: nope.yaml\n"
    (root / "buildzr.yml").write_text("workspace: x.py\n")
    code, _, err = run(root, monkeypatch, capsys, "build")
    assert code == 2 and err == "found buildzr.yml; the config file must be named buildzr.yaml\n"


def test_explicit_config_flag(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspace: nope.py\n")  # discovered file would fail
    other = root / "other.yaml"
    other.write_text("workspace: ws/workspace.py\nbuild: {viewer: false, out: o}\n")
    code, _, err = run(root, monkeypatch, capsys, "build", "-c", str(other))
    assert (code, err) == (0, "")
    assert (root / "o" / "data" / "index.json").is_file()


def test_build_failure_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, "build", "-w", "missing.py", "--no-viewer")
    assert code == 1 and err.startswith("buildzr: error: workspace file not found:")


@pytest.mark.parametrize("argv", [[], ["frobnicate"], ["build", "--nope"], ["build", "--text-color", "red"],
                                  ["serve", "-p", "x"], ["deploy", "--from"]])
def test_argparse_problems_exit_2(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str],
                                  argv: list[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, *argv)
    assert code == 2 and "buildzr: error: " in err


def test_k_must_be_at_least_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                              capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, "build", "-w", "x.py", "--k", "0")
    assert code == 2 and err == "buildzr: error: --k: expected a whole number of at least 1\n"


def test_help_exits_0(capsys: pytest.CaptureFixture[str]) -> None:
    assert main(["deploy", "--help"]) == 0
    assert "--dry-run" in capsys.readouterr().out


DEPLOY_YAML = """workspace: ws/workspace.py
build: {viewer: false}
targets:
  www: {dir: out/www}
  preview: {dir: out/preview, path: "pr/${PR_NUMBER}"}
  live: {url: "http://127.0.0.1:9001"}
"""


def test_unknown_target_lists_the_available_ones(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML + "default_target: www\n")
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "staging")
    assert code == 2 and out == ""
    assert err == (f'buildzr: error: no target named "staging"; targets in {root / "buildzr.yaml"}: '
                   "www (default), preview, live\n")


def test_deploy_needs_a_config_and_a_target(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path), monkeypatch, capsys, "deploy", "-t", "x")
    assert code == 2 and err == "buildzr: error: no buildzr.yaml found; deploy needs a target\n"
    code, _, err = run(project(tmp_path / "b", DEPLOY_YAML), monkeypatch, capsys, "deploy")
    assert code == 2 and "no target given and no default_target" in err


def test_dry_run_prints_the_resolved_target_and_writes_nothing(
        tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    before = sorted(os.listdir(root))
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--dry-run")
    assert (code, err) == (0, "")
    assert "dry run: would write " in out and " files, " in out
    assert f"to {root / 'out' / 'www'} (target www)" in out and "nothing was written" in out
    assert out.startswith("built (")
    assert sorted(os.listdir(root)) == before and not (root / "out").exists()
    assert len(checks) == 1 and checks[0][1] == {"require_build_json": True}
    assert checks[0][0].endswith(os.path.join("site", "data"))


def test_dir_deploy_writes_the_site_below_the_path(tmp_path: Path, stubbed: None,
                                                    checks: list[tuple[str, dict[str, Any]]],
                                                    monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    monkeypatch.setenv("PR_NUMBER", "42")
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview")
    assert (code, err) == (0, "")
    site = root / "out" / "preview" / "pr" / "42"
    assert (site / "data" / "index.json").is_file() and (site / "build.json").is_file()
    assert "writing " in out and "deployed pr/42: modelHash sha256:" in out and "previous" not in out
    assert not [n for n in os.listdir(root / "out" / "preview" / "pr") if n.startswith(".")]
    assert len(checks) == 1 and checks[0][1] == {"require_build_json": True}
    # a second deploy replaces it and names the previous model
    code, out, _ = run(root, monkeypatch, capsys, "deploy", "-t", "preview")
    assert code == 0 and "(previous sha256:" in out


def test_dir_deploy_with_the_variable_unset_fails(tmp_path: Path, stubbed: None,
                                                  checks: list[tuple[str, dict[str, Any]]],
                                                  monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    monkeypatch.delenv("PR_NUMBER", raising=False)
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview")
    assert code == 2 and out == ""
    assert err == ('buildzr.yaml:5: targets.preview.path: environment variable PR_NUMBER is not set '
                   '(used in "pr/${PR_NUMBER}")\n')
    assert not (root / "out").exists()
    # another target's variable does not matter
    code, _, _ = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--dry-run")
    assert code == 0


def test_path_flag_overrides_the_targets_path(tmp_path: Path, stubbed: None,
                                              checks: list[tuple[str, dict[str, Any]]],
                                              monkeypatch: pytest.MonkeyPatch,
                                              capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--path", "/team/a/")
    assert (code, err) == (0, "")
    assert (root / "out" / "www" / "team" / "a" / "data" / "index.json").is_file()
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--path", "../x")
    assert code == 2 and err == 'buildzr: error: --path: must not contain a ".." segment\n'
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--path", "Up")
    assert code == 2 and "--path: segment" in err


def test_a_url_target_off_this_machine_is_refused_before_building(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML + "  far: {url: \"http://10.1.2.3:8001\"}\n")
    for extra in ([], ["--dry-run"], ["--rollback"]):
        code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "far", *extra)
        assert code == 2 and out == ""
        assert "10.1.2.3 is not this machine" in err and "ssh -N -L 9001:127.0.0.1:8001" in err


def test_base_path_flag_is_gone(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--base-path", "pr/42")
    assert code == 2 and out == ""
    assert err == "buildzr: error: --base-path was removed; use --path P (or the target's path: in buildzr.yaml)\n"
    assert not (root / "out").exists()


def test_old_target_dir_flag_is_a_name_now(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    code, _, err = run(root, monkeypatch, capsys, "deploy", "--target", "./some/dir")
    assert code == 2 and 'no target named "./some/dir"' in err


def test_rollback_is_not_built(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                               capsys: pytest.CaptureFixture[str]) -> None:
    code, _, err = run(project(tmp_path, DEPLOY_YAML), monkeypatch, capsys, "deploy", "-t", "www", "--rollback")
    assert code == 2
    assert err == "buildzr: error: --rollback works with url targets only (a dir target keeps no previous release)\n"


def test_checker_failure_exits_1_and_leaves_the_target_alone(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    monkeypatch.setattr(cli, "check_site", lambda d, **kw: Report(errors=[f"scene {i}: broken" for i in range(25)]))
    keep = root / "out" / "www"
    keep.mkdir(parents=True)
    (keep / "build.json").write_text("{}")
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    assert code == 1 and "checker found 25 problem(s)" in err and "... and 5 more" in err
    assert err.count("broken") == 20
    assert sorted(os.listdir(keep)) == ["build.json"] and (keep / "build.json").read_text() == "{}"
    assert not [n for n in os.listdir(root / "out") if n.startswith(".")]


def test_deploy_will_not_replace_a_folder_that_is_not_a_site(
        tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    (root / "out" / "www").mkdir(parents=True)
    (root / "out" / "www" / "notes.txt").write_text("mine")
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    assert code == 1 and "is not a buildzr site" in err
    assert (root / "out" / "www" / "notes.txt").read_text() == "mine"


def test_deploy_from_a_built_site(tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]],
                                  monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    code, _, _ = run(root, monkeypatch, capsys, "build", "-o", "built")
    assert code == 0
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--from", "built")
    assert (code, err) == (0, "")
    assert out.startswith("using built (") and (root / "out" / "www" / "data" / "index.json").is_file()
    assert (root / "out" / "www" / "build.json").read_bytes() == (root / "built" / "build.json").read_bytes()
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--from", "built", "--k", "2")
    assert code == 2 and "--k cannot be used with --from" in err
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www", "--from", "nothing-here")
    assert code == 1 and "does not look like a built site" in err


def test_deploy_warns_when_jsonschema_is_missing(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                                  capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    monkeypatch.setattr(cli, "check_site", lambda d, **kw: Report())
    monkeypatch.setitem(sys.modules, "jsonschema", None)  # makes ``import jsonschema`` raise ImportError
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    warning = "buildzr: warning: jsonschema is not installed; the site check skips the schema step\n"
    assert code == 0 and err == warning


def test_deploy_does_not_warn_when_jsonschema_is_installed(
        tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    pytest.importorskip("jsonschema")
    root = project(tmp_path, DEPLOY_YAML)
    monkeypatch.setattr(cli, "check_site", lambda d, **kw: Report())
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    assert (code, err) == (0, "")


@pytest.mark.skipif(os.name == "nt" or (hasattr(os, "geteuid") and os.geteuid() == 0),
                    reason="needs a user that file permissions apply to")
def test_dir_deploy_into_a_read_only_parent_is_an_error_not_a_traceback(
        tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)
    (root / "out").mkdir()
    (root / "out").chmod(0o555)
    try:
        code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    finally:
        (root / "out").chmod(0o755)
    assert code == 1 and out == ""
    assert err.startswith(f"buildzr: error: cannot write to {root / 'out' / 'www'}: ") and "Traceback" not in err
    assert err.count("\n") == 1 and os.listdir(root / "out") == []


def test_dir_deploy_swap_failure_is_an_error_not_a_traceback(
        tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, DEPLOY_YAML)

    def boom(src: str, dest: str) -> None:
        raise PermissionError(13, "Permission denied")
    monkeypatch.setattr(cli, "swap_dir", boom)
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "www")
    assert code == 1 and err == f"buildzr: error: cannot write to {root / 'out' / 'www'}: Permission denied\n"
    assert not [n for n in os.listdir(root / "out") if n.startswith(".")]  # the staging folder is removed


def test_deploy_viewer_follows_the_target(tmp_path: Path, stubbed: None, checks: list[tuple[str, dict[str, Any]]],
                                          monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspace: ws/workspace.py\ntargets:\n  d: {dir: out/d, viewer: false}\n")
    code, _, err = run(root, monkeypatch, capsys, "deploy", "-t", "d")
    assert (code, err) == (0, "")  # no viewer bundle needed: the target says data only
    assert sorted(os.listdir(root / "out" / "d")) == ["build.json", "data"]


# --- serve: default directory ---------------------------------------------------------------------------


@pytest.fixture
def served(monkeypatch: pytest.MonkeyPatch) -> list[tuple[str, str, int]]:
    calls: list[tuple[str, str, int]] = []
    monkeypatch.setattr(cli, "serve", lambda d, host, port, *a: calls.append((d, host, port)))
    return calls


def fake_site(d: Path) -> None:
    (d / "data").mkdir(parents=True)
    (d / "data" / "index.json").write_text("{}")


def test_serve_default_dir_is_build_out_of_the_nearest_config(
        tmp_path: Path, served: list[tuple[str, str, int]], monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {out: public/site}\n")
    fake_site(root / "public" / "site")
    (root / "sub").mkdir()
    code, _, err = run(root / "sub", monkeypatch, capsys, "serve", "-p", "9123")
    assert (code, err) == (0, "")
    assert served == [(str(root / "public" / "site"), "127.0.0.1", 9123)]


def test_serve_default_dir_without_a_config(tmp_path: Path, served: list[tuple[str, str, int]],
                                            monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    code, _, err = run(root, monkeypatch, capsys, "serve")
    assert code == 1
    assert err == "buildzr: error: .buildzr/site does not look like a built site (run `buildzr build` first)\n"
    assert served == []
    fake_site(root / ".buildzr" / "site")
    code, _, _ = run(root, monkeypatch, capsys, "serve", "--host", "0.0.0.0")
    assert code == 0 and served == [(".buildzr/site", "0.0.0.0", 8000)]


def test_serve_with_a_dir_does_not_read_the_config(tmp_path: Path, served: list[tuple[str, str, int]],
                                                   monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "build: {k: four}\n")  # broken, but not needed
    fake_site(root / "mysite")
    code, _, err = run(root, monkeypatch, capsys, "serve", "mysite")
    assert (code, err) == (0, "") and served == [("mysite", "127.0.0.1", 8000)]
    code, _, err = run(root, monkeypatch, capsys, "serve")  # now the file is needed
    assert code == 2 and "build.k" in err


def test_serve_port_in_use_exits_1(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path)
    fake_site(root / "s")
    busy = make_server(str(root / "s"), port=0)
    try:
        port = busy.server_address[1]
        code, _, err = run(root, monkeypatch, capsys, "serve", "s", "-p", str(port))
        assert code == 1 and err.startswith(f"buildzr: error: cannot serve on 127.0.0.1:{port}:")
    finally:
        busy.server_close()


def test_serve_has_no_deploy_flags(capsys: pytest.CaptureFixture[str]) -> None:
    for flag in ("--accept-deploys", "--deploy-port", "--max-upload-mb"):
        assert main(["serve", flag]) == 2


def test_plain_serve_stays_read_only(tmp_path: Path) -> None:
    root = tmp_path / "root"
    fake_site(root)
    srv = make_server(str(root), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        url = f"http://127.0.0.1:{srv.server_address[1]}/data/index.json"
        assert get(url)[0] == 200
        for method in ("POST", "PUT", "DELETE", "PATCH"):
            req = urllib.request.Request(url, data=b"{}", method=method)
            with pytest.raises(urllib.error.HTTPError) as ei:
                urllib.request.urlopen(req)
            assert ei.value.code == 501
    finally:
        srv.shutdown()
        srv.server_close()


# --- real layout (Node): the checker accepts what deploy writes ------------------------------------------


@needs_node
def test_real_dir_deploy_passes_the_checker(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                            capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setenv("PYTHONPATH", ROOT)
    monkeypatch.setenv("PR_NUMBER", "42")
    root = project(tmp_path, DEPLOY_YAML)
    code, out, err = run(root, monkeypatch, capsys, "deploy", "-t", "preview")
    assert (code, err) == (0, ""), err
    site = root / "out" / "preview" / "pr" / "42"
    assert (site / "data" / "index.json").is_file()
    assert check_site(str(site / "data"), require_build_json=True).errors == []
    index = json.loads((site / "data" / "index.json").read_text(encoding="utf-8"))
    assert index["model"]["file"].startswith("model.") and (site / "data" / index["model"]["file"]).is_file()
    assert not (site / "data" / "model.json").exists()


REAL_RUNNER = """
import sys
from buildzr.site.build import build_site
build_site(sys.argv[1], sys.argv[2], viewer=False)
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
