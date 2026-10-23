"""The Publishing pages agree with the code and with each other: options, hash links, links between pages, the nav."""

from __future__ import annotations

import argparse
import importlib
import os
import re
from typing import Any
from urllib.parse import unquote

import pytest

import buildzr.site.cli as cli
from tests.docs.blocks import DOCS, PAGES, ROOT, extract_blocks

OPTION = re.compile(r"(?<![\w-])(--?[A-Za-z][\w-]*)")


def parser_options(command: str) -> tuple[set[str], set[str]]:
    """All option strings of a sub command of the real parser, and the first one of each (what a usage line shows).
    ``-h``/``--help`` and hidden options are left out."""
    ap = cli._parser()
    sub = next(a for a in ap._actions if a.choices and command in a.choices)  # the sub parsers action
    found: set[str] = set()
    first: set[str] = set()
    choices: Any = sub.choices
    for action in choices[command]._actions:
        if action.help == argparse.SUPPRESS or "-h" in action.option_strings:
            continue
        found.update(action.option_strings)
        first.update(action.option_strings[:1])
    return found, first


@pytest.mark.parametrize("command", ["build", "export", "serve"])
def test_cli_page_lists_exactly_the_options_of_the_parser(command: str) -> None:
    with open(os.path.join(DOCS, "cli.md"), encoding="utf-8") as f:
        text = f.read()
    start = text.index(f"### `buildzr {command}`")
    end = text.index("\n### ", start + 1) if "\n### " in text[start + 1:] else len(text)
    end = min(e for e in (text.find("\n### ", start + 1), text.find("\n## ", start + 1)) if e > 0)
    section = text[start:end]
    table = [l for l in section.split("\n") if l.startswith("| `")]
    documented: set[str] = set()
    for row in table:
        cell = row.split("|")[1]
        documented.update(o for o in OPTION.findall(cell) if o not in ("-h", "--help"))
    expected, first = parser_options(command)
    assert documented == expected, (sorted(documented - expected), sorted(expected - documented))
    synopsis = re.search(r"```text\n(buildzr " + command + r" .*)\n```", section)
    assert synopsis is not None
    assert {o for o in OPTION.findall(synopsis.group(1)) if o not in ("-h", "--help")} == first


def test_config_page_and_cli_page_have_one_description_of_the_flags() -> None:
    """The flags are described on the command line page only; the other pages point there."""
    with open(os.path.join(DOCS, "config.md"), encoding="utf-8") as f:
        text = f.read()
    assert "buildzr build [" not in text and "| Exit code |" not in text


# --- viewer links -----------------------------------------------------------------------------------------

SEGMENT = re.compile(r"[a-z0-9-]+")


def check_hash(h: str) -> None:
    """The grammar of ``viewer-hash-routes.md``, applied to one hash."""
    assert h.startswith("#/"), h
    route, _, query = h[2:].partition("?")
    parts = route.split("/")
    if parts[0] == "m":
        assert all(SEGMENT.fullmatch(p) for p in parts[1:]), h
    else:
        assert parts[0] == "v" and len(parts) == 2 and SEGMENT.fullmatch(parts[1]), h
    order = ["sel", "q", "tags", "mode"]
    seen = []
    for param in query.split("&") if query else []:
        key, _, value = param.partition("=")
        assert key in order and value, (h, key)
        seen.append(key)
        if key == "mode":
            assert value == "and", f"mode=or is never written: {h}"
        if key == "tags":
            assert all(unquote(t) for t in value.split(",")), h
    assert seen == sorted(seen, key=order.index), f"keys out of order in {h}"


def hash_lines() -> list[str]:
    out = []
    for page in PAGES:
        for b in extract_blocks(page):
            if b.lang in ("", "text") and b.text.lstrip().startswith("#/"):
                out += [l for l in b.text.split("\n") if l.strip()]
    return out


def test_every_hash_example_follows_the_grammar() -> None:
    lines = hash_lines()
    assert len(lines) >= 10
    for line in lines:
        check_hash(line.strip())


@pytest.mark.parametrize("bad", ["#m", "#/x", "#/m/Billing", "#/m?q=a&sel=b", "#/m?mode=or", "#/v/a/b"])
def test_the_grammar_check_rejects_what_the_page_says_is_wrong(bad: str) -> None:
    with pytest.raises(AssertionError):
        check_hash(bad)


# --- links and navigation ---------------------------------------------------------------------------------

LINK = re.compile(r"\]\(([^)\s]+)\)")


def headings(page: str) -> set[str]:
    pytest.importorskip("markdown")
    slugify = importlib.import_module("markdown.extensions.toc").slugify  # the slugs mkdocs makes
    with open(os.path.join(DOCS, page), encoding="utf-8") as f:
        return {slugify(m.group(1).replace("`", ""), "-") for m in re.finditer(r"^#{1,6} (.+?)\s*$", f.read(), re.M)}


@pytest.mark.parametrize("page", PAGES)
def test_links_between_pages_resolve(page: str) -> None:
    with open(os.path.join(DOCS, page), encoding="utf-8") as f:
        text = f.read()
    text = re.sub(r"```.*?```", "", text, flags=re.S)
    for target in LINK.findall(text):
        if re.match(r"[a-z]+:", target):
            continue
        name, _, anchor = target.partition("#")
        dest = page if not name else os.path.normpath(os.path.join(os.path.dirname(page), name))
        assert os.path.isfile(os.path.join(DOCS, dest)), f"{page}: {target} does not exist"
        if anchor:
            assert anchor in headings(dest), f"{page}: {target}: no such heading"


def test_the_publishing_section_is_in_the_nav_in_order() -> None:
    with open(os.path.join(ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        nav = f.read().split("\nnav:\n")[1].split("\nextra:")[0]
    files = re.findall(r":\s+(\S+\.md)\s*$", nav, re.M)
    pub = ["serve-workspaces.md", "cli.md", "config.md", "publishing-recipes.md", "hosting.md", "ui-settings.md",
           "viewer-hash-routes.md"]
    i = files.index("serve-workspaces.md")
    assert files[i:i + len(pub)] == pub
    assert files.index("user-guide/export.md") < i < files.index("api/dsl.md")
    assert files[files.index("api/models.md") + 1] == "model-api.md"
    for p in PAGES:
        assert p in files, f"{p} is not in the nav"
