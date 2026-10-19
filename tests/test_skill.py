"""The agent skill in ``skills/buildzr`` is installable and true: its frontmatter, its size, its words, its links,
and every Python example in it builds."""

from __future__ import annotations

import os
import re
from pathlib import Path

import pytest
import yaml

from tests.docs.blocks import SKILLS, Block, authored_views, build_and_check_views, extract_blocks

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
    build_and_check_views(block.text, block.id, tmp_path, monkeypatch, tmp_path_factory)


def test_an_example_has_a_deployment_view() -> None:
    """The skill shows a deployment view that builds (the test above checks that it is drawn)."""
    assert any("deploymentViews" in authored_views(b.text, b.id) for b in python_blocks())
