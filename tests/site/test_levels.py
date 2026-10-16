"""Stage 0: level graphs (buildzr.levels/2)."""

from __future__ import annotations

import json
import os
import shutil
from typing import Any

import jsonschema  # type: ignore[import-untyped]
import pytest

from buildzr.site.canonical import dumps
from buildzr.site.export import load_workspaces
from buildzr.site.levels import build_levels
from buildzr.site.model import ModelIndex, export_model, rollup
from tests.site.small_workspace import small_workspace
from tests.site.synthetic import synthetic
from tests.site.test_model import ROOT, dsl_files, workspaces_of

Json = dict[str, Any]

with open(os.path.join(ROOT, "buildzr/site/schema/levels.schema.json"), encoding="utf-8") as _f:
    SCHEMA = json.load(_f)


def check_levels(model: Json, levels: Json) -> list[str]:
    """Everything the schema cannot say about a level graph; returns the problems found."""
    errs = [f"schema {list(e.absolute_path)}: {e.message}"
            for e in jsonschema.Draft202012Validator(SCHEMA).iter_errors(levels)]
    mi = ModelIndex(model)
    by_key = {lv["key"]: lv for lv in levels["levels"]}
    keys = [lv["key"] for lv in levels["levels"]]
    want = ["landscape"] + [f"e/{e['id']}" for e in model["elements"] if e["children"]] \
        + [v["scene"] for v in model["views"]]
    if keys != want:
        errs.append(f"level keys {keys} != {want}")
    if levels["modelHash"] != model["modelHash"]:
        errs.append("modelHash differs")
    for lv in levels["levels"]:
        k = lv["key"]
        ids = [n["id"] for n in lv["nodes"]]
        if len(set(ids)) != len(ids):
            errs.append(f"{k}: duplicate node ids")
        eids = [e["id"] for e in lv["edges"]]
        if eids != sorted(eids) or len(set(eids)) != len(eids):
            errs.append(f"{k}: edges not sorted/unique")
        if [p["id"] for p in lv["ports"]] != sorted(p["id"] for p in lv["ports"]):
            errs.append(f"{k}: ports not sorted")
        seen: set[str] = set()
        sib: dict[Any, str] = {}
        for n in lv["nodes"]:
            if n["parent"] is not None and n["parent"] not in seen:
                errs.append(f"{k}: node {n['id']} before its parent")
            if sib.get(n["parent"], "") > n["id"]:
                errs.append(f"{k}: siblings not sorted at {n['id']}")
            sib[n["parent"]] = n["id"]
            seen.add(n["id"])
            if n["id"] not in mi.el and not (n["type"] == "Group" and n["id"].startswith("group:")):
                errs.append(f"{k}: node {n['id']} not an element")
        for e in lv["edges"]:
            if e["rels"] != sorted(set(e["rels"])):
                errs.append(f"{k}: edge {e['id']} rels not sorted/unique")
            for r in e["rels"]:
                if r not in mi.rel:
                    errs.append(f"{k}: edge {e['id']} rel {r} not in model")
            for end in (e["source"], e["target"]):
                if isinstance(end, str):
                    if end not in ids:
                        errs.append(f"{k}: edge {e['id']} end {end} not a node")
                elif end["port"] not in {p["id"] for p in lv["ports"]}:
                    errs.append(f"{k}: edge {e['id']} port {end['port']} unknown")
        if lv["level"]["kind"] == "view":
            continue
        # rollup golden: every ordered pair of distinct nodes
        nodes = [n["id"] for n in lv["nodes"] if n["type"] != "Group"]
        drawn = {(e["source"], e["target"]): e["rels"] for e in lv["edges"]
                 if isinstance(e["source"], str) and isinstance(e["target"], str)}
        for a in nodes:
            for b in nodes:
                if a == b:
                    continue
                expect = rollup(model, a, b)
                if drawn.get((a, b), []) != expect:
                    errs.append(f"{k}: {a}->{b} rels {drawn.get((a, b), [])} != rollup {expect}")
        # child nodes
        scope = lv["level"]["scope"]
        expect_nodes = set(mi.el[scope]["children"]) if scope else {
            r for r in mi.roots if mi.el[r]["type"] in ("Person", "SoftwareSystem")}
        if set(nodes) != expect_nodes:
            errs.append(f"{k}: nodes {sorted(set(nodes) ^ expect_nodes)} differ from the model level")
        for n in (n for n in lv["nodes"] if n["type"] != "Group"):
            kids = mi.el[n["id"]]["children"]
            if bool(kids) != ("children" in n) or (kids and n["children"] != len(kids)):
                errs.append(f"{k}: node {n['id']} children count")
        # ports and their continuation
        if scope is not None:
            parent = mi.el[scope]["parent"]
            pl = by_key[f"e/{parent}" if parent else "landscape"]
            incident = {e["id"]: e for e in pl["edges"] if scope in (e["source"], e["target"])}
            if {p["id"] for p in lv["ports"]} != set(incident):
                errs.append(f"{k}: ports differ from the parent edges at {scope}")
            for p in lv["ports"]:
                pe = incident[p["id"]]
                inward = pe["target"] == scope
                if p["dir"] != ("in" if inward else "out"):
                    errs.append(f"{k}: port {p['id']} direction")
                inner: list[str] = []
                for e in lv["edges"]:
                    if {"port": p["id"]} in (e["source"], e["target"]):
                        if e["source" if inward else "target"] != {"port": p["id"]}:
                            errs.append(f"{k}: edge {e['id']} against port direction")
                        inner += e["rels"]
                if len(inner) != len(set(inner)):
                    errs.append(f"{k}: port {p['id']} rel continues twice")
                want_rels = [r for r in pe["rels"]
                             if mi.rel[r]["destination" if inward else "source"] != scope]
                if sorted(inner) != sorted(want_rels):
                    errs.append(f"{k}: port {p['id']} continues {sorted(inner)} != {sorted(want_rels)}")
    return errs


@pytest.mark.parametrize("size", ["S", "M", "L"])
def test_synthetic_levels(size: str) -> None:
    ws = synthetic(size)
    model = export_model(ws)
    levels = build_levels(ws, model)
    assert check_levels(model, levels) == []
    assert levels["levels"][0]["key"] == "landscape"
    assert sum(1 for lv in levels["levels"] if lv["level"]["kind"] == "view") == 3
    assert any(lv["ports"] for lv in levels["levels"])


def test_small_workspace_matches_fixture_levels() -> None:
    """Nodes, edges, ports and rels equal the hand-made fixture; styles and label lines may differ."""
    ws = small_workspace()
    model = export_model(ws)
    mine = build_levels(ws, model)
    assert check_levels(model, mine) == []
    with open(os.path.join(ROOT, "tests/site/fixtures/small/levels.json"), encoding="utf-8") as f:
        fixture = json.load(f)

    def topo(doc: Json) -> Any:
        return [(lv["key"], lv["level"], lv["ports"],
                 [(n["id"], n["role"], n["parent"], n["type"], n.get("children"), n.get("childType"),
                   n["shape"], n["tags"]) for n in lv["nodes"]],
                 [(e["id"], e["source"], e["target"], e["rels"], e.get("order")) for e in lv["edges"]])
                for lv in doc["levels"]]

    assert topo(mine) == topo(fixture)
    # Differences that are expected: the fixture has no edge label lines, and the
    # DSL version names containers 'Web', 'API', 'DB' so that their slugs match the fixture ids.
    m_styles = [(n["id"], n["style"]) for lv in mine["levels"] for n in lv["nodes"]]
    f_styles = [(n["id"], n["style"]) for lv in fixture["levels"] for n in lv["nodes"]]
    assert m_styles == f_styles


def test_text_color_switch() -> None:
    ws = small_workspace()
    model = export_model(ws)
    wcag = build_levels(ws, model)["levels"][1]
    c4 = build_levels(ws, model, text_color="c4")["levels"][1]
    web = lambda lv: next(n for n in lv["nodes"] if n["id"] == "billing/web")["style"]["color"]  # noqa: E731
    assert web(wcag) == "#000000" and web(c4) == "#ffffff"
    with pytest.raises(ValueError):
        build_levels(ws, model, text_color="red")


def test_label_lines() -> None:
    ws = small_workspace()
    model = export_model(ws)
    levels = {lv["key"]: lv for lv in build_levels(ws, model)["levels"]}
    land = levels["landscape"]
    cust = next(e for e in land["edges"] if e["id"] == "customer->billing")
    assert cust["lines"] == [{"text": "2 relationships", "tier": 0, "size": 12}]
    one = next(e for e in land["edges"] if e["id"] == "support-agent->crm")
    assert [l["text"] for l in one["lines"]] == ["Uses", "[HTTPS]"]
    billing = next(n for n in land["nodes"] if n["id"] == "billing")
    assert billing["lines"] == [{"text": "Billing", "tier": 0, "weight": "bold"},
                                {"text": "[Software System]", "tier": 1, "size": 12},
                                {"text": "Invoices customers and takes payments.", "tier": 2, "size": 12}]


def test_dsl_files_levels(tmp_path: Any) -> None:
    shutil.copytree(os.path.join(ROOT, "examples"), str(tmp_path / "examples_copy"))
    built = 0
    for rel in dsl_files():
        scratch = tmp_path / rel.replace(os.sep, "_")
        scratch.mkdir()
        src = str(tmp_path / "examples_copy" / os.path.basename(rel)) if rel.startswith("examples") else rel
        for ws in workspaces_of(src, str(scratch)):
            model = export_model(ws)
            levels = build_levels(ws, model)
            assert check_levels(model, levels) == [], rel
            assert dumps(levels).encode() == dumps(json.loads(dumps(levels))).encode()
            built += 1
    assert built >= 10


def test_groups_become_boundaries() -> None:
    from buildzr.dsl import Container, Group, SoftwareSystem, SystemLandscapeView, Workspace
    with Workspace("g", scope=None, group_separator="/") as w:
        with Group("Company"):
            with Group("Dept"):
                a = SoftwareSystem("A")
            b = SoftwareSystem("B")
        with SoftwareSystem("C"):
            with Group("Stores"):
                d = Container("D")
            e = Container("E")
        a >> "Uses" >> b
        d >> "Reads" >> e
        SystemLandscapeView(key="land", description="")
    model = export_model(w)
    levels = {lv["key"]: lv for lv in build_levels(w, model)["levels"]}
    assert check_levels(model, build_levels(w, model)) == []
    land = [(n["id"], n["role"], n["parent"]) for n in levels["landscape"]["nodes"]]
    assert land == [("c", "element", None), ("group:company", "boundary", None),
                    ("b", "element", "group:company"), ("group:company/dept", "boundary", "group:company"),
                    ("a", "element", "group:company/dept")]
    inner = [(n["id"], n["parent"]) for n in levels["e/c"]["nodes"]]
    assert inner == [("c/e", None), ("group:stores", None), ("c/d", "group:stores")]


def test_dynamic_view_steps() -> None:
    from buildzr.dsl import Container, DynamicView, Person, SoftwareSystem, Workspace
    with Workspace("d", scope=None) as w:
        u = Person("U")
        with SoftwareSystem("S") as s:
            web = Container("Web")
            db = Container("Db")
        u >> "Uses" >> web
        web >> "Reads" >> db
        DynamicView(key="dyn", description="Flow", scope=s, steps=[
            u >> "Asks" >> web,
            web >> "Queries" >> db,
        ])
    model = export_model(w)
    levels = build_levels(w, model)
    assert check_levels(model, levels) == []
    dyn = next(lv for lv in levels["levels"] if lv["key"] == "v/dyn")
    assert [(e["id"], e["order"]) for e in dyn["edges"]] == [("s/web->s/db#2", "2"), ("u->s/web#1", "1")]
    assert dyn["edges"][1]["lines"][0]["text"] == "1: Asks"
