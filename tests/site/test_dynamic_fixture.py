"""Dynamic views: what the viewer needs to step through their interactions.

The viewer reads the ``order`` of each edge of a dynamic view's scene (and its label for the step's text); nothing is
added to the built workspace for stepping, so these tests pin what it relies on, on a real build (the committed fixture).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from buildzr.site.build import build_workspace
from buildzr.site.check import check_built
from tests.site.test_cli import ROOT, needs_node

Json = dict[str, Any]

FIXTURE = Path(ROOT) / "tests" / "site" / "fixtures" / "dynamic"


def scene(key: str) -> Json:
    index = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    sc: Json = json.loads((FIXTURE / index["scenes"][key]["file"]).read_text(encoding="utf-8"))
    return sc


def test_the_committed_fixture_passes_the_checker() -> None:
    rep = check_built(str(FIXTURE))
    assert rep.errors == []
    index = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    assert sorted(index["scenes"]) == ["e/shop", "landscape", "v/checkout", "v/shop-containers", "v/sign-in"]


def test_every_step_is_an_edge_with_its_order_and_text() -> None:
    edges = sorted(scene("v/checkout")["edges"], key=lambda e: int(e["order"]))
    assert [(e["id"], e["order"]) for e in edges] == [
        ("customer->shop/web-app#1", "1"),
        ("shop/web-app->shop/api#2", "2"),
        ("shop/api->shop/database#3", "3"),
        ("shop/api->payments#4", "4"),
        ("shop/web-app->shop/api#5", "5"),
    ]
    assert edges[1]["label"]["lines"][0]["text"] == "2: Posts the order to"
    assert [e["order"] for e in scene("v/sign-in")["edges"]] == ["1", "2"]


def test_other_views_have_no_order() -> None:
    for key in ("v/shop-containers", "landscape", "e/shop"):
        assert all("order" not in e for e in scene(key)["edges"]), key


@needs_node
def test_the_committed_fixture_is_what_the_workspace_builds(tmp_path: Path) -> None:
    src = tmp_path / "workspace.py"
    src.write_text("from tests.site.dynamic_workspace import dynamic_workspace\nw = dynamic_workspace()\n", encoding="utf-8")
    info = build_workspace(str(src), str(tmp_path / "out"), viewer=False)
    assert info.get("status") == "ok", info.get("errors")
    built = json.loads((tmp_path / "out" / "data" / "index.json").read_text(encoding="utf-8"))
    committed = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    assert built == committed, "run tests/site/fixtures/make_dynamic.py"
    shutil.rmtree(tmp_path / "out")
