"""ELK runner, the vendored bundle, and the ELK port behaviour the reserved-frame layout relies on."""

from __future__ import annotations

import hashlib
import os
import shutil
from typing import Any

import pytest

from buildzr.site.layout import elk
from buildzr.site.layout.elk import ElkError, ElkRunner
from buildzr.site.layout.passes import OPTS

needs_node = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")

Json = dict[str, Any]


def test_vendored_bundle_is_the_pinned_one() -> None:
    with open(elk.VENDORED_ELK, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == elk.ELK_SHA256
    assert elk.elk_bundle_path() == elk.VENDORED_ELK
    vendor = os.path.dirname(elk.VENDORED_ELK)
    for name in ("LICENSE-EPL-2.0.md", "NOTICE", "THIRD_PARTY_LICENSES.md"):
        assert os.path.getsize(os.path.join(vendor, name)) > 100
    notice = open(os.path.join(vendor, "NOTICE"), encoding="utf-8").read()
    assert "github.com/eclipse/elk" in notice and "github.com/kieler/elkjs" in notice


def test_tampered_bundle_is_refused(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    bad = tmp_path / "elk.bundled.js"
    bad.write_bytes(b"// not elk\n")
    monkeypatch.setattr(elk, "VENDORED_ELK", str(bad))
    with pytest.raises(ElkError, match="sha256"):
        elk.elk_bundle_path()


def test_missing_node_is_a_clear_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("BUILDZR_NODE", "/nonexistent/node")
    with pytest.raises(ElkError, match="Node.js was not found"):
        elk.find_node()
    monkeypatch.delenv("BUILDZR_NODE")
    monkeypatch.setenv("PATH", "")
    with pytest.raises(ElkError, match="Node.js was not found"):
        elk.find_node()


@pytest.mark.skipif(not os.environ.get("BUILDZR_TEST_DOWNLOAD"), reason="set BUILDZR_TEST_DOWNLOAD=1 (needs network)")
def test_download_switch_fetches_and_verifies(tmp_path: Any, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("BUILDZR_ELK", "download")
    path = elk.elk_bundle_path()
    assert path.startswith(str(tmp_path))
    with open(path, "rb") as f:
        assert hashlib.sha256(f.read()).hexdigest() == elk.ELK_SHA256


def _port(pid: str, side: str, x: float | None = None, y: float | None = None) -> Json:
    p: Json = {"id": pid, "width": 0, "height": 0, "layoutOptions": {"elk.port.side": side}}
    if x is not None:
        p["x"], p["y"] = x, y
    return p


def _opts() -> Json:
    return {**OPTS, "elk.padding": "[top=0,left=0,bottom=0,right=0]"}


def _by_id(g: Json) -> dict[str, Json]:
    out: dict[str, Json] = {}

    def walk(n: Json) -> None:
        for c in n.get("children", []):
            out[c["id"]] = c
            walk(c)
    walk(g)
    return out


@needs_node
def test_runner_returns_layouts_and_times() -> None:
    g = {"id": "root", "layoutOptions": _opts(),
         "children": [{"id": "a", "width": 10, "height": 10}, {"id": "b", "width": 10, "height": 10}],
         "edges": [{"id": "e", "sources": ["a"], "targets": ["b"]}]}
    with ElkRunner() as r:
        out = r.layout({"x": g, "y": g})
        assert set(out) == {"x", "y"}
        assert out["x"]["edges"][0]["sections"]
        assert r.total_ms > 0 and r.calls == 2
        with pytest.raises(ElkError):
            r.layout({"bad": {"id": "root", "children": [{"id": "n", "width": 1, "height": 1}],
                              "edges": [{"id": "e", "sources": ["missing"], "targets": ["n"]}]}})


@needs_node
def test_fixed_pos_honoured_on_leaf_ignored_on_compound() -> None:
    """Pin: FIXED_POS ports are honoured on a leaf (<= 1 px) and ignored on a compound node."""
    want_leaf_x, want_comp_x = 40.3, 250.0
    leaf = {"id": "leaf", "width": 150, "height": 140, "layoutOptions": {"elk.portConstraints": "FIXED_POS"},
            "ports": [_port("leaf|p", "NORTH", want_leaf_x, 0), _port("leaf|q", "SOUTH", 120.7, 140)]}
    g = {"id": "root", "layoutOptions": _opts(), "children": [leaf, {"id": "other", "width": 240, "height": 140}],
         "edges": [{"id": "e1", "sources": ["leaf|q"], "targets": ["other"]}]}
    comp = {"id": "comp", "layoutOptions": {"elk.padding": "[top=40,left=20,bottom=20,right=20]",
                                            "elk.portConstraints": "FIXED_POS"},
            "ports": [_port("comp:p", "NORTH", want_comp_x, 0)],
            "children": [{"id": "c1", "width": 100, "height": 60}, {"id": "c2", "width": 100, "height": 60}]}
    g2 = {"id": "root", "layoutOptions": _opts(), "children": [comp],
          "edges": [{"id": "e2", "sources": ["comp:p"], "targets": ["c1"]}, {"id": "e3", "sources": ["c1"], "targets": ["c2"]}]}
    with ElkRunner() as r:
        res = r.layout({"leaf": g, "comp": g2})
    nodes = _by_id(res["leaf"])
    lf = nodes["leaf"]
    px = next(p for p in lf["ports"] if p["id"] == "leaf|p")
    assert abs((px["x"] - lf["x"]) - want_leaf_x) <= 1.0
    assert abs((px["y"] - lf["y"]) - 0) <= 1.0
    cp = _by_id(res["comp"])["comp"]
    got = next(p for p in cp["ports"] if p["id"] == "comp:p")
    assert abs((got["x"] - cp["x"]) - want_comp_x) > 1.0, "FIXED_POS on a compound node is expected to be ignored"


@needs_node
def test_fixed_order_with_side_honoured_on_compound() -> None:
    """Pin: FIXED_ORDER + port.side on a compound put every port on its requested border.

    The order of the ports within one side is NOT pinned: elkjs 0.12.0 ignores ``elk.port.index`` and
    does not always follow the order of the ``ports`` array on a compound, so the layout relies on the
    side only (measured).
    """
    ports = [_port("n0", "NORTH"), _port("n1", "NORTH"), _port("e0", "EAST"), _port("e1", "EAST"),
             _port("s0", "SOUTH"), _port("s1", "SOUTH"), _port("w0", "WEST"), _port("w1", "WEST")]
    comp = {"id": "X", "layoutOptions": {"elk.padding": "[top=40,left=20,bottom=20,right=20]",
                                         "elk.portConstraints": "FIXED_ORDER"},
            "ports": ports,
            "children": [{"id": c, "width": 100, "height": 60} for c in "abcd"]}
    edges = [{"id": "e1", "sources": ["n0"], "targets": ["b"]}, {"id": "e2", "sources": ["n1"], "targets": ["a"]},
             {"id": "e3", "sources": ["c"], "targets": ["e0"]}, {"id": "e4", "sources": ["d"], "targets": ["e1"]},
             {"id": "e5", "sources": ["a"], "targets": ["s0"]}, {"id": "e6", "sources": ["b"], "targets": ["s1"]},
             {"id": "e7", "sources": ["w0"], "targets": ["d"]}, {"id": "e8", "sources": ["w1"], "targets": ["c"]}]
    g = {"id": "root", "layoutOptions": _opts(), "children": [comp], "edges": edges}
    with ElkRunner() as r:
        res = r.layout({"g": g})["g"]
    x = _by_id(res)["X"]
    pos = {p["id"]: (p["x"] - x["x"], p["y"] - x["y"]) for p in x["ports"]}
    w, h = x["width"], x["height"]
    for pid in ("n0", "n1"):
        assert abs(pos[pid][1]) <= 1
    for pid in ("e0", "e1"):
        assert abs(pos[pid][0] - w) <= 1
    for pid in ("s0", "s1"):
        assert abs(pos[pid][1] - h) <= 1
    for pid in ("w0", "w1"):
        assert abs(pos[pid][0]) <= 1
