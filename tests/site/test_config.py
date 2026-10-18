"""Stage 1 of the CLI: the ``buildzr.yaml`` loader, its schema and its error messages."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any, Optional

import pytest
import yaml

from buildzr.site.config import (
    BuildSettings,
    Config,
    ConfigError,
    find_config,
    load_config,
    resolve_build,
    resolve_serve,
    resolve_workspaces,
)

SCHEMA = Path(__file__).resolve().parents[2] / "buildzr" / "site" / "schema" / "config.schema.json"


def write(d: Path, text: str, name: str = "buildzr.yaml") -> Path:
    p = d / name
    p.write_text(text)
    return p


def problems(d: Path, text: str) -> list[str]:
    with pytest.raises(ConfigError) as e:
        load_config(write(d, text))
    return e.value.problems


# --------------------------------------------------------------- the four 4.4 messages


def test_error_text_not_number(tmp_path: Path) -> None:
    text = "workspaces: model.py\nbuild:\n  text_color: c4\n  k: four\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:4: build.k: expected a whole number of at least 1, got the text "four"'
    ]


def test_error_secret_key(tmp_path: Path) -> None:
    text = "# 1\n# 2\n# 3\n# 4\n# 5\n# 6\n# 7\nbuild:\n  token: abc\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:9: build: unknown key "token". '
        "Secrets never go in this file; keep them in an environment variable."
    ]


def test_error_unset_variable(tmp_path: Path) -> None:
    text = "version: 1\n# pad\nworkspaces: m.py\nbuild:\n  k: 4\n  # pad\n  # pad\n  out: \"out/${BRANCH}\"\n"
    cfg = load_config(write(tmp_path, text))
    with pytest.raises(ConfigError) as e:
        resolve_build(cfg, {})
    assert e.value.problems == [
        'buildzr.yaml:8: build.out: environment variable BRANCH is not set (used in "out/${BRANCH}")'
    ]
    # the workspaces folder does not need the variable
    assert resolve_workspaces(cfg, {}) == tmp_path / "m.py"


# ------------------------------------------------------------ strict YAML reading


def test_yaml_1_1_traps_stay_text(tmp_path: Path) -> None:
    text = "build:\n  text_color: on\n  viewer: yes\n  k: 1:30\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:2: build.text_color: expected wcag or c4, got the text "on"',
        'buildzr.yaml:3: build.viewer: expected true or false, got the text "yes"',
        'buildzr.yaml:4: build.k: expected a whole number of at least 1, got the text "1:30"',
    ]
    assert problems(tmp_path, "workspaces: 2026-10-17\nbuild: {out: 0755, k: 0755}\n") == [
        'buildzr.yaml:2: build.k: expected a whole number of at least 1, got the text "0755"',
    ]


def test_text_values_are_not_converted(tmp_path: Path) -> None:
    p = write(tmp_path, "workspaces: 0755\nbuild: {out: on, text_color: c4}\n")
    cfg = load_config(p)
    assert cfg.workspaces == "0755"
    assert cfg.build.out == "on"


def test_key_on_stays_text(tmp_path: Path) -> None:
    assert problems(tmp_path, "on: 1\n") == [
        'buildzr.yaml:1: unknown key "on"; allowed keys: version, workspaces, build, serve'
    ]


def test_types_are_checked_not_converted(tmp_path: Path) -> None:
    assert problems(tmp_path, 'build: {k: "4"}\n') == [
        'buildzr.yaml:1: build.k: expected a whole number of at least 1, got the text "4"'
    ]
    assert problems(tmp_path, "build: {k: 4.0}\n") == [
        "buildzr.yaml:1: build.k: expected a whole number of at least 1, got the number 4.0"
    ]
    assert problems(tmp_path, "build: {k: true}\n") == [
        "buildzr.yaml:1: build.k: expected a whole number of at least 1, got true"
    ]
    assert problems(tmp_path, "build: {k: 0}\n") == [
        "buildzr.yaml:1: build.k: expected a whole number of at least 1, got the whole number 0"
    ]
    assert problems(tmp_path, "workspaces: 5\n") == [
        "buildzr.yaml:1: workspaces: expected a path (text) or a list of files and folders, got the whole number 5"]


def test_duplicate_keys_rejected(tmp_path: Path) -> None:
    assert problems(tmp_path, "workspaces: a.py\nworkspaces: b.py\n") == [
        'buildzr.yaml:2: duplicate key "workspaces" (first used on line 1)'
    ]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("a: &x 1\nworkspaces: *x\n", "anchors (&name)"),
        ("workspaces: *x\n", "aliases (*name)"),
        ("workspaces: !!str m.py\n", "tags ("),
        ("workspaces: !custom m.py\n", "tags ("),
        ("build:\n  <<: {k: 1}\n", "merge keys"),
    ],
)
def test_anchors_aliases_tags_merge_rejected(tmp_path: Path, text: str, fragment: str) -> None:
    out = problems(tmp_path, text)
    assert any(fragment in line for line in out), out


def test_syntax_error_and_multiple_documents(tmp_path: Path) -> None:
    assert "YAML syntax error" in problems(tmp_path, "build: [\n")[0]
    assert problems(tmp_path, "version: 1\n---\nversion: 1\n")[0].startswith("buildzr.yaml:")


def test_empty_file_is_valid(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, ""))
    assert cfg.workspaces is None and cfg.build == BuildSettings()


def test_all_problems_listed_at_once(tmp_path: Path) -> None:
    out = problems(tmp_path, "version: 2\nbuild: {k: x, bogus: 1, viewer: 1}\nworkspaces: 5\ncolour: red\n")
    assert len(out) == 6, out
    assert [int(line.split(":")[1]) for line in out] == sorted(int(line.split(":")[1]) for line in out)


# -------------------------------------------------------------------- keys and rules


def test_full_valid_file(tmp_path: Path) -> None:
    cfg = load_config(
        write(
            tmp_path,
            "version: 1\nworkspaces: architecture/model.py\n"
            "build: {k: 6, text_color: c4, viewer: false, out: out/built}\n",
        )
    )
    assert cfg.build == BuildSettings(6, "c4", False, "out/built")
    assert cfg.workspaces == "architecture/model.py"


def test_defaults(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "workspaces: m.py\n"))
    b = resolve_build(cfg, {})
    assert (b.k, b.text_color, b.viewer, b.out) == (4, "wcag", True, tmp_path / ".buildzr" / "build")


def test_removed_keys_say_what_to_do(tmp_path: Path) -> None:
    text = "version: 1\nworkspace: model.py\ndefault_target: www\ntargets:\n  www: {dir: /var/www}\n"
    assert problems(tmp_path, text) == [
        "buildzr.yaml:2: workspace: removed: use workspaces: (a folder; a single .py file path also works)",
        "buildzr.yaml:3: default_target: removed: buildzr deploy no longer exists; delete this key",
        "buildzr.yaml:4: targets: removed: buildzr deploy no longer exists; delete this key",
    ]
    # a key of the same name inside build: is just unknown
    assert problems(tmp_path, "build: {targets: 1}\n") == [
        'buildzr.yaml:1: build: unknown key "targets"; allowed keys: k, text_color, viewer, out'
    ]


def test_secret_keys_get_their_own_message(tmp_path: Path) -> None:
    for key in ("token", "password", "secret"):
        out = problems(tmp_path, f"{key}: abc\n")
        assert out == [
            f'buildzr.yaml:1: unknown key "{key}". Secrets never go in this file; keep them in an environment variable.'
        ]


def test_unknown_keys_are_errors(tmp_path: Path) -> None:
    assert problems(tmp_path, "build: {colour: 1}\n") == [
        'buildzr.yaml:1: build: unknown key "colour"; allowed keys: k, text_color, viewer, out'
    ]


# ------------------------------------------------------------------ ${VAR} expansion


def cfg_with(tmp_path: Path, out_value: str) -> Config:
    return load_config(write(tmp_path, f"build:\n  out: '{out_value}'\n"))


def test_unset_and_empty_variables(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "pr/${N}")
    for env, state in (({}, "not set"), ({"N": ""}, "empty")):
        with pytest.raises(ConfigError) as e:
            resolve_build(cfg, env)
        assert e.value.problems == [f'buildzr.yaml:2: build.out: environment variable N is {state} (used in "pr/${{N}}")']


def test_fallback(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "pr/${N:-local}")
    assert resolve_build(cfg, {}).out == tmp_path / "pr" / "local"
    assert resolve_build(cfg, {"N": ""}).out == tmp_path / "pr" / "local"
    assert resolve_build(cfg, {"N": "7"}).out == tmp_path / "pr" / "7"


def test_dollar_dollar_is_a_literal_dollar(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "build: {out: 'a$$b'}\n"))
    assert resolve_build(cfg, {}).out == tmp_path / "a$b"


@pytest.mark.parametrize("value", ["$X", "${x}", "${X", "a$", "${X:-a$b}", "${1X}", "$ {X}"])
def test_bad_dollar_is_an_error_at_load(tmp_path: Path, value: str) -> None:
    out = problems(tmp_path, f"workspaces: '{value}'\n")
    assert len(out) == 1 and out[0].startswith('buildzr.yaml:1: workspaces: invalid "$"')


def test_several_unset_variables_all_reported(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "${A}/${B}")
    with pytest.raises(ConfigError) as e:
        resolve_build(cfg, {})
    assert len(e.value.problems) == 2


def test_variables_in_other_text_fields(tmp_path: Path) -> None:
    cfg = load_config(
        write(tmp_path, "workspaces: '${W}'\nbuild: {out: '${O:-o}'}\n")
    )
    assert resolve_workspaces(cfg, {"W": "m.py"}) == tmp_path / "m.py"
    assert resolve_build(cfg, {}).out == tmp_path / "o"
    with pytest.raises(ConfigError, match="workspaces: environment variable W is not set"):
        resolve_workspaces(cfg, {})


def test_variables_are_not_read_by_load_config(tmp_path: Path) -> None:
    # loading must succeed with the variable unset: only the resolve calls look at the environment
    load_config(write(tmp_path, "build: {out: '${NOPE_NOT_SET}'}\n"))


# ------------------------------------------------------------------------ discovery


def test_discovery_finds_nearest_and_walks_up(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    cfg = write(tmp_path, "workspaces: m.py\n")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_config(deep) == cfg
    inner = write(tmp_path / "a", "workspaces: n.py\n")
    assert find_config(deep) == inner
    assert find_config(tmp_path) == cfg


def test_discovery_stops_after_the_git_folder(tmp_path: Path) -> None:
    write(tmp_path, "workspaces: outer.py\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "x"
    sub.mkdir()
    assert find_config(sub) is None
    # a config in the folder that holds .git is still found
    here = write(repo, "workspaces: m.py\n")
    assert find_config(sub) == here


def test_discovery_git_file_also_marks_the_root(tmp_path: Path) -> None:
    write(tmp_path, "workspaces: outer.py\n")
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n")  # a worktree has a .git file
    assert find_config(repo) is None


@pytest.mark.parametrize("name", ["buildzr.yml", ".buildzr.yaml"])
def test_misnamed_file_error(tmp_path: Path, name: str) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path, "workspaces: m.py\n", name)
    sub = tmp_path / "s"
    sub.mkdir()
    with pytest.raises(ConfigError) as e:
        find_config(sub)
    assert e.value.problems == [f"found {name}; the config file must be named buildzr.yaml"]


def test_correct_name_wins_over_misnamed(tmp_path: Path) -> None:
    write(tmp_path, "workspaces: m.py\n", "buildzr.yml")
    good = write(tmp_path, "workspaces: m.py\n")
    assert find_config(tmp_path) == good


def test_relative_paths_resolve_against_the_file_folder(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    p = write(proj, "workspaces: architecture/model.py\nbuild: {out: ../pub}\n")
    cwd = os.getcwd()
    os.chdir(proj / "sub")
    try:
        cfg = load_config(p)
        assert resolve_workspaces(cfg, {}) == proj / "architecture" / "model.py"
        assert resolve_build(cfg, {}).out == tmp_path / "pub"
    finally:
        os.chdir(cwd)
    assert cfg.root == proj


def test_unreadable_file(tmp_path: Path) -> None:
    with pytest.raises(ConfigError, match="cannot read"):
        load_config(tmp_path / "missing.yaml")


# ------------------------------------------------------ light import, schema agreement


def test_import_buildzr_does_not_import_yaml() -> None:
    code = (
        "import sys, buildzr, buildzr.dsl\n"
        "bad = [m for m in sys.modules if m == 'yaml' or m.startswith('yaml.')]\n"
        "sys.exit(1 if bad else 0)\n"
    )
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    r2 = subprocess.run([sys.executable, "-c", "import sys, buildzr.site.config; sys.exit(0 if 'yaml' in sys.modules else 1)"])
    assert r2.returncode == 0  # sanity: the config module does import it


# fixture name -> (text, valid)
FIXTURES: dict[str, tuple[str, bool]] = {
    "empty": ("", True),
    "workspaces-only": ("workspaces: architecture\n", True),
    "workspaces-file": ("workspaces: architecture/model.py\n", True),
    "old-workspace": ("workspace: model.py\n", False),
    "old-targets": ("targets: {www: {dir: x}}\n", False),
    "old-default-target": ("default_target: www\n", False),
    "full": (
        "version: 1\nworkspaces: m.py\nbuild: {k: 4, text_color: wcag, viewer: true, out: 'out/${BRANCH:-main}'}\n",
        True,
    ),
    "version-2": ("version: 2\n", False),
    "k-text": ("build: {k: four}\n", False),
    "k-zero": ("build: {k: 0}\n", False),
    "k-float": ("build: {k: 4.5}\n", False),
    "text-color": ("build: {text_color: rgb}\n", False),
    "viewer-text": ("build: {viewer: 'yes'}\n", False),
    "unknown-top": ("colour: 1\n", False),
    "unknown-build": ("build: {colour: 1}\n", False),
    "secret-token": ("build: {token: x}\n", False),
    "workspaces-number": ("workspaces: 5\n", False),
    "list-text": ("workspaces: [architecture/billing.py, shared-models/]\n", True),
    "list-mixed": ("build: {k: 4}\nworkspaces:\n  - architecture/billing.py\n  - path: architecture/platform.py\n"
                   "    build: {k: 9, text_color: c4}\n  - path: architecture/api_catalog.py\n"
                   "    build: {viewer: false}\n  - path: '${TEAM}/x.py'\n", True),
    "list-empty": ("workspaces: []\n", False),
    "list-number": ("workspaces: [5]\n", False),
    "list-empty-path": ("workspaces: ['']\n", False),
    "list-no-path": ("workspaces: [{build: {k: 2}}]\n", False),
    "list-unknown-key": ("workspaces: [{path: a.py, name: A}]\n", False),
    "list-out": ("workspaces: [{path: a.py, build: {out: x}}]\n", False),
    "list-bad-k": ("workspaces: [{path: a.py, build: {k: 0}}]\n", False),
    "list-bad-viewer": ("workspaces: [{path: a.py, build: {viewer: 'no'}}]\n", False),
    "list-bad-color": ("workspaces: [{path: a.py, build: {text_color: rgb}}]\n", False),
    "build-list": ("build: [a, b]\n", False),
    "serve-all": ("serve: {public_url: 'https://a.example.com/', port: 8080, host: 0.0.0.0, "
                  "cors_origins: ['https://b.example.com', 'http://localhost:3000']}\n", True),
    "serve-empty-origins": ("serve: {cors_origins: []}\n", True),
    "serve-env": ("serve: {public_url: '${URL}', host: '${HOST:-127.0.0.1}', cors_origins: ['${ORIGIN}']}\n", True),
    "serve-ftp": ("serve: {public_url: 'ftp://a.example.com'}\n", False),
    "serve-query": ("serve: {public_url: 'https://a.example.com/?x=1'}\n", False),
    "serve-port-0": ("serve: {port: 0}\n", False),
    "serve-port-big": ("serve: {port: 65536}\n", False),
    "serve-port-text": ("serve: {port: '8080'}\n", False),
    "serve-port-env": ("serve: {port: '${PORT}'}\n", False),
    "serve-host-empty": ("serve: {host: ''}\n", False),
    "serve-origin-path": ("serve: {cors_origins: ['https://b.example.com/app']}\n", False),
    "serve-origin-star": ("serve: {cors_origins: ['*']}\n", False),
    "serve-origins-text": ("serve: {cors_origins: 'https://b.example.com'}\n", False),
    "serve-unknown": ("serve: {tls: true}\n", False),
}


def schema_valid(text: str) -> bool:
    import jsonschema  # type: ignore[import-untyped]
    data: Any = yaml.safe_load(text)
    schema = json.loads(SCHEMA.read_text())
    jsonschema.Draft202012Validator.check_schema(schema)
    return not list(jsonschema.Draft202012Validator(schema).iter_errors(data if data is not None else {}))


def loader_valid(tmp_path: Path, text: str) -> bool:
    try:
        load_config(write(tmp_path, text))
    except ConfigError:
        return False
    return True


@pytest.mark.parametrize("name", sorted(FIXTURES))
def test_loader_and_schema_agree(tmp_path: Path, name: str) -> None:
    text, valid = FIXTURES[name]
    assert loader_valid(tmp_path, text) is valid, "loader"
    assert schema_valid(text) is valid, "schema"


# --------------------------------------------------------------- serve:


def test_serve_keys_load_and_resolve(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "serve:\n  public_url: https://arch.example.com/\n  port: 8080\n"
                                      "  host: 0.0.0.0\n  cors_origins:\n    - https://b.example.com\n"
                                      "    - https://b.example.com\n"))
    s = resolve_serve(cfg, {})
    assert (s.public_url, s.port, s.host, s.cors_origins) == (
        "https://arch.example.com", 8080, "0.0.0.0", ["https://b.example.com"])  # the trailing / goes, as for the option
    assert resolve_serve(load_config(write(tmp_path, "version: 1\n")), {}) == resolve_serve(
        load_config(write(tmp_path, "serve: {}\n")), {})
    unset = resolve_serve(load_config(write(tmp_path, "version: 1\n")), {})
    assert (unset.public_url, unset.port, unset.host, unset.cors_origins) == (None, None, None, None)
    assert resolve_serve(load_config(write(tmp_path, "serve: {cors_origins: []}\n")), {}).cors_origins == []


def test_serve_values_are_checked_with_the_option_wording(tmp_path: Path) -> None:
    from buildzr.site.api import normalise_origin, normalise_public_url
    with pytest.raises(ValueError) as url_err:
        normalise_public_url("ftp://a.example.com")
    with pytest.raises(ValueError) as origin_err:
        normalise_origin("https://b.example.com/app")
    assert problems(tmp_path, "serve:\n  public_url: ftp://a.example.com\n  port: 0\n  host: ''\n"
                              "  cors_origins:\n    - https://ok.example.com\n    - https://b.example.com/app\n"
                              "  tls: true\n") == [
        f"buildzr.yaml:2: serve.public_url: {url_err.value}",
        "buildzr.yaml:3: serve.port: expected a whole number from 1 to 65535, got the whole number 0",
        "buildzr.yaml:4: serve.host: expected a host name or address, got empty text",
        f"buildzr.yaml:7: serve.cors_origins[1]: {origin_err.value}",
        'buildzr.yaml:8: serve: unknown key "tls"; allowed keys: public_url, port, host, cors_origins',
    ]
    assert problems(tmp_path, "serve: {port: 65536}\n") == [
        "buildzr.yaml:1: serve.port: expected a whole number from 1 to 65535, got the whole number 65536"]
    assert problems(tmp_path, "serve: {port: '${PORT}'}\n") == [
        'buildzr.yaml:1: serve.port: expected a whole number from 1 to 65535, got the text "${PORT}"']
    assert problems(tmp_path, "serve: {cors_origins: https://b.example.com}\n") == [
        'buildzr.yaml:1: serve.cors_origins: expected a list of origins, got the text "https://b.example.com"']


def test_serve_text_is_expanded_from_the_environment(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "serve:\n  public_url: ${PUBLIC_URL}\n  host: ${HOST:-127.0.0.1}\n"
                                      "  cors_origins: ['${DASHBOARD}', 'https://fixed.example.com']\n"))
    s = resolve_serve(cfg, {"PUBLIC_URL": "https://pr-42.example.com/", "DASHBOARD": "https://dash.example.com"})
    assert (s.public_url, s.host, s.cors_origins) == (
        "https://pr-42.example.com", "127.0.0.1", ["https://dash.example.com", "https://fixed.example.com"])
    with pytest.raises(ConfigError) as e:
        resolve_serve(cfg, {})
    assert e.value.problems == [
        'buildzr.yaml:2: serve.public_url: environment variable PUBLIC_URL is not set (used in "${PUBLIC_URL}")',
        'buildzr.yaml:4: serve.cors_origins[0]: environment variable DASHBOARD is not set (used in "${DASHBOARD}")',
    ]
    with pytest.raises(ConfigError) as e:  # an expanded value is checked like the option
        resolve_serve(cfg, {"PUBLIC_URL": "pr-42.example.com", "DASHBOARD": "https://dash.example.com/x"})
    assert [p.split(": ", 2)[1] for p in e.value.problems] == ["serve.public_url", "serve.cors_origins[0]"]
    assert "expected an http:// or https:// URL" in e.value.problems[0]


def test_build_never_reads_the_serve_section(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "serve: {public_url: '${UNSET_URL}'}\n"))
    resolve_build(cfg, {})  # no error: the unset variable matters only to serve
    with pytest.raises(ConfigError):
        resolve_serve(cfg, {})
