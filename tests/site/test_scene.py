"""Scene emit: schema-exact objects, labels, ordering, edge labels."""

from __future__ import annotations

import copy
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from buildzr.site.check import check_built
from buildzr.site.layout import layout_workspace

SMALL = Path(__file__).parent / "fixtures" / "small"

pytestmark = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")

Json = dict[str, Any]


def _load(p: Path) -> Json:
    out: Json = json.loads(p.read_text(encoding="utf-8"))
    return out


def _build(tmp: Path, levels: Json) -> dict[str, Json]:
    layout_workspace(levels, _load(SMALL / "model.json"), str(tmp))
    assert check_built(str(tmp)).errors == []
    index = _load(tmp / "index.json")
    return {k: _load(tmp / v["file"]) for k, v in index["scenes"].items()}


def test_edge_labels_are_wrapped_placed_and_inside_bounds(tmp_path: Path) -> None:
    levels = _load(SMALL / "levels.json")
    lv = copy.deepcopy(levels)
    for level in lv["levels"]:
        for e in level["edges"]:
            e["lines"] = [{"text": "Sends a long description of what happens here", "tier": 0, "size": 12},
                          {"text": "[HTTPS]", "tier": 1, "size": 11}]
    sc = _build(tmp_path, lv)
    n = 0
    for s in sc.values():
        bx, by, bw, bh = s["bounds"]
        for e in s["edges"]:
            lab = e["label"]
            n += 1
            assert len(lab["lines"]) >= 3  # 200 px wrap splits the long sentence
            assert [ln["tier"] for ln in lab["lines"]][-1] == 1
            assert lab["w"] > 0 and lab["h"] > 0
            # the label box lies within the drawing (landscape, views) or the element box
            assert bx - 0.5 <= lab["x"] and lab["x"] + lab["w"] <= bx + bw + 0.5
            assert by - 0.5 <= lab["y"] and lab["y"] + lab["h"] <= by + bh + 0.5
    assert n > 20


def test_scene_shape_and_ordering(tmp_path: Path) -> None:
    sc = _build(tmp_path, _load(SMALL / "levels.json"))
    land = sc["landscape"]
    assert land["schema"] == "buildzr.scene/2" and land["ports"] == []
    assert land["layout"]["engine"] == "elkjs" and land["layout"]["version"] == "0.12.0"
    assert land["layout"]["inputHash"].startswith("sha256:")
    assert land["layout"]["passes"] == 2  # sides + final: nothing above it needs a size
    assert sc["e/billing"]["layout"]["passes"] == 3  # sizes, sides, final
    assert sc["e/billing/api"]["layout"]["passes"] == 2  # no frames inside: no sides pass
    for s in sc.values():
        assert [e["id"] for e in s["edges"]] == sorted(e["id"] for e in s["edges"])
        assert all(e["count"] == len(e["rels"]) for e in s["edges"])
        assert "elk.algorithm" in s["layout"]["options"]
        assert not any(k.startswith("org.eclipse.elk.json") for k in s["layout"]["options"])
    api = sc["e/billing/api"]
    assert [p["id"] for p in api["ports"]] == sorted(p["id"] for p in api["ports"])
    assert {p["side"] for p in api["ports"]} <= {"N", "E", "S", "W"}
    b = sc["landscape"]["nodes"][0]
    assert {"id", "role", "type", "parent", "x", "y", "w", "h", "shape", "style", "label", "tags", "name"} <= set(b)
    # frame labels keep tier/weight/size from levels.json and are wrapped to the frame width
    billing = next(n for n in land["nodes"] if n["id"] == "billing")
    assert billing["frame"]["children"] == 3 and billing["frame"]["childType"] == "Container"
    assert billing["frame"]["scene"] == "e/billing"
    assert [ln["tier"] for ln in billing["label"]["lines"]][0] == 0
    assert billing["label"]["lines"][0]["weight"] == "bold"


def test_node_sizes_are_whole_pixels_for_leaves(tmp_path: Path) -> None:
    sc = _build(tmp_path, _load(SMALL / "levels.json"))
    for s in sc.values():
        for n in s["nodes"]:
            if "frame" not in n and n["role"] == "element":
                assert n["w"] == int(n["w"]) and n["h"] == int(n["h"])


def test_groups_become_boundaries_in_generated_levels(tmp_path: Path) -> None:
    """Group boundaries in the landscape / an element level hold their members; frames may sit inside them."""
    levels = _load(SMALL / "levels.json")
    lv = copy.deepcopy(levels)
    land = lv["levels"][0]
    g = {"id": "group:core", "lines": [{"text": "Core", "tier": 0, "weight": "bold"}], "name": "Core",
         "parent": None, "role": "boundary", "shape": "Box", "tags": ["Element", "Group"], "type": "Group",
         "style": {"color": "#000000", "dash": [6, 4], "fill": "#ffffff", "fontSize": 16, "stroke": "#888888"}}
    land["nodes"].append(g)
    for n in land["nodes"]:
        if n["id"] in ("billing", "crm"):
            n["parent"] = "group:core"
    sc = _build(tmp_path, lv)
    nodes = {n["id"]: n for n in sc["landscape"]["nodes"]}
    assert nodes["group:core"]["role"] == "boundary" and "frame" not in nodes["group:core"]
    assert nodes["billing"]["parent"] == "group:core" and "frame" in nodes["billing"]
    ids = [n["id"] for n in sc["landscape"]["nodes"]]
    assert ids.index("group:core") < ids.index("billing")
