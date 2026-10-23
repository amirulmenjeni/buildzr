"""``docs/model-api.md`` between its generated markers is what ``scripts/gen_api_reference.py`` writes."""

from __future__ import annotations

import importlib.util
import os
import re
from types import ModuleType

import pytest

from tests.docs.blocks import ROOT

SCRIPT = os.path.join(ROOT, "scripts", "gen_api_reference.py")


@pytest.fixture(scope="module")
def gen() -> ModuleType:
    spec = importlib.util.spec_from_file_location("gen_api_reference", SCRIPT)
    assert spec is not None and spec.loader is not None
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_the_page_is_what_a_fresh_generation_writes(gen: ModuleType) -> None:
    with open(gen.PAGE, encoding="utf-8") as f:
        old = f.read()
    assert gen.generate(old) == old, "docs/model-api.md is out of date; run: python scripts/gen_api_reference.py"


def test_the_script_checks_without_writing(gen: ModuleType) -> None:
    before = open(gen.PAGE, encoding="utf-8").read()
    assert gen.main(["--check"]) == 0
    assert open(gen.PAGE, encoding="utf-8").read() == before


def test_drift_is_found(gen: ModuleType) -> None:
    with open(gen.PAGE, encoding="utf-8") as f:
        old = f.read()
    stale = old.replace("| `view` | `/<name>/api/v1/view?key={key}`", "| `view` | `/<name>/api/v1/view?name={key}`")
    assert stale != old and gen.generate(stale) == old


def test_only_the_marked_lines_change(gen: ModuleType) -> None:
    text = f"hand written\n{gen.BEGIN}\nold\n{gen.END}\nalso hand written\n"
    new = gen.generate(text)
    assert new.startswith("hand written\n" + gen.BEGIN + "\n| Name |") and new.endswith(gen.END + "\nalso hand written\n")
    assert "old" not in new


def test_every_endpoint_of_the_orientation_document_has_a_row_in_the_hand_written_table(gen: ModuleType) -> None:
    doc = gen.orientation()
    with open(gen.PAGE, encoding="utf-8") as f:
        text = f.read()
    hand = text.split("## Endpoints")[1].split("### `element`")[0]
    for template in doc["endpoints"].values():
        path = template.split("/api/v1/")[1].split("?")[0].split("{")[0]
        assert re.search(rf"^\| `{path}` \|", hand, re.M), f"no row for {path} in the table of endpoints"
    assert re.search(r"^\| `` \(empty\) \|", hand, re.M)
