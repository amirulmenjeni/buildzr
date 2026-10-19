"""The agent skill in ``skills/buildzr`` is installable and true: its frontmatter, its size, its words, its links,
and every Python example in it builds."""

from __future__ import annotations

import glob
import json
import os
import re
from pathlib import Path

import pytest
import yaml

import buildzr.site.cli as cli
from buildzr.dsl import Workspace
from tests.docs.blocks import SKILLS, Block, extract_blocks, stub_layout_unless_real

SKILL = os.path.join(SKILLS, "buildzr")
MAX_CHARS = 10_000
LINK = re.compile(r"\]\(([^)\s]+)\)")


def skill_files() -> list[str]:
    """SKILL.md and every page of ``references/``, relative to the skills folder."""
    refs = os.path.join(SKILL, "references")
    pages = sorted(f for f in os.listdir(refs) if f.endswith(".md")) if os.path.isdir(refs) else []
    return ["buildzr/SKILL.md"] + [f"buildzr/references/{f}" for f in pages]


def read(rel: str) -> str:
    with open(os.path.join(SKILLS, rel), encoding="utf-8") as f:
        return f.read()


def frontmatter() -> dict[str, object]:
    text = read("buildzr/SKILL.md")
    assert text.startswith("---\n"), "SKILL.md starts with YAML frontmatter"
    meta = yaml.safe_load(text.split("---\n", 2)[1])
    assert isinstance(meta, dict)
    return meta


def test_frontmatter_has_name_and_description() -> None:
    meta = frontmatter()
    assert meta.get("name") == "buildzr"
    description = meta.get("description")
    assert isinstance(description, str) and description.startswith("Use when"), description


def test_skill_md_is_short() -> None:
    assert len(read("buildzr/SKILL.md")) <= MAX_CHARS


@pytest.mark.parametrize("rel", skill_files())
def test_no_site_vocabulary(rel: str) -> None:
    """The build writes built workspaces into the build output; the skill never calls them a site."""
    found = [line for line in read(rel).split("\n") if re.search(r"\bsites?\b", line, re.IGNORECASE)]
    assert not found, found


@pytest.mark.parametrize("rel", skill_files())
def test_relative_links_resolve(rel: str) -> None:
    here = os.path.dirname(os.path.join(SKILLS, rel))
    for target in LINK.findall(read(rel)):
        if re.match(r"^[a-z]+:", target) or target.startswith("#"):
            continue
        assert os.path.exists(os.path.join(here, target.split("#")[0])), f"{rel}: {target}"


def python_blocks() -> list[Block]:
    return [b for rel in skill_files() for b in extract_blocks(rel, root=SKILLS) if b.lang == "python"]


def test_the_dsl_reference_has_three_complete_examples() -> None:
    assert len([b for b in python_blocks() if b.page.endswith("references/dsl.md")]) >= 3


@pytest.mark.parametrize("block", python_blocks(), ids=lambda b: b.id)
def test_every_python_example_builds(block: Block, tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                     tmp_path_factory: pytest.TempPathFactory) -> None:
    stub_layout_unless_real(monkeypatch, tmp_path_factory.mktemp("static"))
    (tmp_path / ".git").mkdir()  # so that the config search stops here
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "model.py").write_text(block.text, encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 0
    built = list((tmp_path / ".buildzr" / "build").iterdir())
    assert len(built) == 1 and (built[0] / "index.html").is_file(), built
    with open(glob.glob(str(built[0] / "data" / "model.*.json"))[0], encoding="utf-8") as f:
        built_views = {v["viewKey"] for v in json.load(f)["views"]}
    written = authored_views(block)
    deployment = written.pop("deploymentViews", set())
    assert not built_views & deployment, ("buildzr now builds deployment views: update the deployment notes of "
                                          "skills/buildzr (SKILL.md, references/dsl.md) and docs/getting-started/ai-agents.md")
    assert built_views == set().union(*written.values()), "every view but the deployment views is built"


def authored_views(block: Block) -> dict[str, set[str]]:
    """The view keys of the example's workspace, by Structurizr view list."""
    scope: dict[str, object] = {}
    exec(compile(block.text, block.id, "exec"), scope)
    [w] = [v for v in scope.values() if isinstance(v, Workspace)]
    views = json.loads(w.to_json())["views"]
    return {name: {v["key"] for v in items} for name, items in views.items() if isinstance(items, list) and items}
