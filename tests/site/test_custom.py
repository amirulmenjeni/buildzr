"""Custom elements and custom views in the built workspace: model.json, the level graphs, the checker, the Model API."""

from __future__ import annotations

import copy
import filecmp
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from buildzr.dsl import Container, CustomView, Element, Person, SoftwareSystem, SystemContextView, Workspace
from buildzr.site.api import Api, Query
from buildzr.site.canonical import model_hash
from buildzr.site.check import Report, check_built, check_model
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model, workspace_json
from tests.site.custom_workspace import custom_workspace
from tests.site.small_workspace import small_workspace
from tests.site.test_cli import ROOT, needs_node

Json = dict[str, Any]

FIXTURE = Path(ROOT) / "tests" / "site" / "fixtures" / "custom"


def by_id(items: list[Json], key: str = "id") -> dict[str, Json]:
    return {i[key]: i for i in items}


def errors_of(model: Json) -> list[str]:
    rep = Report()
    check_model(model, rep)
    return rep.errors


def rehash(model: Json) -> Json:
    model["modelHash"] = model_hash(model)
    return model


@pytest.fixture(scope="module")
def workspace() -> Workspace:
    return custom_workspace()  # one instance: the model and the levels must come from the same ids


@pytest.fixture(scope="module")
def model(workspace: Workspace) -> Json:
    return export_model(workspace)


@pytest.fixture(scope="module")
def levels(workspace: Workspace, model: Json) -> dict[str, Json]:
    return by_id(build_levels(workspace, model)["levels"], "key")


# --- model.json ---------------------------------------------------------------------------------------------


def test_custom_elements_are_exported_with_their_metadata(model: Json) -> None:
    els = by_id(model["elements"])
    assert [e["id"] for e in model["elements"]] == [
        "operator", "supervisor", "mes", "mes/dashboard", "mes/collector", "erp", "plc", "sensor", "conveyor", "spare-part"]
    assert {i: (els[i]["type"], els[i].get("metadata")) for i in ("plc", "sensor", "conveyor", "spare-part")} == {
        "plc": ("Element", "Hardware"), "sensor": ("Element", "Hardware"), "conveyor": ("Element", None),
        "spare-part": ("Element", "Stock")}
    assert all(e["parent"] is None and e["children"] == [] for e in model["elements"] if e["type"] == "Element")
    assert els["plc"]["tags"] == ["Element", "Device"] and els["plc"]["description"] == "Controls the line."
    assert "metadata" not in els["conveyor"], "an element without metadata has no metadata key"
    assert not any("metadata" in e for e in model["elements"] if e["type"] != "Element")
    assert errors_of(model) == []


def test_custom_views_are_exported_after_the_other_views(model: Json) -> None:
    views = by_id(model["views"], "key")
    assert [(v["key"], v["kind"]) for v in model["views"]] == [
        ("landscape", "systemLandscape"), ("mes-containers", "container"), ("devices", "custom"), ("sensing", "custom")]
    assert views["devices"] == {"key": "devices", "viewKey": "devices", "kind": "custom", "title": "Devices",
                                "description": "Every device on the line.", "scope": None, "scene": "v/devices"}
    els = by_id(model["elements"])
    assert els["plc"]["views"] == ["landscape", "mes-containers", "devices", "sensing"]
    assert els["conveyor"]["views"] == ["landscape", "devices"]
    assert els["spare-part"]["views"] == [], "excluded from every view"
    assert els["operator"]["views"] == ["landscape", "mes-containers"]


def test_relationships_between_custom_and_c4_elements_are_exported(model: Json) -> None:
    rels = by_id(model["relationships"])
    assert {"mes/collector->plc", "plc->sensor", "plc->conveyor"} <= set(rels)
    assert rels["mes/collector->plc"]["technology"] == "OPC UA"


def test_a_workspace_without_custom_elements_is_exported_as_before() -> None:
    m = export_model(small_workspace())
    assert not any("metadata" in e for e in m["elements"])
    assert not any(v["kind"] == "custom" for v in m["views"])
    assert errors_of(m) == []


def test_a_custom_view_without_elements_is_a_view_like_any_other() -> None:
    with Workspace("Empty") as w:
        Person("P")
        CustomView(key="none", description="nothing yet")
    m = export_model(w)
    assert [(v["key"], v["kind"], v["scope"]) for v in m["views"]] == [("none", "custom", None)]
    lv = by_id(build_levels(w, m)["levels"], "key")["v/none"]
    assert lv["nodes"] == [] and lv["edges"] == []
    assert errors_of(m) == []


def test_the_checker_refuses_a_misplaced_custom_element_or_metadata(model: Json) -> None:
    def bad(edit: Any) -> list[str]:
        m = copy.deepcopy(model)
        edit(m)
        return errors_of(rehash(m))

    def meta_on_person(m: Json) -> None:
        by_id(m["elements"])["operator"]["metadata"] = "Human"

    def nested(m: Json) -> None:
        els = by_id(m["elements"])
        els["plc"]["parent"] = "mes"
        els["mes"]["children"].append("plc")

    def with_children(m: Json) -> None:
        by_id(m["elements"])["plc"]["children"] = ["plc/x"]

    assert any("metadata is only for custom elements" in e for e in bad(meta_on_person))
    assert any("a custom element is a root with no children" in e for e in bad(nested))
    assert any("a custom element is a root with no children" in e for e in bad(with_children))
    assert any("metadata" in e for e in bad(lambda m: by_id(m["elements"])["plc"].update(metadata="")))  # schema: minLength 1


# --- level graphs -------------------------------------------------------------------------------------------


def test_the_custom_view_level_draws_custom_elements_with_structurizr_labels(levels: dict[str, Json]) -> None:
    lv = levels["v/devices"]
    assert lv["level"] == {"kind": "view", "scope": "devices"} and lv["title"] == "Devices"
    nodes = by_id(lv["nodes"])
    assert sorted(nodes) == ["conveyor", "plc", "sensor"]
    assert [ln["text"] for ln in nodes["plc"]["lines"]] == ["PLC", "[Hardware]", "Controls the line."]
    assert [ln["text"] for ln in nodes["conveyor"]["lines"]] == ["Conveyor", "Moves the parts."], "no [Element] text"
    assert all(n["role"] == "element" and n["parent"] is None and n["type"] == "Element" for n in nodes.values())
    assert sorted(e["id"] for e in lv["edges"]) == ["plc->conveyor", "plc->sensor"]


def test_custom_elements_get_the_structurizr_default_style_and_their_own_styles(levels: dict[str, Json]) -> None:
    nodes = by_id(levels["v/devices"]["nodes"])
    assert nodes["conveyor"]["shape"] == "Box"
    assert (nodes["conveyor"]["style"]["fill"], nodes["conveyor"]["style"]["color"]) == ("#dddddd", "#000000")
    assert nodes["plc"]["shape"] == "Hexagon"
    assert (nodes["plc"]["style"]["fill"], nodes["plc"]["style"]["color"]) == ("#1f6f5c", "#ffffff")


def test_standard_views_draw_the_custom_elements_they_list_beside_the_c4_ones(levels: dict[str, Json]) -> None:
    assert sorted(n["id"] for n in levels["v/landscape"]["nodes"]) == [
        "conveyor", "erp", "mes", "operator", "plc", "sensor", "supervisor"], "everything but the spare part"
    cont = by_id(levels["v/mes-containers"]["nodes"])
    assert sorted(cont) == ["erp", "mes", "mes/collector", "mes/dashboard", "operator", "plc", "supervisor"]
    assert cont["mes"]["role"] == "boundary" and cont["plc"]["parent"] is None, "the custom element sits outside the boundary"
    assert "mes/collector->plc" in {r for e in levels["v/mes-containers"]["edges"] for r in e["rels"]}


def test_the_model_canvas_levels_stay_the_c4_hierarchy(levels: dict[str, Json]) -> None:
    assert sorted(n["id"] for n in levels["landscape"]["nodes"]) == ["erp", "mes", "operator", "supervisor"]
    assert sorted(n["id"] for n in levels["e/mes"]["nodes"]) == ["mes/collector", "mes/dashboard"]
    assert sorted(levels) == ["e/mes", "landscape", "v/devices", "v/landscape", "v/mes-containers", "v/sensing"]
    for key in ("landscape", "e/mes"):
        assert all(n["type"] != "Element" for n in levels[key]["nodes"])
        assert not any(r.startswith(("plc", "sensor", "conveyor")) or "->plc" in r for e in levels[key]["edges"] for r in e["rels"])


def test_levels_of_a_workspace_without_custom_elements_do_not_change() -> None:
    w = small_workspace()
    lv = build_levels(w, export_model(w))
    assert all(n["type"] != "Element" for level in lv["levels"] for n in level["nodes"])


def test_a_custom_element_in_a_system_context_view_is_drawn_there() -> None:
    with Workspace("Ctx") as w:
        user = Person("User")
        with SoftwareSystem("App") as app:
            Container("Web")
        box = Element("Gateway", metadata="Hardware")
        user >> "Uses" >> app
        app >> "Talks to" >> box
        SystemContextView(software_system_selector=app, key="ctx", description="", include_elements=[box])
    m = export_model(w)
    lv = by_id(build_levels(w, m)["levels"], "key")["v/ctx"]
    assert sorted(n["id"] for n in lv["nodes"]) == ["app", "gateway", "user"]
    assert sorted(e["id"] for e in lv["edges"]) == ["app->gateway", "user->app"]
    assert errors_of(m) == []


# --- the built workspace -----------------------------------------------------------------------------------


def test_the_committed_fixture_passes_the_checker() -> None:
    rep = check_built(str(FIXTURE))
    assert rep.errors == []
    index = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    assert sorted(index["scenes"]) == ["e/mes", "landscape", "v/devices", "v/landscape", "v/mes-containers", "v/sensing"]


def test_the_checker_refuses_a_scene_that_draws_a_deployment_element_in_a_custom_view(tmp_path: Path) -> None:
    import shutil
    d = tmp_path / "data"
    shutil.copytree(FIXTURE, d)
    index = json.loads((d / "index.json").read_text(encoding="utf-8"))
    f = d / index["scenes"]["v/devices"]["file"]
    scene = json.loads(f.read_text(encoding="utf-8"))
    scene["nodes"][0]["type"] = "DeploymentNode"
    f.write_text(json.dumps(scene), encoding="utf-8")
    assert any("a DeploymentNode in the custom view devices" in e for e in check_built(str(d)).errors)


@needs_node
def test_the_fixture_is_what_the_real_build_makes(tmp_path: Path) -> None:
    """``tests/site/fixtures/make_custom.py`` rebuilds the fixture with the real layout; it must give the same files."""
    out = tmp_path / "custom"
    env = dict(os.environ, PYTHONPATH=ROOT)
    subprocess.run([sys.executable, os.path.join(ROOT, "tests", "site", "fixtures", "make_custom.py"), str(out)],
                   check=True, env=env, cwd=str(tmp_path), capture_output=True)

    def same(a: Path, b: Path) -> bool:
        cmp = filecmp.dircmp(a, b)
        return (not cmp.left_only and not cmp.right_only and not cmp.diff_files
                and all(same(a / s, b / s) for s in cmp.common_dirs))

    assert same(out, FIXTURE), "run: uv run python tests/site/fixtures/make_custom.py"
    assert workspace_json(custom_workspace())["model"]["customElements"], "the workspace has custom elements"


# --- the Model API -----------------------------------------------------------------------------------------


def test_the_model_api_links_a_custom_element_to_the_first_view_that_draws_it(model: Json) -> None:
    api = Api(model, viewer=True)
    assert api.viewer_url("plc") == "/#/v/landscape?sel=plc"
    assert api.viewer_url("spare-part") is None, "in no view: nothing to link to"
    assert api.viewer_url("mes/collector") == "/#/m/mes?sel=mes/collector", "C4 links are as before"
    el = api.element(Query("element", "id=plc"))["element"]
    assert el["type"] == "Element" and el["metadata"] == "Hardware" and el["views"] == [
        "landscape", "mes-containers", "devices", "sensing"]
    assert "metadata" not in api.element(Query("element", "id=conveyor"))["element"]
    assert "metadata" not in api.element(Query("element", "id=mes"))["element"]
    views = {v["key"]: v for v in api.views_answer(Query("views", ""))["items"]}
    assert views["devices"]["kind"] == "custom" and views["devices"]["viewerUrl"] == "/#/v/devices"
    one = api.view(Query("view", "key=sensing"))["view"]
    assert [e["id"] for e in one["elements"]] == ["plc", "sensor"]
