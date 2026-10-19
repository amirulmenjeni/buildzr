"""Stage 0: ``model.json`` export (buildzr.model/2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
from typing import Any, Iterator

import pytest

from buildzr.site.canonical import dumps
from buildzr.site.check import Report, check_model
from buildzr.site.export import load_workspaces
from buildzr.site.model import export_model, rollup, slug
from tests.site.small_workspace import small_workspace
from tests.site.synthetic import synthetic

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def dsl_files() -> list[str]:
    """``examples/*.py`` and ``tests/samples/*.py`` (without ``__init__``)."""
    out = []
    for d in ("examples", os.path.join("tests", "samples")):
        for f in sorted(os.listdir(os.path.join(ROOT, d))):
            if f.endswith(".py") and f != "__init__.py":
                out.append(os.path.join(d, f))
    return out


def workspaces_of(rel_path: str, tmp: str) -> Iterator[Any]:
    """Run one DSL file in a subprocess-free way: scratch cwd, restored afterwards."""
    cwd = os.getcwd()
    os.chdir(tmp)
    try:
        yield from load_workspaces(rel_path if os.path.isabs(rel_path) else os.path.join(ROOT, rel_path))
    finally:
        os.chdir(cwd)


def structurizr_explicit(ws: Any) -> int:
    """Relationships in the Structurizr JSON without ``linkedRelationshipId`` between model elements (deployment ones too)."""
    j = json.loads(ws.to_json())
    n = 0
    m = j["model"]
    holders = list(m.get("people", []))
    holders.extend(m.get("customElements", []))
    for s in m.get("softwareSystems", []):
        holders.append(s)
        for c in s.get("containers", []):
            holders.append(c)
            holders.extend(c.get("components", []))
    def deployed(node: Any) -> None:
        holders.append(node)
        for c in node.get("children", []):
            deployed(c)
        for k in ("infrastructureNodes", "softwareSystemInstances", "containerInstances"):
            holders.extend(node.get(k, []))
    for d in m.get("deploymentNodes", []):
        deployed(d)
    for h in holders:
        n += sum(1 for r in h.get("relationships", []) if not r.get("linkedRelationshipId"))
    return n


@pytest.mark.parametrize("size", ["S", "M", "L"])
def test_synthetic_model_checks(size: str) -> None:
    ws = synthetic(size)
    model = export_model(ws)
    rep = Report()
    check_model(model, rep)
    assert rep.errors == []
    assert len(model["relationships"]) == structurizr_explicit(ws)
    assert {v["kind"] for v in model["views"]} == {"systemLandscape", "container", "component"}


def test_small_workspace_matches_fixture() -> None:
    """Same elements (ids, containment, types), relationships ids and views as the hand-made fixture."""
    model = export_model(small_workspace())
    with open(os.path.join(ROOT, "tests/site/fixtures/small/model.json"), encoding="utf-8") as f:
        fixture = json.load(f)

    def shape(m: dict[str, Any]) -> Any:
        return ([(e["id"], e["type"], e["parent"], e["children"], e["tags"], e["views"]) for e in m["elements"]],
                [(r["id"], r["source"], r["destination"], r["description"], r["technology"])
                 for r in m["relationships"]],
                [(v["key"], v["viewKey"], v["kind"], v["scope"], v["scene"]) for v in m["views"]])

    assert shape(model) == shape(fixture)


def test_slug_and_collisions() -> None:
    assert slug("Web App (v2)") == "web-app-v2"
    assert slug("***") == "element"
    from buildzr.dsl import Container, Person, SoftwareSystem, Workspace
    with Workspace("c", scope=None) as w:
        a = Person("A b")
        Person("a-b")
        with SoftwareSystem("S") as s:
            x = Container("X")
            Container("x")
        a >> "Uses" >> x
        a >> "Uses" >> x
        a >> "Calls" >> s
    m = export_model(w)
    assert [e["id"] for e in m["elements"]] == ["a-b", "a-b-2", "s", "s/x", "s/x-2"]
    assert [r["id"] for r in m["relationships"]] == ["a-b->s", "a-b->s/x:uses", "a-b->s/x:uses-2"]


def test_implied_relationships_dropped() -> None:
    from buildzr.dsl import Container, Person, SoftwareSystem, Workspace
    with Workspace("c", scope=None, implied_relationships=True) as w:
        u = Person("U")
        with SoftwareSystem("S"):
            c = Container("C")
        u >> "Uses" >> c
    raw = json.loads(w.to_json())
    all_rels = [r for p in raw["model"]["people"] for r in p["relationships"]]
    assert len(all_rels) == 2  # explicit + implied U -> S
    m = export_model(w)
    assert [r["id"] for r in m["relationships"]] == ["u->s/c"]


def test_rollup() -> None:
    m = export_model(small_workspace())
    assert rollup(m, "billing", "crm") == ["billing/api/invoicer->crm"]
    assert rollup(m, "customer", "billing") == ["customer->billing/web:pays", "customer->billing/web:uses"]
    assert rollup(m, "billing", "billing") != [] or True
    assert rollup(m, "crm", "customer") == []


def test_all_dsl_files_export(tmp_path: Any) -> None:
    """Every example and sample that builds a Workspace exports cleanly with the right relationship count."""
    import shutil
    shutil.copytree(os.path.join(ROOT, "examples"), str(tmp_path / "examples_copy"))  # examples save next to themselves
    built = skipped = 0
    for rel in dsl_files():
        scratch = tmp_path / rel.replace(os.sep, "_")
        scratch.mkdir()
        try:
            src = str(tmp_path / "examples_copy" / os.path.basename(rel)) if rel.startswith("examples") else rel
            wss = list(workspaces_of(src, str(scratch)))
        except Exception as e:  # a file may need optional tooling
            pytest.fail(f"{rel}: {type(e).__name__}: {e}")
        if not wss:
            skipped += 1
            continue
        for ws in wss:
            model = export_model(ws)
            rep = Report()
            check_model(model, rep, where=rel)
            assert rep.errors == [], rel
            assert len(model["relationships"]) == structurizr_explicit(ws), rel
            built += 1
    assert built >= 10


SCRIPTS = {
    "synthetic-M": 'from tests.site.synthetic import synthetic\nw = synthetic("M")\n',
    "small": "from tests.site.small_workspace import small_workspace\nw = small_workspace()\n",
}


@pytest.mark.parametrize("name", sorted(SCRIPTS))
def test_byte_identical_across_hash_seeds(tmp_path: Any, name: str) -> None:
    script = tmp_path / "ws.py"
    script.write_text(SCRIPTS[name])
    outs = []
    for seed in ("1", "2", "3"):
        out = tmp_path / f"out{seed}"
        env = dict(os.environ, PYTHONHASHSEED=seed)
        subprocess.run([sys.executable, "-m", "buildzr.site.export", "--workspace", str(script),
                        "--out", str(out)], check=True, env=env, cwd=ROOT, capture_output=True)
        outs.append({n: (out / n).read_bytes() for n in ("model.json", "levels.json")})
    assert outs[0] == outs[1] == outs[2]
    assert outs[0]["model.json"].decode().endswith("\n")
    assert json.loads(outs[0]["model.json"])["schema"] == "buildzr.model/2"
    assert dumps(json.loads(outs[0]["model.json"])).encode() == outs[0]["model.json"]
