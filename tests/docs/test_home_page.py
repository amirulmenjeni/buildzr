"""The home page (docs/index.md) is built from parts of README.md; the parts are the intended ones."""

from __future__ import annotations

import os
import re

import markdown

from tests.docs.blocks import DOCS, ROOT

INCLUDE = re.compile(r'^--8<--\s+"(?P<spec>[^"]+)"\s*$')
IMAGE = "![Example"


def included_parts() -> list[str]:
    """The text of each ``--8<--`` include of docs/index.md, as the snippets extension builds it."""
    md = markdown.Markdown(
        extensions=["pymdownx.snippets"],
        extension_configs={"pymdownx.snippets": {"base_path": [ROOT], "check_paths": True}},
    )
    with open(os.path.join(DOCS, "index.md"), encoding="utf-8") as f:
        lines = f.read().splitlines()
    parts = []
    for line in lines:
        if INCLUDE.match(line):
            parts.append("\n".join(md.preprocessors["snippet"].run([line])))
    return parts


def test_home_page_includes_two_readme_parts() -> None:
    assert len(included_parts()) == 2


def test_fences_are_balanced_in_each_part() -> None:
    for part in included_parts():
        fences = [ln for ln in part.splitlines() if ln.lstrip().startswith("```")]
        assert len(fences) % 2 == 0, "a code fence is cut off"


def test_first_part_has_the_whole_quickstart_and_no_images() -> None:
    first = included_parts()[0]
    lines = first.rstrip("\n").splitlines()
    assert lines[-1].strip() == "```", "the quickstart code block must end the first part (with its closing fence)"
    assert "w.save(format='svg'" in first
    assert IMAGE not in first, "the images come from docs/index.md, not from the README part"


def test_second_part_runs_from_ready_to_dive_in_to_the_contributing_link() -> None:
    lines = included_parts()[1].strip().splitlines()
    assert lines[0].startswith("Ready to dive in?")
    assert lines[-1].startswith("- [Contributing Guide]")
