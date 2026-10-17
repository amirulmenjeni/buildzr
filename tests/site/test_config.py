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
    TargetSpec,
    find_config,
    load_config,
    resolve_build,
    resolve_target,
    resolve_workspace,
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
    text = "workspace: model.py\nbuild:\n  text_color: c4\n  k: four\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:4: build.k: expected a whole number of at least 1, got the text "four"'
    ]


def test_error_secret_key(tmp_path: Path) -> None:
    text = "# 1\n# 2\n# 3\n# 4\n# 5\n# 6\n# 7\ntargets:\n  prod: {url: \"http://127.0.0.1:9101\", token: abc}\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:9: targets.prod: unknown key "token". '
        "Secrets never go in this file; keep them in an environment variable."
    ]


def test_error_unset_variable(tmp_path: Path) -> None:
    text = (
        "version: 1\nworkspace: m.py\nbuild: {k: 4}\ndefault_target: dev\ntargets:\n"
        '  dev: {url: "http://127.0.0.1:8001"}\n'
        '  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}"}\n'
    )
    # path is on line 8 here: pad so the line matches the note's example
    text = text.replace("version: 1\n", "version: 1\n# pad\n")
    cfg = load_config(write(tmp_path, text))
    with pytest.raises(ConfigError) as e:
        resolve_target(cfg, "preview", {})
    assert e.value.problems == [
        'buildzr.yaml:8: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")'
    ]
    # the other target does not need the variable
    assert resolve_target(cfg, "dev", {}).url == "http://127.0.0.1:8001"


def test_error_no_target_named() -> None:
    cfg = Config(
        path=Path("/repo/buildzr.yaml"),
        default_target="dev",
        targets={n: TargetSpec(n, url="http://127.0.0.1:1") for n in ("dev", "preview", "prod")},
    )
    with pytest.raises(ConfigError) as e:
        resolve_target(cfg, "staging", {})
    assert str(e.value) == (
        'buildzr: error: no target named "staging"; targets in /repo/buildzr.yaml: dev (default), preview, prod'
    )


# ------------------------------------------------------------ strict YAML reading


def test_yaml_1_1_traps_stay_text(tmp_path: Path) -> None:
    text = "build:\n  text_color: on\n  viewer: yes\n  k: 1:30\n"
    assert problems(tmp_path, text) == [
        'buildzr.yaml:2: build.text_color: expected wcag or c4, got the text "on"',
        'buildzr.yaml:3: build.viewer: expected true or false, got the text "yes"',
        'buildzr.yaml:4: build.k: expected a whole number of at least 1, got the text "1:30"',
    ]
    assert problems(tmp_path, "workspace: 2026-10-17\nbuild: {out: 0755, k: 0755}\n") == [
        'buildzr.yaml:2: build.k: expected a whole number of at least 1, got the text "0755"',
    ]


def test_text_values_are_not_converted(tmp_path: Path) -> None:
    p = write(tmp_path, "workspace: 0755\nbuild: {out: on, text_color: c4}\ntargets: {no: {dir: y}}\n")
    cfg = load_config(p)
    assert cfg.workspace == "0755"
    assert cfg.build.out == "on"
    assert list(cfg.targets) == ["no"]
    assert cfg.targets["no"].dir == "y"


def test_key_on_stays_text(tmp_path: Path) -> None:
    assert problems(tmp_path, "on: 1\n") == [
        'buildzr.yaml:1: unknown key "on"; allowed keys: version, workspace, build, default_target, targets'
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
    assert problems(tmp_path, "workspace: 5\n") == ["buildzr.yaml:1: workspace: expected text, got the whole number 5"]


def test_duplicate_keys_rejected(tmp_path: Path) -> None:
    assert problems(tmp_path, "workspace: a.py\nworkspace: b.py\n") == [
        'buildzr.yaml:2: duplicate key "workspace" (first used on line 1)'
    ]


@pytest.mark.parametrize(
    "text, fragment",
    [
        ("a: &x 1\nworkspace: *x\n", "anchors (&name)"),
        ("workspace: *x\n", "aliases (*name)"),
        ("workspace: !!str m.py\n", "tags ("),
        ("workspace: !custom m.py\n", "tags ("),
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
    assert cfg.workspace is None and cfg.build == BuildSettings() and not cfg.targets


def test_all_problems_listed_at_once(tmp_path: Path) -> None:
    out = problems(tmp_path, "version: 2\nbuild: {k: x, bogus: 1}\ntargets:\n  Prod: {}\n  b: {dir: a, url: http://h}\n")
    assert len(out) == 6, out
    assert [int(line.split(":")[1]) for line in out] == sorted(int(line.split(":")[1]) for line in out)


# -------------------------------------------------------------------- keys and rules


def test_full_valid_file(tmp_path: Path) -> None:
    cfg = load_config(
        write(
            tmp_path,
            "version: 1\nworkspace: architecture/model.py\n"
            "build: {k: 6, text_color: c4, viewer: false, out: out/site}\n"
            "default_target: preview\n"
            "targets:\n"
            '  preview: {url: "http://127.0.0.1:9001", path: "/pr/42/", timeout: 30, viewer: false}\n'
            "  www: {dir: /var/www/arch}\n",
        )
    )
    assert cfg.build == BuildSettings(6, "c4", False, "out/site")
    assert cfg.default_target == "preview"
    t = resolve_target(cfg, None, {})
    assert (t.name, t.url, t.path, t.viewer, t.timeout, t.dir) == ("preview", "http://127.0.0.1:9001", "pr/42", False, 30.0, None)
    w = resolve_target(cfg, "www", {})
    assert w.dir == Path("/var/www/arch") and w.viewer is False and w.timeout == 120.0
    assert w.site_dir == Path("/var/www/arch")


def test_defaults(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "workspace: m.py\n"))
    b = resolve_build(cfg, {})
    assert (b.k, b.text_color, b.viewer, b.out) == (4, "wcag", True, tmp_path / ".buildzr" / "site")


def test_target_needs_exactly_one_of_dir_url(tmp_path: Path) -> None:
    assert problems(tmp_path, "targets:\n  a: {path: x}\n") == [
        'buildzr.yaml:2: targets.a: expected exactly one of "dir" or "url", got neither'
    ]
    assert problems(tmp_path, "targets:\n  a: {dir: x, url: http://h}\n") == [
        'buildzr.yaml:2: targets.a: expected exactly one of "dir" or "url", got both'
    ]


def test_token_env_rejected_and_secrets(tmp_path: Path) -> None:
    out = problems(tmp_path, "targets:\n  a: {url: http://h, token_env: X}\n")
    assert len(out) == 1 and out[0].startswith("buildzr.yaml:2: targets.a.token_env: token_env is reserved")
    for key in ("token", "password", "secret"):
        out = problems(tmp_path, f"{key}: abc\n")
        assert out == [
            f'buildzr.yaml:1: unknown key "{key}". Secrets never go in this file; keep them in an environment variable.'
        ]


def test_unknown_keys_are_errors(tmp_path: Path) -> None:
    assert problems(tmp_path, "build: {colour: 1}\n") == [
        'buildzr.yaml:1: build: unknown key "colour"; allowed keys: k, text_color, viewer, out'
    ]


def test_default_target_rules(tmp_path: Path) -> None:
    one = load_config(write(tmp_path, "targets: {only: {dir: x}}\n"))
    assert one.default_target == "only"
    assert resolve_target(one, None, {}).name == "only"
    two = load_config(write(tmp_path, "targets: {a: {dir: x}, b: {dir: y}}\n"))
    assert two.default_target is None
    with pytest.raises(ConfigError, match="no target given and no default_target; targets in .*: a, b"):
        resolve_target(two, None, {})
    assert problems(tmp_path, "default_target: z\ntargets: {a: {dir: x}}\n") == [
        'buildzr.yaml:1: default_target: no target named "z" in targets (targets: a)'
    ]


@pytest.mark.parametrize("name", ["Prod", "1a", "a b", "-a"])
def test_target_names(tmp_path: Path, name: str) -> None:
    out = problems(tmp_path, f'targets:\n  "{name}": {{dir: x}}\n')
    assert any("invalid target name" in line for line in out)


@pytest.mark.parametrize(
    "path, expected",
    [("pr/42", "pr/42"), ("/pr/42/", "pr/42"), ("", ""), ("/", ""), ("a.b/c_d-e", "a.b/c_d-e")],
)
def test_path_normalised(tmp_path: Path, path: str, expected: str) -> None:
    cfg = load_config(write(tmp_path, f'targets: {{a: {{dir: x, path: "{path}"}}}}\n'))
    assert resolve_target(cfg, "a", {}).path == expected


@pytest.mark.parametrize("path", ["../x", "a/../b", "a//b", "A/b", ".hidden", "a/ b", "a/_b"])
def test_bad_paths(tmp_path: Path, path: str) -> None:
    out = problems(tmp_path, f'targets: {{a: {{dir: x, path: "{path}"}}}}\n')
    assert len(out) == 1 and out[0].startswith("buildzr.yaml:1: targets.a.path: ")


def test_path_checked_after_expansion(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, 'targets: {a: {dir: x, path: "pr/${N}"}}\n'))
    assert resolve_target(cfg, "a", {"N": "42"}).path == "pr/42"
    with pytest.raises(ConfigError) as e:
        resolve_target(cfg, "a", {"N": ".."})
    assert e.value.problems == ['buildzr.yaml:1: targets.a.path: must not contain a ".." segment']
    with pytest.raises(ConfigError) as e:
        resolve_target(cfg, "a", {"N": "A B"})
    assert "is not allowed" in e.value.problems[0]


@pytest.mark.parametrize("url", ["ftp://h", "h:8000", "http://", "https:/h", "http://a b"])
def test_bad_urls(tmp_path: Path, url: str) -> None:
    out = problems(tmp_path, f'targets: {{a: {{url: "{url}"}}}}\n')
    assert len(out) == 1 and "expected a URL starting with http:// or https://" in out[0]


def test_timeout_rules(tmp_path: Path) -> None:
    assert problems(tmp_path, "targets: {a: {dir: x, timeout: 5}}\n") == [
        'buildzr.yaml:1: targets.a.timeout: only applies to targets with "url"'
    ]
    assert "expected a number of seconds above 0" in problems(tmp_path, "targets: {a: {url: http://h, timeout: 0}}\n")[0]


# ------------------------------------------------------------------ ${VAR} expansion


def cfg_with(tmp_path: Path, path_value: str) -> Config:
    return load_config(write(tmp_path, f"targets:\n  a: {{dir: x, path: '{path_value}'}}\n"))


def test_unset_and_empty_variables(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "pr/${N}")
    for env, state in (({}, "not set"), ({"N": ""}, "empty")):
        with pytest.raises(ConfigError) as e:
            resolve_target(cfg, "a", env)
        assert e.value.problems == [f'buildzr.yaml:2: targets.a.path: environment variable N is {state} (used in "pr/${{N}}")']


def test_fallback(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "pr/${N:-local}")
    assert resolve_target(cfg, "a", {}).path == "pr/local"
    assert resolve_target(cfg, "a", {"N": ""}).path == "pr/local"
    assert resolve_target(cfg, "a", {"N": "7"}).path == "pr/7"


def test_dollar_dollar_is_a_literal_dollar(tmp_path: Path) -> None:
    cfg = load_config(write(tmp_path, "targets: {a: {dir: 'a$$b'}}\n"))
    assert resolve_target(cfg, "a", {}).dir == tmp_path / "a$b"


@pytest.mark.parametrize("value", ["$X", "${x}", "${X", "a$", "${X:-a$b}", "${1X}", "$ {X}"])
def test_bad_dollar_is_an_error_at_load(tmp_path: Path, value: str) -> None:
    out = problems(tmp_path, f"workspace: '{value}'\n")
    assert len(out) == 1 and out[0].startswith('buildzr.yaml:1: workspace: invalid "$"')


def test_several_unset_variables_all_reported(tmp_path: Path) -> None:
    cfg = cfg_with(tmp_path, "${A}/${B}")
    with pytest.raises(ConfigError) as e:
        resolve_target(cfg, "a", {})
    assert len(e.value.problems) == 2


def test_variables_in_other_text_fields(tmp_path: Path) -> None:
    cfg = load_config(
        write(tmp_path, "workspace: '${W}'\nbuild: {out: '${O:-o}'}\ntargets: {a: {url: '${U}'}}\n")
    )
    assert resolve_workspace(cfg, {"W": "m.py"}) == tmp_path / "m.py"
    assert resolve_build(cfg, {}).out == tmp_path / "o"
    assert resolve_target(cfg, "a", {"U": "http://h:1"}).url == "http://h:1"
    with pytest.raises(ConfigError, match="workspace: environment variable W is not set"):
        resolve_workspace(cfg, {})
    with pytest.raises(ConfigError, match="url: expected a URL"):
        resolve_target(cfg, "a", {"U": "nope"})


def test_variables_are_not_read_by_load_config(tmp_path: Path) -> None:
    # loading must succeed with the variable unset: only the resolve calls look at the environment
    load_config(write(tmp_path, "targets: {a: {dir: '${NOPE_NOT_SET}'}}\n"))


# ------------------------------------------------------------------------ discovery


def test_discovery_finds_nearest_and_walks_up(tmp_path: Path) -> None:
    (tmp_path / ".git").mkdir()
    cfg = write(tmp_path, "workspace: m.py\n")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert find_config(deep) == cfg
    inner = write(tmp_path / "a", "workspace: n.py\n")
    assert find_config(deep) == inner
    assert find_config(tmp_path) == cfg


def test_discovery_stops_after_the_git_folder(tmp_path: Path) -> None:
    write(tmp_path, "workspace: outer.py\n")
    repo = tmp_path / "repo"
    (repo / ".git").mkdir(parents=True)
    sub = repo / "x"
    sub.mkdir()
    assert find_config(sub) is None
    # a config in the folder that holds .git is still found
    here = write(repo, "workspace: m.py\n")
    assert find_config(sub) == here


def test_discovery_git_file_also_marks_the_root(tmp_path: Path) -> None:
    write(tmp_path, "workspace: outer.py\n")
    repo = tmp_path / "wt"
    repo.mkdir()
    (repo / ".git").write_text("gitdir: /elsewhere\n")  # a worktree has a .git file
    assert find_config(repo) is None


@pytest.mark.parametrize("name", ["buildzr.yml", ".buildzr.yaml"])
def test_misnamed_file_error(tmp_path: Path, name: str) -> None:
    (tmp_path / ".git").mkdir()
    write(tmp_path, "workspace: m.py\n", name)
    sub = tmp_path / "s"
    sub.mkdir()
    with pytest.raises(ConfigError) as e:
        find_config(sub)
    assert e.value.problems == [f"found {name}; the config file must be named buildzr.yaml"]


def test_correct_name_wins_over_misnamed(tmp_path: Path) -> None:
    write(tmp_path, "workspace: m.py\n", "buildzr.yml")
    good = write(tmp_path, "workspace: m.py\n")
    assert find_config(tmp_path) == good


def test_relative_paths_resolve_against_the_file_folder(tmp_path: Path) -> None:
    proj = tmp_path / "proj"
    (proj / "sub").mkdir(parents=True)
    p = write(proj, "workspace: architecture/model.py\nbuild: {out: out}\ntargets: {a: {dir: ../pub, path: x}}\n")
    cwd = os.getcwd()
    os.chdir(proj / "sub")
    try:
        cfg = load_config(p)
        assert resolve_workspace(cfg, {}) == proj / "architecture" / "model.py"
        assert resolve_build(cfg, {}).out == proj / "out"
        t = resolve_target(cfg, "a", {})
    finally:
        os.chdir(cwd)
    assert t.dir == tmp_path / "pub" and t.site_dir == tmp_path / "pub" / "x"
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
    "workspace-only": ("workspace: architecture/model.py\n", True),
    "full": (
        "version: 1\nworkspace: m.py\nbuild: {k: 4, text_color: wcag, viewer: true, out: .buildzr/site}\n"
        "default_target: dev\ntargets:\n  dev: {url: 'http://127.0.0.1:8001'}\n"
        "  preview: {url: 'http://127.0.0.1:9001', path: 'pr/${PR_NUMBER}', timeout: 30.5}\n  www: {dir: /var/www, viewer: false}\n",
        True,
    ),
    "path-slashes": ("targets: {a: {dir: x, path: '/pr/42/'}}\n", True),
    "version-2": ("version: 2\n", False),
    "k-text": ("build: {k: four}\n", False),
    "k-zero": ("build: {k: 0}\n", False),
    "k-float": ("build: {k: 4.5}\n", False),
    "text-color": ("build: {text_color: rgb}\n", False),
    "viewer-text": ("build: {viewer: 'yes'}\n", False),
    "unknown-top": ("colour: 1\n", False),
    "unknown-build": ("build: {colour: 1}\n", False),
    "secret-token": ("targets: {a: {url: 'http://h', token: x}}\n", False),
    "token-env": ("targets: {a: {url: 'http://h', token_env: X}}\n", False),
    "both-dir-url": ("targets: {a: {dir: x, url: 'http://h'}}\n", False),
    "neither-dir-url": ("targets: {a: {path: x}}\n", False),
    "bad-target-name": ("targets: {Prod: {dir: x}}\n", False),
    "bad-url": ("targets: {a: {url: 'ftp://h'}}\n", False),
    "path-dotdot": ("targets: {a: {dir: x, path: '../x'}}\n", False),
    "path-upper": ("targets: {a: {dir: x, path: 'PR/1'}}\n", False),
    "timeout-on-dir": ("targets: {a: {dir: x, timeout: 5}}\n", False),
    "timeout-zero": ("targets: {a: {url: 'http://h', timeout: 0}}\n", False),
    "default-target-bad-name": ("default_target: Dev\n", False),
    "workspace-number": ("workspace: 5\n", False),
    "targets-list": ("targets: [a, b]\n", False),
}


def schema_valid(text: str) -> bool:
    jsonschema = pytest.importorskip("jsonschema")
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


def test_default_target_unknown_name_is_loader_only(tmp_path: Path) -> None:
    # cross-reference between keys: the schema cannot express it, the loader does
    assert not loader_valid(tmp_path, "default_target: dev\ntargets: {a: {dir: x}}\n")
    assert schema_valid("default_target: dev\ntargets: {a: {dir: x}}\n")
