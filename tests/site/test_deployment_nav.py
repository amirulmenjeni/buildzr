"""Software that runs in zero, one or several places: what the viewer needs to jump from it to its deployment instances.

The viewer reads ``instanceOf`` of the deployment elements and the ``views`` of each instance; nothing else is added to
``model.json``, so these tests pin what the jump relies on, on the model and on a real build (the committed fixture).
"""

from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from buildzr.site.api import Api
from buildzr.site.build import build_workspace
from buildzr.site.check import Report, check_built, check_model
from buildzr.site.model import export_model
from tests.site.deployment_nav_workspace import deployment_nav_workspace
from tests.site.test_cli import ROOT, needs_node

Json = dict[str, Any]

FIXTURE = Path(ROOT) / "tests" / "site" / "fixtures" / "deployment-nav"

#: What runs where: element id -> the ids of its instances, in model order.
RUNS = {
    "shop/api": ["deploy/production/aws/eu-west-1/ecs-cluster/api", "deploy/production/aws/us-east-1/ecs-cluster/api",
                 "deploy/staging/staging-server/api"],
    "shop/database": ["deploy/production/aws/eu-west-1/rds/database"],
    "shop/worker": [],
    "shop/cache": ["deploy/dev/laptop/cache"],
    "payments": ["deploy/production/payment-provider/payments"],
    "legacy": [],
    "shop": [],
}


def instances(model: Json) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {e["id"]: [] for e in model["elements"] if e["type"] in ("SoftwareSystem", "Container")}
    for e in model["elements"]:
        if e.get("instanceOf"):
            out[e["instanceOf"]].append(e["id"])
    return out


def test_zero_one_and_several_instances_in_the_model() -> None:
    model = export_model(deployment_nav_workspace())
    rep = Report()
    check_model(model, rep)
    assert rep.errors == []
    got = instances(model)
    assert {k: got[k] for k in RUNS} == RUNS
    assert set(got) == set(RUNS), "every software system and container is covered by the table"
    el = {e["id"]: e for e in model["elements"]}
    assert el["deploy/production/aws/eu-west-1/ecs-cluster"]["instances"] == "3"
    assert [el[i]["environment"] for i in RUNS["shop/api"]] == ["production", "production", "staging"]


def test_an_instance_is_drawn_when_its_environment_has_a_view_that_includes_it() -> None:
    model = export_model(deployment_nav_workspace())
    el = {e["id"]: e for e in model["elements"]}
    views = {v["key"] for v in model["views"]}
    shown = {i: any(k in views for k in el[i]["views"]) for ids in RUNS.values() for i in ids}
    assert shown == {
        "deploy/production/aws/eu-west-1/ecs-cluster/api": True,
        "deploy/production/aws/us-east-1/ecs-cluster/api": True,
        "deploy/staging/staging-server/api": True,
        "deploy/production/aws/eu-west-1/rds/database": True,
        "deploy/dev/laptop/cache": False,  # Dev has no deployment view
        "deploy/production/payment-provider/payments": False,  # the Production view is for the Shop system only
    }
    assert [e["key"] for e in model["deployment"]["environments"]] == ["production", "staging", "dev"]


def test_the_model_api_names_what_an_instance_is_an_instance_of() -> None:
    api = Api(export_model(deployment_nav_workspace()))
    shown = api.answer("element", "id=deploy/staging/staging-server/api")["element"]
    assert shown["instanceOf"] == "shop/api" and shown["environment"] == "staging"
    assert shown["viewerUrl"] == "/#/v/staging?sel=deploy/staging/staging-server/api"
    hidden = api.answer("element", "id=deploy/dev/laptop/cache")["element"]
    assert hidden["instanceOf"] == "shop/cache" and hidden["viewerUrl"] is None


def test_the_committed_fixture_passes_the_checker() -> None:
    rep = check_built(str(FIXTURE))
    assert rep.errors == []
    index = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    assert sorted(index["scenes"]) == ["e/shop", "landscape", "v/landscape", "v/production", "v/shop-containers", "v/staging"]
    model = json.loads((FIXTURE / index["model"]["file"]).read_text(encoding="utf-8"))
    assert {k: v for k, v in instances(model).items() if k in RUNS} == RUNS


@needs_node
def test_the_committed_fixture_is_what_the_workspace_builds(tmp_path: Path) -> None:
    src = tmp_path / "workspace.py"
    src.write_text("from tests.site.deployment_nav_workspace import deployment_nav_workspace\nw = deployment_nav_workspace()\n",
                   encoding="utf-8")
    info = build_workspace(str(src), str(tmp_path / "out"), viewer=False)
    assert info.get("status") == "ok", info.get("errors")
    built = json.loads((tmp_path / "out" / "data" / "index.json").read_text(encoding="utf-8"))
    committed = json.loads((FIXTURE / "index.json").read_text(encoding="utf-8"))
    assert built == committed, "run tests/site/fixtures/make_deployment_nav.py"
    shutil.rmtree(tmp_path / "out")
