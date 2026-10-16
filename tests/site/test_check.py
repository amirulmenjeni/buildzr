"""The checker accepts the hand-made fixture and rejects corrupted copies of it."""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any, Callable

import pytest

from buildzr.site.canonical import dumps, model_hash
from buildzr.site.check import check_site

SMALL = Path(__file__).parent / "fixtures" / "small"


def _mutated(tmp_path: Path, rel: str, fn: Callable[[Any], None]) -> Path:
    """Copy the fixture, apply fn to one JSON file, and re-hash it in index.json."""
    import hashlib

    d = tmp_path / "site"
    shutil.copytree(SMALL, d)
    p = d / rel
    obj = json.loads(p.read_text(encoding="utf-8"))
    fn(obj)
    text = dumps(obj)
    p.write_text(text, encoding="utf-8")
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    entries = [idx["model"], *idx["scenes"].values()]
    for e in entries:
        if e["file"] == rel:
            e["hash"] = "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")
    return d


def test_fixture_passes() -> None:
    rep = check_site(str(SMALL))
    assert rep.errors == []
    s = rep.metrics["scenes"]
    assert s["scenes"] == 5 and s["frames"] == 2 and s["ports"] == 9
    assert s["bad_edges"] == 0 and s["port_gap_px"] <= 1.5


def _edge(scene: Any, eid: str) -> Any:
    return next(e for e in scene["edges"] if e["id"] == eid)


def _set_port_x(s: Any) -> None:
    next(p for p in s["ports"] if p["id"] == "billing->crm")["x"] = 300


def _drop_port(s: Any) -> None:
    s["ports"] = [p for p in s["ports"] if p["id"] != "crm->billing"]
    s["edges"] = [e for e in s["edges"] if e["source"] != {"port": "crm->billing"}]


def _wrong_rels(s: Any) -> None:
    e = _edge(s, "billing->crm")
    e["rels"] = ["support-agent->crm"]


def _through_box(s: Any) -> None:
    # route crm->billing over the top, straight through the customer box
    _edge(s, "crm->billing")["points"] = [[545, 890], [800, 890], [800, 130], [600, 130], [600, 240],
                                          [720, 240], [720, 385]]


def _missing_edge(s: Any) -> None:
    s["edges"] = [e for e in s["edges"] if e["id"] != "support-agent->crm"]


def _bad_scale(s: Any) -> None:
    next(n for n in s["nodes"] if n["id"] == "billing")["frame"]["scale"] = 0.4


def _model_hash(m: Any) -> None:
    m["workspace"]["name"] = "changed"


def _model_parent(m: Any) -> None:
    m["elements"][3]["parent"] = "crm"
    m["modelHash"] = model_hash(m)


@pytest.mark.parametrize("rel,fn,needle", [
    ("scene/e/billing.json", _set_port_x, "gap"),
    ("scene/e/billing.json", _drop_port, "child ports"),
    ("scene/landscape.json", _wrong_rels, "rollup"),
    ("scene/landscape.json", _through_box, "unrelated node customer"),
    ("scene/landscape.json", _missing_edge, "missing rolled-up edge support-agent->crm"),
    ("scene/landscape.json", _bad_scale, "scale"),
    ("model.json", _model_hash, "modelHash"),
    ("model.json", _model_parent, "parent"),
])
def test_corruption_is_caught(tmp_path: Path, rel: str, fn: Callable[[Any], None], needle: str) -> None:
    rep = check_site(str(_mutated(tmp_path, rel, fn)))
    assert any(needle in e for e in rep.errors), rep.errors


def test_noncanonical_bytes(tmp_path: Path) -> None:
    d = tmp_path / "site"
    shutil.copytree(SMALL, d)
    p = d / "scene" / "landscape.json"
    p.write_text(json.dumps(json.loads(p.read_text(encoding="utf-8")), indent=1), encoding="utf-8")
    rep = check_site(str(d))
    assert any("canonical" in e for e in rep.errors)
    assert any("hash" in e for e in rep.errors)


def test_fixture_is_reproducible(tmp_path: Path) -> None:
    """make_small.py regenerates the committed fixture byte for byte."""
    import subprocess
    import sys

    root = Path(__file__).parents[2]
    before = {p.relative_to(SMALL): p.read_bytes() for p in SMALL.rglob("*.json")}
    subprocess.run([sys.executable, str(SMALL.parent / "make_small.py")], check=True, cwd=root)
    after = {p.relative_to(SMALL): p.read_bytes() for p in SMALL.rglob("*.json")}
    assert before == after
    assert os.path.isdir(SMALL)


def test_levels_fixture_matches_schema() -> None:
    import jsonschema  # type: ignore[import-untyped]

    root = Path(__file__).parents[2] / "buildzr" / "site" / "schema" / "levels.schema.json"
    schema = json.loads(root.read_text(encoding="utf-8"))
    levels = json.loads((SMALL / "levels.json").read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(levels)
    assert [lv["key"] for lv in levels["levels"]] == [
        "landscape", "e/billing", "e/billing/api", "v/landscape", "v/billing-containers"]
