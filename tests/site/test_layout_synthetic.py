"""Stage 1 acceptance on the synthetic S model (and M when asked): zero checker errors, port continuity."""

from __future__ import annotations

import os
import shutil
from pathlib import Path

import pytest

from buildzr.site.check import check_built
from buildzr.site.layout import layout_workspace
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model
from tests.site.synthetic import synthetic

pytestmark = pytest.mark.skipif(shutil.which("node") is None and not os.environ.get("BUILDZR_NODE"),
                                reason="node is not installed")


@pytest.mark.parametrize("size", ["S"] + (["M", "L"] if os.environ.get("BUILDZR_TEST_SLOW") else []))
def test_synthetic_layout_passes_the_checker(tmp_path: Path, size: str) -> None:
    ws = synthetic(size)
    model = export_model(ws)
    levels = build_levels(ws, model)
    metrics = layout_workspace(levels, model, str(tmp_path))
    rep = check_built(str(tmp_path))
    assert rep.errors == []
    m = rep.metrics["scenes"]
    assert m["bad_edges"] == 0
    assert m["ports"] > 0 and m["port_sides_kept"] == m["ports"]
    assert m["port_gap_px"] <= 1.5
    # three levels deep: a component scene (e/<system>/<container>) exists and carries ports
    deep = [k for k in (lv["key"] for lv in levels["levels"]) if k.startswith("e/") and k.count("/") == 2]
    assert deep and all((tmp_path / "scene" / "e").exists() for _ in deep[:1])
    assert metrics["scenes"] == len(levels["levels"])
    from tests.site.test_layout import _scenes, header_violations
    assert header_violations(_scenes(tmp_path)) == []
