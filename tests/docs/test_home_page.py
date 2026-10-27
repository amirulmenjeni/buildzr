"""The home page (docs/index.md) is one part of README.md, with its own link targets; its Quick Start is the real one."""

from __future__ import annotations

import os
import re
from pathlib import Path

import markdown
import pytest

import buildzr.site.cli as cli
from tests.docs.blocks import DOCS, ROOT, extract_blocks, no_run, stub_layout_unless_real

INCLUDE = re.compile(r'^--8<--\s+"(?P<spec>[^"]+)"\s*$')
USED = re.compile(r"\]\[([\w-]+)\]")  # [text][label]: the README links by label
DEFINED = re.compile(r"^\[([\w-]+)\]:\s*(\S+)\s*$", re.MULTILINE)


def read(path: str) -> str:
    with open(path, encoding="utf-8") as f:
        return f.read()


def included_parts() -> list[str]:
    """The text of each ``--8<--`` include of docs/index.md, as the snippets extension builds it."""
    md = markdown.Markdown(
        extensions=["pymdownx.snippets"],
        extension_configs={"pymdownx.snippets": {"base_path": [ROOT], "check_paths": True}},
    )
    return ["\n".join(md.preprocessors["snippet"].run([line]))
            for line in read(os.path.join(DOCS, "index.md")).splitlines() if INCLUDE.match(line)]


def test_home_page_includes_one_readme_part() -> None:
    assert len(included_parts()) == 1


def test_fences_are_balanced() -> None:
    fences = [ln for ln in included_parts()[0].splitlines() if ln.lstrip().startswith("```")]
    assert len(fences) % 2 == 0, "a code fence is cut off"


def test_part_links_by_label_only() -> None:
    """An inline link would keep the address of the README on the home page, which mkdocs does not check."""
    part = included_parts()[0]
    inline = re.findall(r"\]\((?!#)[^)]+\)", re.sub(r"```.*?```", "", part, flags=re.DOTALL))
    assert [i for i in inline if "img.shields.io" not in i and "actions/workflows" not in i
            and "pypi.org" not in i and "structurizr.com" not in i and "astral.sh" not in i
            and "127.0.0.1" not in i] == []


def test_every_label_is_defined_for_the_readme_and_for_the_home_page() -> None:
    labels = set(USED.findall(included_parts()[0]))
    readme = dict(DEFINED.findall(read(os.path.join(ROOT, "README.md"))))
    home = dict(DEFINED.findall(read(os.path.join(DOCS, "index.md"))))
    assert labels and labels <= readme.keys() and labels <= home.keys(), sorted(labels - (readme.keys() & home.keys()))
    assert all(readme[k].startswith(("https://", "docs/")) for k in labels), "the README works on GitHub and PyPI"
    for k in labels:
        target = home[k]
        if target.startswith("http"):  # GitHub pages have no page in docs/; badge images are shields.io
            # the roadmap is not versioned: it is served from master at /roadmap/, outside the docs of a release
            assert target == readme[k] and ("github.com/amirulmenjeni/buildzr" in target
                                            or target.startswith("https://img.shields.io/")
                                            or target == "https://buildzr.dev/roadmap/"), k
        else:
            page = target.split("#")[0]
            assert os.path.isfile(os.path.join(DOCS, page)), f"{k}: docs/{target} does not exist"


# --- the Quick Start of the README --------------------------------------------------------------------------

def model_blocks() -> list[str]:
    return [b.text for b in extract_blocks("README.md", ROOT) if b.directive == ("file", "workspaces/hello.py")]


def test_readme_has_one_model_file() -> None:
    assert len(model_blocks()) == 1


def test_readme_model_file_is_the_complete_example_of_the_quick_start_page() -> None:
    page = [b.text for b in extract_blocks("getting-started/quick-start.md")
            if b.directive == ("file", "workspaces/hello.py")]
    assert no_run(page[-1]) is None
    assert model_blocks() == [page[-1]]


def test_readme_model_file_builds(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                  tmp_path_factory: pytest.TempPathFactory) -> None:
    stub_layout_unless_real(monkeypatch, tmp_path_factory.mktemp("static"))
    (tmp_path / ".git").mkdir()  # so that the config search stops here
    (tmp_path / "workspaces").mkdir()
    (tmp_path / "workspaces" / "hello.py").write_text(model_blocks()[0], encoding="utf-8")
    monkeypatch.chdir(tmp_path)
    assert cli.main(["build"]) == 0
    assert (tmp_path / ".buildzr" / "build" / "hello" / "index.html").is_file()


def test_readme_commands_exist() -> None:
    """The commands of the Quick Start are real: ``buildzr serve`` is a sub command of the parser."""
    ap = cli._parser()
    sub = next(a for a in ap._actions if a.choices and "serve" in a.choices)
    assert {"build", "serve"} <= set(sub.choices)
    assert "uv run buildzr serve" in read(os.path.join(ROOT, "README.md"))
