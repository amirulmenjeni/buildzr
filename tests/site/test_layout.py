"""Three-pass reserved-frame layout on the small fixture: checker, frames, third-level continuity, determinism."""

from __future__ import annotations

import json
import math
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from buildzr.site.check import check_built
from buildzr.site.layout import layout_workspace
from buildzr.site.layout.passes import LEAF_H, LEAF_W, reserve

SMALL = Path(__file__).parent / "fixtures" / "small"

pytestmark = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")

Json = dict[str, Any]


def _load(p: Path) -> Json:
    out: Json = json.loads(p.read_text(encoding="utf-8"))
    return out


@pytest.fixture(scope="module")
def built(tmp_path_factory: pytest.TempPathFactory) -> tuple[Path, Json]:
    out = tmp_path_factory.mktemp("small-built")
    metrics = layout_workspace(_load(SMALL / "levels.json"), _load(SMALL / "model.json"), str(out))
    return out, metrics


def _scenes(d: Path) -> dict[str, Json]:
    index = _load(d / "index.json")
    return {k: _load(d / v["file"]) for k, v in index["scenes"].items()}


def test_checker_passes_with_zero_errors(built: tuple[Path, Json]) -> None:
    d, metrics = built
    rep = check_built(str(d))
    assert rep.errors == []
    m = rep.metrics["scenes"]
    assert m["bad_edges"] == 0
    assert m["ports"] > 0 and m["port_sides_kept"] == m["ports"]
    assert m["port_gap_px"] <= 1.5
    assert m["frames"] == 2
    assert metrics["scenes"] == 5 and metrics["elk_ms"] > 0


def test_scene_files_are_content_hashed(built: tuple[Path, Json]) -> None:
    import hashlib
    d, _ = built
    index = _load(d / "index.json")
    assert set(index["scenes"]) == {"landscape", "e/billing", "e/billing/api", "v/landscape", "v/billing-containers"}
    for key, entry in index["scenes"].items():
        data = (d / entry["file"]).read_bytes()
        digest = hashlib.sha256(data).hexdigest()
        assert entry["hash"] == "sha256:" + digest
        assert entry["file"] == f"scene/{key}.{digest[:8]}.json"
    model_digest = index["model"]["hash"].removeprefix("sha256:")
    assert index["model"]["file"] == f"model.{model_digest[:8]}.json"
    assert hashlib.sha256((d / index["model"]["file"]).read_bytes()).hexdigest() == model_digest
    assert (d / index["model"]["file"]).read_bytes() == (SMALL / "model.json").read_bytes()
    assert not (d / "model.json").exists()


def test_frames_scale_children_and_element_bounds(built: tuple[Path, Json]) -> None:
    d, _ = built
    sc = _scenes(d)
    for key, scene in sc.items():
        for n in scene["nodes"]:
            fr = n.get("frame")
            if not fr:
                continue
            child = sc[fr["scene"]]
            assert child["bounds"][:2] == [0, 0]
            assert abs(n["w"] - fr["scale"] * child["bounds"][2]) <= 0.5
            assert abs(n["h"] - fr["scale"] * child["bounds"][3]) <= 0.5
            assert 0 < fr["scale"] <= 1
            assert n["label"]["anchor"] == "top"
            # the frame is at least a leaf box in area
            assert n["w"] * n["h"] >= LEAF_W * LEAF_H * 0.99
            # reserved area is at most k leaf boxes
            assert n["w"] * n["h"] <= 4.0 * LEAF_W * LEAF_H * 1.01 or fr["scale"] == 1


def test_authored_views_are_a_single_plain_pass(built: tuple[Path, Json]) -> None:
    d, _ = built
    sc = _scenes(d)
    v = sc["v/billing-containers"]
    assert v["layout"]["passes"] == 1 and v["ports"] == []
    assert all("frame" not in n for n in v["nodes"])
    boundary = next(n for n in v["nodes"] if n["role"] == "boundary")
    for n in v["nodes"]:
        if n["parent"] == boundary["id"]:
            assert boundary["x"] <= n["x"] and n["x"] + n["w"] <= boundary["x"] + boundary["w"]
    assert boundary["label"]["anchor"] == "bottom-left"


def test_third_level_continuity_composes_through_two_frames(built: tuple[Path, Json]) -> None:
    """A component edge ends at a port of e/billing/api, which continues through e/billing to the landscape.

    The combination 'compound with FIXED_ORDER ports whose children are leaves with FIXED_POS ports'
    holds (no fallback needed): the end point of the component edge, mapped through the two frames,
    meets the landscape edge Billing -> CRM within the checker's 1.5 px.
    """
    d, _ = built
    sc = _scenes(d)
    land, bill, api = sc["landscape"], sc["e/billing"], sc["e/billing/api"]
    for s in sc.values():
        assert "fallback" not in s["layout"]
    pid = "billing/api->port:billing->crm"  # port of e/billing/api = edge of e/billing
    port = next(p for p in api["ports"] if p["id"] == pid)
    comp_edge = next(e for e in api["edges"] if e["target"] == {"port": pid})
    assert math.hypot(comp_edge["points"][-1][0] - port["x"], comp_edge["points"][-1][1] - port["y"]) <= 1.5
    # level e/billing: the edge that ends at the frame billing/api ...
    api_node = next(n for n in bill["nodes"] if n["id"] == "billing/api")
    s2 = api_node["frame"]["scale"]
    mid = (api_node["x"] + s2 * port["x"], api_node["y"] + s2 * port["y"])
    bill_edge = next(e for e in bill["edges"] if e["id"] == pid)
    assert bill_edge["source"] == "billing/api"
    assert math.hypot(bill_edge["points"][0][0] - mid[0], bill_edge["points"][0][1] - mid[1]) <= 1.5
    # ... continues at the port of e/billing and lands on the landscape edge
    bport = next(p for p in bill["ports"] if p["id"] == "billing->crm")
    bill_node = next(n for n in land["nodes"] if n["id"] == "billing")
    s1 = bill_node["frame"]["scale"]
    top = (bill_node["x"] + s1 * bport["x"], bill_node["y"] + s1 * bport["y"])
    land_edge = next(e for e in land["edges"] if e["id"] == "billing->crm")
    assert math.hypot(land_edge["points"][0][0] - top[0], land_edge["points"][0][1] - top[1]) <= 1.5
    assert math.hypot(bill_edge["points"][-1][0] - bport["x"], bill_edge["points"][-1][1] - bport["y"]) <= 1.5


def test_reserve_budget() -> None:
    w, h, s = reserve(240, 140, 4.0)  # a leaf-sized inner layout is not scaled
    assert (w, h, s) == (240, 140, 1.0)
    w, h, s = reserve(1200, 700, 4.0)  # 25x a leaf: area down to 4 leaves
    assert abs(w * h - 4 * LEAF_W * LEAF_H) < 0.01 * 4 * LEAF_W * LEAF_H
    assert abs(w / 1200 - s) < 1e-3 and abs(h / 700 - s) < 1e-3
    assert reserve(1200, 700, 9.0)[2] > s  # bigger k, bigger scale


def test_k_changes_frame_scale(tmp_path: Path) -> None:
    lv, md = _load(SMALL / "levels.json"), _load(SMALL / "model.json")
    layout_workspace(lv, md, str(tmp_path / "k1"), k=1.0)
    layout_workspace(lv, md, str(tmp_path / "k9"), k=9.0)
    s1 = _scenes(tmp_path / "k1")["landscape"]
    s9 = _scenes(tmp_path / "k9")["landscape"]
    sc1 = next(n for n in s1["nodes"] if n["id"] == "billing")["frame"]["scale"]
    sc9 = next(n for n in s9["nodes"] if n["id"] == "billing")["frame"]["scale"]
    assert sc1 < sc9 <= 1
    assert check_built(str(tmp_path / "k1")).errors == []
    assert check_built(str(tmp_path / "k9")).errors == []


def test_levels_and_model_must_match(tmp_path: Path) -> None:
    lv, md = _load(SMALL / "levels.json"), _load(SMALL / "model.json")
    lv["modelHash"] = "sha256:" + "0" * 64
    with pytest.raises(ValueError, match="made from"):
        layout_workspace(lv, md, str(tmp_path))


def test_cli_and_seed_independence(tmp_path: Path) -> None:
    """The command line works, and output bytes do not depend on PYTHONHASHSEED."""
    trees = []
    for seed in ("1", "2", "3"):
        d = tmp_path / f"s{seed}"
        d.mkdir()
        shutil.copy(SMALL / "levels.json", d)
        shutil.copy(SMALL / "model.json", d)
        env = {**os.environ, "PYTHONHASHSEED": seed}
        r = subprocess.run([sys.executable, "-m", "buildzr.site.layout", "--data", str(d)],
                           env=env, capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        assert json.loads(r.stdout)["scenes"] == 5
        assert check_built(str(d)).errors == []
        trees.append(d)
    def snapshot(d: Path) -> dict[str, bytes]:
        return {str(p.relative_to(d)): p.read_bytes() for p in sorted(d.rglob("*")) if p.is_file()}
    assert snapshot(trees[0]) == snapshot(trees[1]) == snapshot(trees[2])


def header_violations(scenes: dict[str, Json]) -> list[str]:
    """Child nodes whose top lies inside the frame header band (label tiers 0-1 + 8 px, parent scale)."""
    bad = []
    for key, parent in scenes.items():
        for n in parent["nodes"]:
            fr = n.get("frame")
            if not fr:
                continue
            fs = n["style"]["fontSize"]
            band = sum(ln.get("size", fs) * 1.25 for ln in n["label"]["lines"] if ln["tier"] <= 1) + 8
            for c in scenes[fr["scene"]]["nodes"]:
                if c["y"] * fr["scale"] < band - 0.5:
                    bad.append(f"{fr['scene']}:{c['id']} y={c['y']} scale={fr['scale']} band={band}")
    return bad


def test_children_clear_the_frame_header_band(built: tuple[Path, Json]) -> None:
    d, _ = built
    sc = _scenes(d)
    assert header_violations(sc) == []
    # the band is real: the top padding grew beyond the old fixed 40 px where the label needs it
    assert min(c["y"] for c in sc["e/billing"]["nodes"]) >= 40


@pytest.mark.parametrize("icon", [False, True])
def test_a_nested_boundary_is_as_wide_as_its_label_needs_and_no_higher(tmp_path: Path, icon: bool) -> None:
    """ELK applies a compound's minimum size transposed in a DOWN layout: the width a boundary asked for its label
    became height, and the label (with its icon) was wider than the box, so the viewer faded it out."""
    from buildzr.dsl import (Container, ContainerInstance, DeploymentEnvironment, DeploymentNode, DeploymentView,
                             SoftwareSystem, StyleElements, Workspace)
    from buildzr.site import fonts
    from buildzr.site.layout.passes import BOUNDARY_LABEL_X, BOUNDARY_PAD, MIN_BOUNDARY_H, NAME_FIT_INNER, boundary_min_w
    from buildzr.site.levels import build_levels
    from buildzr.site.model import export_model
    from tests.site.branded_workspace import GREEN

    with Workspace("w") as w:
        with SoftwareSystem("X") as x:
            app = Container("Web Application")
        with DeploymentEnvironment("Live") as live:
            with DeploymentNode("Autoscaling Group"):
                with DeploymentNode("Amazon EC2 - Ubuntu Server") as ec2:
                    ContainerInstance(app)
        DeploymentView(environment=live, key="d", software_system_selector=x, description="d")
        if icon:
            StyleElements(on=[ec2], icon=GREEN)
    layout_workspace(build_levels(w, export_model(w)), export_model(w), str(tmp_path))
    nodes = {n["name"]: n for n in _scenes(tmp_path)["v/d"]["nodes"]}
    b, leaf = nodes["Amazon EC2 - Ubuntu Server"], nodes["Web Application"]
    assert ("icon" in b["style"]) is icon
    need = boundary_min_w({"lines": b["label"]["lines"], "style": b["style"]})
    assert b["w"] >= need - 0.01 > leaf["w"] + BOUNDARY_PAD[1] + BOUNDARY_PAD[3]  # the label, not the child, sets it
    # the name and its icon fit the share of the box the viewer draws a name in full
    name = fonts.widest([ln for ln in b["label"]["lines"] if ln["tier"] == 0], 16)
    icon_w = fonts.icon_inline_w(16) if icon else 0
    assert name + icon_w <= NAME_FIT_INNER * b["w"] - BOUNDARY_LABEL_X + 0.01
    # no height beyond the child, the padding and the label strip
    assert b["h"] == pytest.approx(max(MIN_BOUNDARY_H, leaf["h"] + BOUNDARY_PAD[0] + BOUNDARY_PAD[2]), abs=0.01)
    outer = nodes["Autoscaling Group"]
    assert outer["x"] <= b["x"] and b["x"] + b["w"] <= outer["x"] + outer["w"]
