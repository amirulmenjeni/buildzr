"""The product roadmap: ``roadmap.yml`` is validated and rendered into the page ``roadmap.md`` by the mkdocs hooks."""

from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

import pytest
import yaml
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.exceptions import PluginError
from mkdocs.structure.files import Files

from tests.docs.blocks import DOCS, ROOT
from tests.docs.test_runcode_assets import _load

hooks = _load("mkdocs_hooks")

ROADMAP = os.path.join(ROOT, "roadmap.yml")


def valid() -> dict[str, Any]:
    return {
        "version": 1,
        "active": [{"id": "one", "title": "One", "description": "The first."}],
        "planned": [
            {"target": "1.0", "items": [{"id": "two", "title": "Two", "description": "The second.",
                                          "link": "https://example.com/two"}]},
            {"target": "Later", "items": [{"id": "three", "title": "Three <b>", "description": "A & B."}]},
        ],
        "launched": [
            {"version": "0.0.2", "date": "2026-02-02", "link": "https://example.com/v2",
             "items": [{"id": "four", "title": "Four", "description": "The fourth."}]},
            {"version": "0.0.1", "date": "2026-01-01", "items": [{"id": "five", "title": "Five", "description": "5."}]},
        ],
    }


def errors_of(change: Any) -> str:
    data = copy.deepcopy(valid())
    change(data)
    return "\n".join(hooks.validate_roadmap(data))


def test_the_roadmap_of_the_repository_is_valid_and_has_the_agreed_shape() -> None:
    data = hooks.load_roadmap(ROADMAP)
    assert hooks.validate_roadmap(data) == []
    assert data["version"] == 1
    assert [g["target"] for g in data["planned"]] == ["1.2", "Later"]
    assert data["launched"][0]["version"] == "1.1.0"
    assert all(r["date"] for r in data["launched"])
    assert not os.path.exists(os.path.join(DOCS, "roadmap.md")), "the page is generated, not committed"
    assert not os.path.exists(os.path.join(ROOT, "ROADMAP.md"))


def test_a_valid_roadmap_has_no_errors() -> None:
    assert hooks.validate_roadmap(valid()) == []
    data = valid()
    del data["launched"]
    assert hooks.validate_roadmap(data) == []


@pytest.mark.parametrize("change, expected", [
    (lambda d: d.update(version=2), "version: must be 1"),
    (lambda d: d.pop("version"), "missing the required key 'version'"),
    (lambda d: d.update(extra=1), "unknown key 'extra'"),
    (lambda d: d.update(active=[]), "active: must be a non-empty list"),
    (lambda d: d["planned"].append({"target": "1.1", "items": []}), "planned[2].items: must be a non-empty list"),
    (lambda d: d["planned"][0].update(target="soon"), "planned[0].target"),
    (lambda d: d["planned"][0].update(target="2026-12"), "never a date"),
    (lambda d: d["planned"][1].update(target="1.0"), "'1.0' is listed twice"),
    (lambda d: d["planned"].insert(0, d["planned"].pop()), "'Later' target must be the last"),
    (lambda d: d["active"][0].pop("description"), "active[0]: missing the required key 'description'"),
    (lambda d: d["active"][0].update(owner="x"), "active[0]: unknown key 'owner'"),
    (lambda d: d["active"][0].update(id="Not Kebab"), "active[0].id: must be kebab-case"),
    (lambda d: d["active"][0].update(id="rm-active"), "reserved"),
    (lambda d: d["active"][0].update(title="  "), "active[0].title: must be a non-empty text"),
    (lambda d: d["active"][0].update(title="x" * 81), "the limit is 80"),
    (lambda d: d["active"][0].update(description="a\nb"), "one line"),
    (lambda d: d["active"][0].update(link="http://example.com"), "absolute https:// URL"),
    (lambda d: d["active"][0].update(link="/relative"), "absolute https:// URL"),
    (lambda d: d["launched"][0].update(date="16 Oct"), "launched[0].date: must be a calendar date"),
    (lambda d: d["launched"][0].update(date="2026-13-40"), "launched[0].date"),
    (lambda d: d["launched"][0].update(date="2025-01-01"), "list the newest release first"),
    (lambda d: d["launched"][1].update(version="0.0.2"), "launched[1].version: '0.0.2' is listed twice"),
    (lambda d: d["launched"][0].update(version="v1"), "launched[0].version"),
    (lambda d: d["launched"][0].update(version="1.0.0rc"), "launched[0].version"),
    (lambda d: d["launched"][0].update(version="1.0.0dev1"), "launched[0].version"),
    (lambda d: d["launched"][0].update(link="ftp://x/y"), "launched[0].link"),
    (lambda d: d["launched"][0].update(items=[]), "launched[0].items: must be a non-empty list"),
])
def test_validation_names_the_fault_and_where(change: Any, expected: str) -> None:
    assert expected in errors_of(change)


def test_a_release_candidate_is_a_launched_version() -> None:
    assert errors_of(lambda d: d["launched"][0].update(version="1.0.0rc1")) == ""


def test_an_id_is_unique_across_every_status() -> None:
    message = errors_of(lambda d: d["launched"][0]["items"][0].update(id="one"))
    assert "launched[0].items[0].id: 'one' is already used at active[0]" in message


def test_an_item_is_not_placed_twice_under_another_id() -> None:
    message = errors_of(lambda d: d["planned"][0]["items"][0].update(title="one"))
    assert "already the title of active[0]" in message


def test_every_fault_is_reported_at_once() -> None:
    def change(d: dict[str, Any]) -> None:
        d["version"] = 3
        d["active"][0]["id"] = "BAD"
        d["planned"][0]["target"] = "x"
    assert len(errors_of(change).splitlines()) == 3


def test_a_key_given_twice_is_refused(tmp_path: Path) -> None:
    path = tmp_path / "roadmap.yml"
    path.write_text("version: 1\nversion: 1\n", encoding="utf-8")
    with pytest.raises(PluginError, match="given twice"):
        hooks.load_roadmap(str(path))
    path.write_text("version: [1\n", encoding="utf-8")
    with pytest.raises(PluginError, match="not valid YAML"):
        hooks.load_roadmap(str(path))
    with pytest.raises(PluginError, match="Cannot read the roadmap"):
        hooks.load_roadmap(str(tmp_path / "missing.yml"))


def test_render_groups_by_status_and_target_and_escapes_text() -> None:
    page = hooks.render_roadmap(valid())
    assert page == hooks.render_roadmap(copy.deepcopy(valid()))
    order = [page.index(h) for h in ("# Roadmap", "## Active", "## Planned", "### Aiming for 1.0", "### Later",
                                     "## Launched", "### [0.0.2](https://example.com/v2) · 2 February 2026",
                                     "### 0.0.1 · 1 January 2026")]
    assert order == sorted(order)
    assert '<li id="one"><strong>One</strong>' in page
    assert '<a href="https://example.com/two">Two</a>' in page
    assert "Three &lt;b&gt;" in page and "A &amp; B." in page and "<b>" not in page
    assert "{ #rm-active }" in page and "{ #rm-target-1-0 }" in page and "{ #rm-release-0-0-2 }" in page
    assert "structurizr-compatibility.md" in page
    data = valid()
    del data["launched"]
    assert "Launched" not in hooks.render_roadmap(data)


def test_a_roadmap_without_active_work_renders_no_active_section() -> None:
    data = valid()
    del data["active"]
    assert hooks.validate_roadmap(data) == []
    page = hooks.render_roadmap(data)
    assert "Active" not in page and "{ #rm-planned }" in page


def test_render_accepts_unquoted_yaml_dates() -> None:
    data = yaml.safe_load(yaml.safe_dump(valid(), default_flow_style=False).replace("'2026-02-02'", "2026-02-02"))
    assert "2 February 2026" in hooks.render_roadmap(data)


def _config(root: Path) -> Any:
    (root / "docs").mkdir(exist_ok=True)
    config = MkDocsConfig()
    config.load_dict({"site_name": "t", "docs_dir": str(root / "docs"), "site_dir": str(root / "site")})
    errors, warnings = config.validate()
    assert not errors, errors
    setattr(config.plugins, "_current_plugin", "hooks")  # set by mkdocs while a plugin event runs
    return config


def test_the_hook_adds_the_generated_page_and_the_build_stops_on_a_bad_roadmap(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (tmp_path / "roadmap.yml").write_text(yaml.safe_dump(valid()), encoding="utf-8")
    files = hooks.on_files(Files([]), config)
    page = files.get_file_from_path("roadmap.md")
    assert page is not None and page.content_string.startswith("---\ntitle: Roadmap")

    (tmp_path / "roadmap.yml").write_text("version: 1\nactive: []\nplanned: []\n", encoding="utf-8")
    with pytest.raises(PluginError, match=r"roadmap\.yml is not a valid roadmap[\s\S]*active: must be"):
        hooks.on_files(Files([]), config)


def test_the_hook_refuses_a_committed_roadmap_page(tmp_path: Path) -> None:
    config = _config(tmp_path)
    (tmp_path / "roadmap.yml").write_text(yaml.safe_dump(valid()), encoding="utf-8")
    (tmp_path / "docs" / "roadmap.md").write_text("# Old\n", encoding="utf-8")
    from mkdocs.structure.files import File
    files = Files([File("roadmap.md", config["docs_dir"], config["site_dir"], True)])
    with pytest.raises(PluginError, match="must not exist"):
        hooks.on_files(files, config)


def test_nav_style_and_readme_wire_the_roadmap_in() -> None:
    with open(os.path.join(ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        config = f.read()
    for needle in ("- Roadmap: roadmap.md", "- Structurizr compatibility: structurizr-compatibility.md",
                   "stylesheets/roadmap.css"):
        assert needle in config
    with open(os.path.join(ROOT, "README.md"), encoding="utf-8") as f:
        assert "[roadmap]: https://buildzr.dev/roadmap/" in f.read()
    with open(os.path.join(DOCS, "structurizr-compatibility.md"), encoding="utf-8") as f:
        text = f.read()
    assert "Compatibility is not the roadmap" in text and "roadmap.md" in text
