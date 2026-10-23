"""``workspaces:`` as a list in ``buildzr.yaml``: which files are built, and the build settings of each entry."""

from __future__ import annotations

import json
import threading
import urllib.request
from pathlib import Path
from typing import Any, Optional

import pytest

import buildzr.site.build as build_mod
import buildzr.site.cli as cli
from buildzr.site.config import (
    ConfigError,
    WorkspaceEntry,
    load_config,
    resolve_workspace_entries,
    workspace_files,
)
from buildzr.site.serve import make_server
from tests.site.test_build_all import HEAD, built, info, tree, ws
from tests.site.test_cli import make_static, project, run, served, stubbed  # noqa: F401  (fixtures)

Json = dict[str, Any]

LIST = """\
build:
  k: 4
workspaces:
  - architecture/billing.py
  - path: architecture/platform.py
    build:
      k: 9
  - path: architecture/api_catalog.py
    build:
      viewer: false
"""


def write(root: Path, text: str) -> Path:
    p = root / "buildzr.yaml"
    p.write_text(text)
    return p


def problems(root: Path, text: str) -> list[str]:
    with pytest.raises(ConfigError) as e:
        load_config(write(root, text))
    return e.value.problems


def resolved_problems(root: Path, text: str, env: Optional[dict[str, str]] = None) -> list[str]:
    cfg = load_config(write(root, text))
    with pytest.raises(ConfigError) as e:
        workspace_files(cfg, resolve_workspace_entries(cfg, env or {}) or [])
    return e.value.problems


# --- the loader ---------------------------------------------------------------------------------------------------


def test_a_plain_path_is_still_one_path(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "workspaces: architecture\n"))
    assert (cfg.workspaces, cfg.workspace_list) == ("architecture", None)
    assert resolve_workspace_entries(cfg, {}) is None


def test_text_and_mapping_entries(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, LIST + "  - path: shared-models/\n    build: {text_color: c4}\n"))
    assert cfg.workspaces is None
    assert cfg.workspace_list == (
        WorkspaceEntry("architecture/billing.py", "workspaces[0]"),
        WorkspaceEntry("architecture/platform.py", "workspaces[1]", k=9),
        WorkspaceEntry("architecture/api_catalog.py", "workspaces[2]", viewer=False),
        WorkspaceEntry("shared-models/", "workspaces[3]", text_color="c4"),
    )
    entries = resolve_workspace_entries(cfg, {})
    assert entries is not None
    assert [(e.path, e.key, e.line) for e in entries] == [
        (tmp_path / "architecture" / "billing.py", "workspaces[0]", 4),
        (tmp_path / "architecture" / "platform.py", "workspaces[1]", 5),
        (tmp_path / "architecture" / "api_catalog.py", "workspaces[2]", 8),
        (tmp_path / "shared-models", "workspaces[3]", 11),
    ]


def test_entry_problems_name_the_key_and_the_line(tmp_path: Path) -> None:
    text = ("workspaces:\n"
            "  - a.py\n"
            "  - path: b.py\n"
            "    name: B\n"
            "  - path: c.py\n"
            "    build:\n"
            "      k: 0\n"
            "      out: elsewhere\n"
            "      colour: red\n"
            "  - build: {k: 2}\n"
            "  - 5\n"
            "  - ''\n"
            "  - path: d.py\n"
            "    build: [k]\n")
    assert problems(tmp_path, text) == [
        'buildzr.yaml:4: workspaces[1]: unknown key "name"; allowed keys: path, build',
        "buildzr.yaml:7: workspaces[2].build.k: expected a whole number of at least 1, got the whole number 0",
        'buildzr.yaml:8: workspaces[2].build: unknown key "out": the build output is the same for every workspace; '
        "set build.out at the top of the file, not in a workspaces entry",
        'buildzr.yaml:9: workspaces[2].build: unknown key "colour"; allowed keys: k, text_color, viewer',
        "buildzr.yaml:10: workspaces[3]: path: is missing; give the file or folder to build",
        "buildzr.yaml:11: workspaces[4]: expected a path (text) or a mapping with path: and build:, "
        "got the whole number 5",
        "buildzr.yaml:12: workspaces[5]: expected a file or a folder, got empty text",
        "buildzr.yaml:14: workspaces[6].build: expected a mapping, got a list",
    ]


def test_bad_entry_settings(tmp_path: Path) -> None:
    text = "workspaces:\n  - path: a.py\n    build: {text_color: rgb, viewer: 'no'}\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:3: workspaces[0].build.text_color: expected wcag or c4, got the text "rgb"',
        'buildzr.yaml:3: workspaces[0].build.viewer: expected true or false, got the text "no"',
    ]


def test_an_empty_list_is_an_error(tmp_path: Path) -> None:
    assert problems(tmp_path, "workspaces: []\n") == [
        "buildzr.yaml:1: workspaces: expected at least one file or folder, got an empty list"]


def test_variables_in_a_path(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "workspaces:\n  - ${TEAM}/billing.py\n  - path: '${TEAM:-x}/platform.py'\n"))
    entries = resolve_workspace_entries(cfg, {"TEAM": "architecture"})
    assert entries is not None
    assert [e.path for e in entries] == [tmp_path / "architecture" / "billing.py",
                                         tmp_path / "architecture" / "platform.py"]
    assert [e.shown for e in entries] == ["architecture/billing.py", "architecture/platform.py"]
    with pytest.raises(ConfigError) as e:
        resolve_workspace_entries(cfg, {})
    assert e.value.problems == [
        'buildzr.yaml:2: workspaces[0]: environment variable TEAM is not set (used in "${TEAM}/billing.py")']
    assert problems(tmp_path, "workspaces:\n  - path: '$x.py'\n")[0].startswith(
        'buildzr.yaml:2: workspaces[0].path: invalid "$" at position 1')


def test_missing_and_duplicate_files(tmp_path: Path) -> None:
    tree(tmp_path, {"architecture/billing.py": HEAD, "architecture/platform.py": HEAD, "notes.md": "x"})
    assert resolved_problems(tmp_path, "workspaces:\n  - architecture/billing.py\n  - architecture/missing.py\n"
                                       "  - notes.md\n") == [
        "buildzr.yaml:3: workspaces[1]: architecture/missing.py not found (relative to buildzr.yaml's folder)",
        "buildzr.yaml:4: workspaces[2]: expected a .py file or a folder, got notes.md",
    ]
    assert resolved_problems(tmp_path, "workspaces:\n  - architecture/billing.py\n  - path: architecture/billing.py\n"
                                       "    build: {k: 2}\n") == [
        "buildzr.yaml:3: workspaces[1]: architecture/billing.py is already in workspaces[0] (line 2); "
        "list each file once"]
    # via a folder entry, in either order
    assert resolved_problems(tmp_path, "workspaces:\n  - architecture/platform.py\n  - architecture\n") == [
        "buildzr.yaml:3: workspaces[1]: architecture holds architecture/platform.py, which is already in "
        "workspaces[0] (line 2); list each file once"]
    assert resolved_problems(tmp_path, "workspaces:\n  - architecture/\n  - ./architecture/platform.py\n") == [
        "buildzr.yaml:3: workspaces[1]: ./architecture/platform.py is already in workspaces[0] (line 2); "
        "list each file once"]


# --- building -----------------------------------------------------------------------------------------------------


@pytest.fixture
def static(monkeypatch: pytest.MonkeyPatch, tmp_path_factory: pytest.TempPathFactory) -> Path:
    """Build with a small viewer bundle instead of the real one."""
    d = make_static(tmp_path_factory.mktemp("static"))
    real = cli.build_all

    def with_static(path: Any, out: str, *a: Any, **kw: Any) -> Any:
        return real(path, out, *a, **{**kw, "static_dir": str(d)})
    monkeypatch.setattr(cli, "build_all", with_static)
    return d


@pytest.fixture
def arch(tmp_path: Path, stubbed: None, static: Path) -> Path:
    """The architecture project of docs/config.md, with the list of :data:`LIST`."""
    root = project(tmp_path, LIST, ws=False)
    tree(root / "architecture", {
        "billing.py": HEAD + ws("Billing"),
        "platform.py": HEAD + ws("Core") + ws("Infra"),
        "api_catalog.py": HEAD + ws("API Catalog"),
        "_shared.py": "OWNER = 'platform team'\n",
        "draft.py": HEAD + ws("Draft"),  # not listed: never built
    })
    return root


def settings(root: Path, name: str) -> tuple[Any, Any, bool]:
    i = info(root, name)
    return i["k"], i["textColor"], (root / ".buildzr" / "build" / name / "index.html").is_file()


def test_only_the_listed_files_are_built_each_with_its_settings(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    code, out, err = run(arch, monkeypatch, capsys, "build")
    assert (code, err) == (0, "")
    assert built(arch) == ["api-catalog", "billing", "core", "infra"]
    assert settings(arch, "billing") == (4, "wcag", True)
    assert settings(arch, "core") == settings(arch, "infra") == (9, "wcag", True)
    assert settings(arch, "api-catalog") == (4, "wcag", False)
    core = info(arch, "core")
    assert core["input"]["file"] == "architecture/platform.py"  # type: ignore[index]
    assert (core["workspacesFolder"], core["workspacesList"]) == ("../..", "../../buildzr.yaml")


def test_a_folder_entry_gives_its_settings_to_every_file_in_it(tmp_path: Path, stubbed: None, static: Path,
                                                               monkeypatch: pytest.MonkeyPatch,
                                                               capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces:\n  - one.py\n  - path: shared-models/\n    build: {k: 7, text_color: c4}\n"
                             "  - empty/\n", ws=False)
    tree(root, {"one.py": HEAD + ws("One"), "shared-models/a.py": HEAD + ws("A"),
                "shared-models/deep/b.py": HEAD + ws("B"), "shared-models/_util.py": "", "empty/_only.py": ""})
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 0
    assert err == ("buildzr: warning: buildzr.yaml:5: workspaces[2]: empty/ holds no Python file that can create a "
                   "workspace; nothing is built from it\n")
    assert built(root) == ["a", "b", "one"]
    assert settings(root, "a")[:2] == settings(root, "b")[:2] == (7, "c4")
    assert settings(root, "one")[:2] == (4, "wcag")


def test_a_list_that_builds_nothing(tmp_path: Path, stubbed: None, monkeypatch: pytest.MonkeyPatch,
                                    capsys: pytest.CaptureFixture[str]) -> None:
    root = project(tmp_path, "workspaces: [empty]\n", ws=False)
    (root / "empty").mkdir()
    code, out, err = run(root, monkeypatch, capsys, "build")
    assert code == 1 and err.splitlines()[-1] == (
        "buildzr: error: no workspace found in the workspaces: list of buildzr.yaml: no .py file there creates a "
        "Workspace")


def test_a_missing_entry_stops_build_and_serve(arch: Path, served: list[Any], monkeypatch: pytest.MonkeyPatch,
                                               capsys: pytest.CaptureFixture[str]) -> None:
    (arch / "architecture" / "billing.py").unlink()
    msg = "buildzr.yaml:4: workspaces[0]: architecture/billing.py not found (relative to buildzr.yaml's folder)\n"
    assert run(arch, monkeypatch, capsys, "build")[::2] == (2, msg)
    assert run(arch, monkeypatch, capsys, "serve")[::2] == (2, msg)
    assert built(arch) == [] and served == []


#: setting -> (option, the entry's build:, the global build:, the value with the option, then the entry, then the
#: global build:, then the default). Each level sets a value the next one down does not have.
PRECEDENCE = {
    "k": (["--k", "2"], "k: 9", "k: 6", (2, 9, 6, 4)),
    "text_color": (["--text-color", "c4"], "text_color: wcag", "text_color: c4", ("c4", "wcag", "c4", "wcag")),
    "viewer": (["--no-viewer"], "viewer: true", "viewer: false", (False, True, False, True)),
}


@pytest.mark.parametrize("setting", sorted(PRECEDENCE))
def test_option_then_entry_then_global_then_default(tmp_path: Path, stubbed: None, static: Path, setting: str,
                                                    monkeypatch: pytest.MonkeyPatch,
                                                    capsys: pytest.CaptureFixture[str]) -> None:
    option, entry, top, values = PRECEDENCE[setting]
    root = project(tmp_path, "", ws=False)
    tree(root, {"a.py": HEAD + ws("A")})
    both = f"build: {{{top}}}\nworkspaces:\n  - path: a.py\n    build: {{{entry}}}\n"
    cases = [(both, option), (both, []), (f"build: {{{top}}}\nworkspaces:\n  - a.py\n", []), ("workspaces: [a.py]\n", [])]
    got = []
    for text, argv in cases:
        write(root, text)
        assert run(root, monkeypatch, capsys, "build", *argv)[0] == 0
        got.append(settings(root, "a")[("k", "text_color", "viewer").index(setting)])
    assert tuple(got) == values


def test_changing_one_entry_rebuilds_only_its_file(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    assert run(arch, monkeypatch, capsys, "build")[0] == 0
    before = {n: info(arch, n)["fingerprint"] for n in built(arch)}
    write(arch, LIST.replace("k: 9", "k: 12"))
    code, out, _ = run(arch, monkeypatch, capsys, "build")
    assert code == 0
    after = {n: info(arch, n)["fingerprint"] for n in built(arch)}
    assert [n for n in after if after[n] != before[n]] == ["core", "infra"]
    assert info(arch, "core")["k"] == 12
    # serve sees the same: the rest is up to date
    write(arch, LIST.replace("k: 9", "k: 13"))
    monkeypatch.setattr(cli, "serve", lambda *a, **kw: None)
    code, out, _ = run(arch, monkeypatch, capsys, "serve")
    assert code == 0 and out.splitlines()[0] == "up to date: api-catalog, billing"
    assert "built .buildzr/build/core (" in out and info(arch, "infra")["k"] == 13


def test_a_file_taken_off_the_list_loses_its_workspaces(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                         capsys: pytest.CaptureFixture[str]) -> None:
    assert run(arch, monkeypatch, capsys, "build")[0] == 0
    shorter = LIST.replace("  - path: architecture/platform.py\n    build:\n      k: 9\n", "")
    write(arch, shorter)
    # -w FILE removes nothing
    code, out, _ = run(arch, monkeypatch, capsys, "build", "-w", "architecture/billing.py")
    assert code == 0 and "removed" not in out
    assert built(arch) == ["api-catalog", "billing", "core", "infra"]
    code, out, _ = run(arch, monkeypatch, capsys, "build")
    assert code == 0
    assert out.splitlines()[-2:] == [
        "removed core: its model file architecture/platform.py is no longer in the workspaces: list",
        "removed infra: its model file architecture/platform.py is no longer in the workspaces: list",
    ]
    assert built(arch) == ["api-catalog", "billing"]


def test_w_replaces_the_list_and_keeps_the_global_settings(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    write(arch, "build: {k: 5}\n" + LIST.split("\n", 2)[2])
    code, out, _ = run(arch, monkeypatch, capsys, "build", "-w", "architecture/platform.py")
    assert code == 0 and built(arch) == ["core", "infra"]
    assert settings(arch, "core") == (5, "wcag", True)  # the entry's k: 9 does not apply
    i = info(arch, "core")
    assert (i["input"]["file"], i["workspacesFolder"], "workspacesList" in i) == (  # type: ignore[index]
        "platform.py", "../../architecture", False)
    # -w FOLDER: a full build of that folder, which builds draft.py too, and removes nothing of the list's
    assert run(arch, monkeypatch, capsys, "build")[0] == 0
    code, out, _ = run(arch, monkeypatch, capsys, "build", "-w", "architecture")
    assert code == 0 and "removed" not in out
    assert built(arch) == ["api-catalog", "billing", "core", "draft", "infra"]


def test_another_config_never_removes_the_workspaces_of_a_list(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                                capsys: pytest.CaptureFixture[str]) -> None:
    assert run(arch, monkeypatch, capsys, "build")[0] == 0
    (arch / "other.yaml").write_text("workspaces:\n  - architecture/draft.py\n")
    code, out, _ = run(arch, monkeypatch, capsys, "build", "-c", "other.yaml")
    assert code == 0 and "removed" not in out
    assert built(arch) == ["api-catalog", "billing", "core", "draft", "infra"]
    # and the list removes nothing of the other config's
    code, out, _ = run(arch, monkeypatch, capsys, "build")
    assert code == 0 and "removed" not in out and "draft" in built(arch)


def test_a_data_only_entry_is_served_without_a_viewer(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                      capsys: pytest.CaptureFixture[str]) -> None:
    answers: dict[str, Any] = {}

    def real(directory: str, host: str, port: int, public_url: Optional[str], origins: list[str], **kw: Any) -> None:
        srv = make_server(directory, port=0)
        threading.Thread(target=srv.serve_forever, daemon=True).start()
        base = f"http://127.0.0.1:{srv.server_address[1]}"
        try:
            for path in ("/", "/_buildzr/v1/workspaces", "/api-catalog/api/v1/", "/core/api/v1/"):
                with urllib.request.urlopen(base + path) as r:
                    body = r.read().decode()
                    answers[path] = body if path == "/" else json.loads(body)
        finally:
            srv.shutdown()
            srv.server_close()
    monkeypatch.setattr(cli, "serve", real)
    code, out, err = run(arch, monkeypatch, capsys, "serve")
    assert (code, err) == (0, "")
    listed = {w["name"]: w for w in answers["/_buildzr/v1/workspaces"]["workspaces"]}
    assert sorted(listed) == ["api-catalog", "billing", "core", "infra"]
    assert listed["api-catalog"]["viewerUrl"] is None and listed["api-catalog"]["apiUrl"] == "/api-catalog/api/v1/"
    assert listed["core"]["viewerUrl"] == "/core/"
    assert answers["/api-catalog/api/v1/"]["viewerUrl"] is None
    assert answers["/core/api/v1/"]["viewerUrl"] == "/core/"
    index = answers["/"]
    assert '<li><a href="/core/">core</a> &middot; Core' in index
    assert ('<li>api-catalog <small>(data only, no viewer: <a href="/api-catalog/api/v1/">Model API</a>)</small> '
            "&middot; API Catalog") in index


def test_the_check_and_the_names_still_apply(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                             capsys: pytest.CaptureFixture[str]) -> None:
    (arch / "architecture" / "billing.py").write_text("raise RuntimeError('boom')\n")
    code, out, err = run(arch, monkeypatch, capsys, "build")
    assert code == 1
    assert "buildzr: BROKEN: workspace billing (architecture/billing.py) failed at the model step" in err
    assert info(arch, "billing")["status"] == "broken" and info(arch, "core")["status"] == "ok"
    (arch / "architecture" / "billing.py").write_text(HEAD + ws("Core"))
    code, out, err = run(arch, monkeypatch, capsys, "build")
    assert code == 1 and 'two workspaces would both be built as "core"' in err


def test_a_build_json_of_a_list_matches_its_schema(arch: Path, monkeypatch: pytest.MonkeyPatch,
                                                   capsys: pytest.CaptureFixture[str]) -> None:
    import jsonschema  # type: ignore[import-untyped]

    assert run(arch, monkeypatch, capsys, "build")[0] == 0
    schema = json.loads((Path(build_mod.__file__).parent / "schema" / "build.schema.json").read_text())
    for name in built(arch):
        jsonschema.validate(info(arch, name), schema)
