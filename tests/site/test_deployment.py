"""Deployment environments, nodes, instances and deployment views in the built workspace and the Model API."""

from __future__ import annotations

import copy
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from buildzr.dsl import (
    Container, ContainerInstance, ContainerView, DeploymentEnvironment, DeploymentNode, DeploymentView,
    InfrastructureNode, Person, SoftwareSystem, SoftwareSystemInstance, StyleElements, Workspace,
)
from buildzr.site.api import Api
from buildzr.site.canonical import dumps, model_hash
from buildzr.site.check import Report, check_built, check_model
from buildzr.site.levels import build_levels
from buildzr.site.model import BrokenDeployment, export_model, workspace_json
from tests.site.test_cli import ROOT, make_static, needs_node

Json = dict[str, Any]

SHOP = '''
from buildzr.dsl import (
    Workspace, Person, SoftwareSystem, Container,
    DeploymentEnvironment, DeploymentNode, InfrastructureNode, ContainerInstance,
    ContainerView, DeploymentView, StyleElements,
)

with Workspace('Shop Deployment') as w:
    customer = Person('Customer')
    with SoftwareSystem('Shop') as shop:
        api = Container('API', technology='Python, FastAPI', description='Takes orders')
        db = Container('Database', technology='PostgreSQL', tags={'Database'})
    customer >> ("Buys from", "HTTPS") >> api
    api >> ("Reads from and writes to", "SQL") >> db

    with DeploymentEnvironment('Production') as production:
        with DeploymentNode('AWS', technology='Amazon Web Services'):
            with DeploymentNode('eu-west-1', technology='AWS region'):
                lb = InfrastructureNode('Load Balancer', technology='Elastic Load Balancer')
                with DeploymentNode('ECS Cluster', technology='Amazon ECS', instances='2'):
                    api_instance = ContainerInstance(api)
                with DeploymentNode('RDS', technology='Amazon RDS'):
                    ContainerInstance(db)
                lb >> ("Forwards requests to", "HTTPS") >> api_instance

    ContainerView(software_system_selector=shop, key='shop-containers', description='The containers of the shop')
    DeploymentView(environment=production, key='production', software_system_selector=shop,
                   description='The shop in production')
    StyleElements(on=['Database'], shape='Cylinder')
'''

P = "deploy/production/aws/eu-west-1"


def shop() -> Workspace:
    ns: Json = {}
    exec(compile(SHOP, "shop.py", "exec"), ns)
    w: Workspace = ns["w"]
    return w


def errors_of(model: Json) -> list[str]:
    rep = Report()
    check_model(model, rep)
    return rep.errors


def rehash(model: Json) -> Json:
    model["modelHash"] = model_hash(model)
    return model


# --- model.json -------------------------------------------------------------------------------------------


def test_shop_model_has_the_environment_its_elements_and_the_view() -> None:
    model = export_model(shop())
    assert errors_of(model) == []
    assert model["deployment"]["environments"] == [{"key": "production", "name": "Production", "id": "deploy/production",
                                                    "nodes": ["deploy/production/aws"], "views": ["production"]}]
    el = {e["id"]: e for e in model["elements"]}
    deployed = [e["id"] for e in model["elements"] if e["id"].startswith("deploy/")]
    assert deployed == ["deploy/production/aws", P, f"{P}/ecs-cluster", f"{P}/ecs-cluster/api", f"{P}/rds",
                        f"{P}/rds/database", f"{P}/load-balancer"]
    api = el[f"{P}/ecs-cluster/api"]
    assert api["type"] == "ContainerInstance" and api["instanceOf"] == "shop/api" and api["parent"] == f"{P}/ecs-cluster"
    assert (api["name"], api["technology"], api["description"]) == ("API", "Python, FastAPI", "Takes orders")
    assert api["environment"] == "production" and api["views"] == ["production"] and "instances" not in api
    assert el[f"{P}/ecs-cluster"]["instances"] == "2" and el[P]["instances"] == "1"
    assert el["deploy/production/aws"]["parent"] is None
    assert el[f"{P}/load-balancer"]["type"] == "InfrastructureNode"
    assert el["shop/api"]["views"] == ["shop-containers"]  # the container is not in the deployment view, its instance is
    view = next(v for v in model["views"] if v["key"] == "production")
    assert view["kind"] == "deployment" and view["environment"] == "production" and view["scope"] == "shop"
    # explicit relationships only: the copied instance relationship is not one, the load balancer's is
    assert [r["id"] for r in model["relationships"]] == [
        "customer->shop/api", f"{P}/load-balancer->{P}/ecs-cluster/api", "shop/api->shop/database"]


def test_the_deploy_root_is_reserved() -> None:
    with Workspace("w") as w:
        SoftwareSystem("Deploy")
        SoftwareSystem("deploy!")
    assert [e["id"] for e in export_model(w)["elements"]] == ["deploy-2", "deploy-3"]


def test_two_environments_with_the_same_slug_and_an_environment_with_no_nodes() -> None:
    with Workspace("w") as w:
        with SoftwareSystem("S") as s:
            c = Container("C")
        with DeploymentEnvironment("Prod") as prod:
            with DeploymentNode("Box"):
                ContainerInstance(c)
        with DeploymentEnvironment("prod") as prod2:
            with DeploymentNode("Box"):
                SoftwareSystemInstance(s)
        with DeploymentEnvironment("Empty") as empty:
            pass
        DeploymentView(environment=prod, key="a")
        DeploymentView(environment=prod2, key="b")
        DeploymentView(environment=empty, key="c")
    model = export_model(w)
    assert errors_of(model) == []
    envs = model["deployment"]["environments"]
    assert [(e["key"], e["name"], e["nodes"], e["views"]) for e in envs] == [
        ("prod", "Prod", ["deploy/prod/box"], ["a"]), ("prod-2", "prod", ["deploy/prod-2/box"], ["b"]),
        ("empty", "Empty", [], ["c"])]
    el = {e["id"]: e for e in model["elements"]}
    assert el["deploy/prod-2/box/s"]["instanceOf"] == "s" and el["deploy/prod-2/box/s"]["type"] == "SoftwareSystemInstance"
    levels = {lv["key"]: lv for lv in build_levels(w, model)["levels"]}
    assert levels["v/c"]["nodes"] == [] and levels["v/c"]["edges"] == []
    assert [n["id"] for n in levels["v/b"]["nodes"]] == ["deploy/prod-2/box", "deploy/prod-2/box/s"]


def test_old_structurizr_shapes_are_read() -> None:
    """No environment (Structurizr's 'Default'), instances as a number, no name on an instance, health checks."""
    ws = workspace_json(shop())
    raw = copy.deepcopy(ws)

    def strip(n: Json) -> None:
        n.pop("environment", None)
        for c in n.get("children", []):
            strip(c)
        for k in ("containerInstances", "infrastructureNodes"):
            for x in n.get(k, []):
                x.pop("environment", None)
    for n in raw["model"]["deploymentNodes"]:
        strip(n)
        n["instances"] = 3
    for v in raw["views"]["deploymentViews"]:
        v.pop("environment")
    inst = raw["model"]["deploymentNodes"][0]["children"][0]["children"][0]["containerInstances"][0]
    inst["healthChecks"] = [{"name": "ping", "url": "https://shop/health", "interval": 60, "timeout": 500}]
    model = export_model(raw)
    assert errors_of(model) == []
    assert [e["key"] for e in model["deployment"]["environments"]] == ["default"]
    el = {e["id"]: e for e in model["elements"]}
    assert el["deploy/default/aws"]["instances"] == "3"
    assert el["deploy/default/aws/eu-west-1/ecs-cluster/api"]["healthChecks"] == [
        {"name": "ping", "url": "https://shop/health", "interval": 60, "timeout": 500}]


def test_an_instance_of_a_missing_element_is_a_broken_workspace() -> None:
    raw = workspace_json(shop())
    raw["model"]["deploymentNodes"][0]["children"][0]["children"][0]["containerInstances"][0]["containerId"] = "999"
    with pytest.raises(BrokenDeployment, match=r"ContainerInstance .* is an instance of '999', which is not a Container"):
        export_model(raw)


def test_the_checker_catches_bad_deployment_data() -> None:
    good = export_model(shop())

    def bad(change: Any) -> list[str]:
        m = copy.deepcopy(good)
        change(m)
        return errors_of(rehash(m))

    def el(m: Json, path: str) -> Json:
        return next(e for e in m["elements"] if e["id"] == path)

    assert any("unknown environment" in e for e in bad(lambda m: el(m, P).update(environment="staging")))
    assert any("is not a Container" in e for e in bad(lambda m: el(m, f"{P}/ecs-cluster/api").update(instanceOf="shop")))
    assert any("instances is required" in e for e in bad(lambda m: el(m, P).pop("instances")))
    assert any("only for deployment elements" in e for e in bad(lambda m: el(m, "shop").update(environment="production")))
    assert any("nodes" in e for e in bad(lambda m: m["deployment"]["environments"][0].update(nodes=[])))
    assert any("cannot be in the deployment view" in e for e in bad(lambda m: el(m, "shop").update(views=["production"])))
    assert any("environment is required" in e for e in bad(lambda m: m["views"][1].pop("environment")))


def test_cross_environment_relationships_build_and_are_not_drawn() -> None:
    """The DSL allows a relationship between nodes of two environments; it is in the model, in no view."""
    with Workspace("w") as w:
        with SoftwareSystem("S"):
            c = Container("C")
        with DeploymentEnvironment("A") as a:
            with DeploymentNode("One") as one:
                ContainerInstance(c)
        with DeploymentEnvironment("B") as b:
            with DeploymentNode("Two") as two:
                ContainerInstance(c)
        one >> "Replicates to" >> two
        DeploymentView(environment=a, key="a")
        DeploymentView(environment=b, key="b")
    model = export_model(w)
    assert errors_of(model) == []
    assert [r["id"] for r in model["relationships"]] == ["deploy/a/one->deploy/b/two"]
    levels = {lv["key"]: lv for lv in build_levels(w, model)["levels"]}
    assert levels["v/a"]["edges"] == [] and levels["v/b"]["edges"] == []


# --- levels ------------------------------------------------------------------------------------------------


def test_the_deployment_view_level_nests_nodes_as_boundaries() -> None:
    w = shop()
    model = export_model(w)
    levels = {lv["key"]: lv for lv in build_levels(w, model)["levels"]}
    assert list(levels) == ["landscape", "e/shop", "v/shop-containers", "v/production"]  # no e/deploy/... level
    lv = levels["v/production"]
    nodes = {n["id"]: n for n in lv["nodes"]}
    assert [n["id"] for n in lv["nodes"]] == ["deploy/production/aws", P, f"{P}/ecs-cluster", f"{P}/ecs-cluster/api",
                                             f"{P}/load-balancer", f"{P}/rds", f"{P}/rds/database"]
    assert {i: (n["role"], n["parent"]) for i, n in nodes.items()} == {
        "deploy/production/aws": ("boundary", None), P: ("boundary", "deploy/production/aws"),
        f"{P}/ecs-cluster": ("boundary", P), f"{P}/ecs-cluster/api": ("element", f"{P}/ecs-cluster"),
        f"{P}/load-balancer": ("element", P), f"{P}/rds": ("boundary", P), f"{P}/rds/database": ("element", f"{P}/rds")}
    assert nodes[f"{P}/ecs-cluster"]["instances"] == "2" and "instances" not in nodes[P]
    assert "dash" not in nodes[P]["style"]  # deployment nodes have a solid border
    assert [ln["text"] for ln in nodes[f"{P}/ecs-cluster"]["lines"]] == ["ECS Cluster", "[Deployment Node: Amazon ECS]"]
    db = nodes[f"{P}/rds/database"]
    assert db["shape"] == "Cylinder" and [ln["text"] for ln in db["lines"]] == ["Database", "[Container: PostgreSQL]"]
    assert [(e["id"], e["rels"]) for e in lv["edges"]] == [
        (f"{P}/ecs-cluster/api->{P}/rds/database", ["shop/api->shop/database"]),  # stands for the container relationship
        (f"{P}/load-balancer->{P}/ecs-cluster/api", [f"{P}/load-balancer->{P}/ecs-cluster/api"])]


def test_a_node_with_nothing_inside() -> None:
    """The DSL leaves a node without instances out of a deployment view; one listed anyway is a plain box."""
    with Workspace("w") as w:
        with DeploymentEnvironment("Live") as live:
            with DeploymentNode("Rack"):
                DeploymentNode("Spare server", technology="Ubuntu")
        DeploymentView(environment=live, key="live")
    model = export_model(w)
    assert errors_of(model) == [] and [e["id"] for e in model["elements"]] == ["deploy/live/rack",
                                                                                "deploy/live/rack/spare-server"]
    lv = next(lv for lv in build_levels(w, model)["levels"] if lv["key"] == "v/live")
    assert lv["nodes"] == []
    raw = workspace_json(w)
    rack = raw["model"]["deploymentNodes"][0]
    raw["views"]["deploymentViews"][0]["elements"] = [{"id": rack["children"][0]["id"]}]  # the parent is added
    model = export_model(raw)
    lv = next(lv for lv in build_levels(raw, model)["levels"] if lv["key"] == "v/live")
    assert [(n["id"], n["role"]) for n in lv["nodes"]] == [("deploy/live/rack", "boundary"),
                                                          ("deploy/live/rack/spare-server", "element")]


# --- build, layout and check (real ELK) ----------------------------------------------------------------------


def built(tmp_path: Path, text: str, name: str = "ws.py") -> Path:
    from buildzr.site.build import build_workspace
    src = tmp_path / name
    src.write_text(text)
    out = tmp_path / "built"
    info = build_workspace(str(src), str(out), static_dir=str(make_static(tmp_path / "static")))
    assert info["status"] == "ok", info
    return out


def scene(out: Path, key: str) -> Json:
    index = json.loads((out / "data" / "index.json").read_text())
    return json.loads((out / "data" / index["scenes"][key]["file"]).read_text())  # type: ignore[no-any-return]


@needs_node
def test_shop_builds_and_the_view_is_checked(tmp_path: Path) -> None:
    out = built(tmp_path, SHOP)
    assert check_built(str(out / "data")).errors == []
    sc = scene(out, "v/production")
    nodes = {n["id"]: n for n in sc["nodes"]}
    assert nodes[f"{P}/ecs-cluster"]["instances"] == "2" and nodes[f"{P}/ecs-cluster"]["role"] == "boundary"
    inner, outer = nodes[f"{P}/ecs-cluster/api"], nodes[f"{P}/ecs-cluster"]
    assert outer["x"] <= inner["x"] and inner["x"] + inner["w"] <= outer["x"] + outer["w"]
    assert len(sc["edges"]) == 2


DEEP_AND_WIDE = '''
from buildzr.dsl import (Workspace, SoftwareSystem, Container, DeploymentEnvironment, DeploymentNode,
                         ContainerInstance, DeploymentView)

with Workspace('Big') as w:
    with SoftwareSystem('S') as s:
        cs = [Container(f'Service {i}') for i in range(12)]
    for a, b in zip(cs, cs[1:]):
        a >> 'Calls' >> b
    with DeploymentEnvironment('Live') as live:
        with DeploymentNode('Level 0'):
            def nest(depth):
                with DeploymentNode(f'Level {depth}'):
                    if depth < 12:
                        nest(depth + 1)
                    else:
                        ContainerInstance(cs[0])
            nest(1)
        for r in range(10):
            with DeploymentNode(f'Region {r}', instances='3'):
                for c in cs[:11]:
                    ContainerInstance(c)
    DeploymentView(environment=live, key='live')
'''


@needs_node
def test_deep_nesting_and_over_a_hundred_instances_build(tmp_path: Path) -> None:
    out = built(tmp_path, DEEP_AND_WIDE)
    assert check_built(str(out / "data")).errors == []
    model = json.loads((out / "data" / json.loads((out / "data" / "index.json").read_text())["model"]["file"]).read_text())
    assert sum(e["type"] == "ContainerInstance" for e in model["elements"]) == 111
    sc = scene(out, "v/live")
    deepest = max(n["id"].count("/") for n in sc["nodes"])
    assert deepest == 15 and len(sc["nodes"]) == 13 + 1 + 10 + 110


@needs_node
def test_a_broken_deployment_is_a_broken_workspace_with_a_clear_message(tmp_path: Path) -> None:
    from buildzr.site.build import build_all
    folder = tmp_path / "workspaces"
    folder.mkdir()
    (folder / "bad.py").write_text(
        "import json\n"
        "from buildzr.dsl import Workspace, SoftwareSystem, Container, DeploymentEnvironment, DeploymentNode, "
        "ContainerInstance\n"
        "with Workspace('Bad') as w:\n"
        "    with SoftwareSystem('S'):\n"
        "        c = Container('C')\n"
        "    with DeploymentEnvironment('Live'):\n"
        "        with DeploymentNode('Box'):\n"
        "            ContainerInstance(c)\n"
        "    c.model.id = 'gone'\n")  # the instance now names an element that is not there
    result = build_all(str(folder), str(tmp_path / "out"), static_dir=str(make_static(tmp_path / "static")))
    assert [b.name for b in result.broken] == ["bad"]
    errors = result.broken[0].info["errors"]
    assert any("BrokenDeployment" in e and "not a Container of the model" in e for e in errors), errors


def test_deployment_export_does_not_depend_on_the_hash_seed(tmp_path: Path) -> None:
    src = tmp_path / "shop.py"
    src.write_text(SHOP)
    code = ("import sys; from buildzr.site.export import load_workspaces; from buildzr.site.model import export_model; "
            "from buildzr.site.levels import build_levels; from buildzr.site.canonical import dumps; "
            f"w = load_workspaces({str(src)!r})[-1]; m = export_model(w); "
            "sys.stdout.write(dumps(m) + dumps(build_levels(w, m)))")
    outs = set()
    for seed in ("0", "1", "4242"):
        env = dict(os.environ, PYTHONHASHSEED=seed, PYTHONPATH=ROOT)
        outs.add(subprocess.run([sys.executable, "-c", code], cwd=str(tmp_path), env=env, capture_output=True,
                                text=True, check=True).stdout)
    assert len(outs) == 1


# --- Model API -----------------------------------------------------------------------------------------------


def test_the_api_answers_about_deployment() -> None:
    api = Api(export_model(shop()))
    doc = api.answer("", "")
    assert doc["environments"] == [{"key": "production", "name": "Production", "nodes": ["deploy/production/aws"],
                                    "views": ["production"]}]
    assert doc["endpoints"]["views"] == "/api/v1/views{?scope,environment}"
    e = api.answer("element", f"id={P}/ecs-cluster/api")["element"]
    assert e["instanceOf"] == "shop/api" and e["environment"] == "production" and e["type"] == "ContainerInstance"
    assert e["viewerUrl"] == f"/#/v/production?sel={P}/ecs-cluster/api"
    node = api.answer("element", f"id={P}/ecs-cluster")["element"]
    assert node["instances"] == "2" and node["children"] == [f"{P}/ecs-cluster/api"]
    assert "environment" not in api.answer("element", "id=shop/api")["element"]
    nodes = api.answer("elements", "type=DeploymentNode")
    assert [i["id"] for i in nodes["items"]] == ["deploy/production/aws", P, f"{P}/ecs-cluster", f"{P}/rds"]
    vs = api.answer("views", "environment=production")["items"]
    assert [(v["key"], v["kind"], v["environment"]) for v in vs] == [("production", "deployment", "production")]
    assert api.answer("views", "")["items"][0]["environment"] is None
    with pytest.raises(Exception, match="no environment 'staging'; environments: production"):
        api.answer("views", "environment=staging")
    v = api.answer("view", "key=production")["view"]
    assert [b["id"] for b in v["elements"]][:2] == ["deploy/production/aws", P]
    t = api.answer("tree", "id=deploy/production/aws&depth=4")["items"][0]
    assert t["children"][0]["id"] == P
    lb = api.answer("neighbours", f"id={P}/load-balancer&direction=out")["items"]
    assert [i["element"]["id"] for i in lb] == [f"{P}/ecs-cluster/api"]
    assert "Deployment environments: Production (`production`)" in api.llms_txt()


def test_an_old_model_without_environments_still_serves() -> None:
    model = export_model(shop())
    old = {**model, "elements": [e for e in model["elements"] if not e["id"].startswith("deploy/")],
           "views": [v for v in model["views"] if v["kind"] != "deployment"], "relationships": [
               r for r in model["relationships"] if not r["id"].startswith("deploy/")]}
    old.pop("deployment")
    doc = Api(old).answer("", "")
    assert doc["environments"] == [] and doc["counts"]["elements"] == 4


def test_scene_bytes_are_canonical_for_a_deployment_level() -> None:
    w = shop()
    model = export_model(w)
    lv = next(lv for lv in build_levels(w, model)["levels"] if lv["key"] == "v/production")
    assert dumps(lv) == dumps(json.loads(dumps(lv)))
