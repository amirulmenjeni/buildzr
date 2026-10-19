"""Export a buildzr workspace as ``model.json`` (``buildzr.model/2``).

The model is read from the Structurizr JSON buildzr already produces
(``Workspace.to_json()``): people, software systems, containers and components,
then the deployment environments with their deployment nodes, infrastructure
nodes and instances (ids under ``deploy/<environment>/``). Relationships buildzr
implied (Structurizr ``linkedRelationshipId``) are dropped: the viewer rolls
relationships up itself, and an instance relationship stands for the container
relationship it was copied from.
"""

from __future__ import annotations

import json
import re
from typing import Any, Optional

from buildzr.site.canonical import MODEL_SCHEMA, model_hash

Json = dict[str, Any]

#: Element types written in v4, with the Structurizr type tag.
TYPE_TAG = {
    "Person": "Person",
    "SoftwareSystem": "Software System",
    "Container": "Container",
    "Component": "Component",
    "Element": "Element",
    "DeploymentNode": "Deployment Node",
    "InfrastructureNode": "Infrastructure Node",
    "ContainerInstance": "Container Instance",
    "SoftwareSystemInstance": "Software System Instance",
}

#: Types the level graphs draw; other types (custom elements) are exported but not drawn.
DRAWN_TYPES = ("Person", "SoftwareSystem", "Container", "Component")

#: Deployment element types; deployment views draw them, the landscape and element levels never do.
DEPLOYMENT_TYPES = ("DeploymentNode", "InfrastructureNode", "ContainerInstance", "SoftwareSystemInstance")

#: Root of every deployment element id (``deploy/<environment>/<node>/...``); no static root element takes it.
DEPLOY_ROOT = "deploy"

#: Environment of a deployment node that names none (Structurizr's default).
DEFAULT_ENVIRONMENT = "Default"

#: Structurizr view lists in the order the export reads them, with the schema's ``kind``.
VIEW_KINDS = (
    ("systemLandscapeViews", "systemLandscape"),
    ("systemContextViews", "systemContext"),
    ("containerViews", "container"),
    ("componentViews", "component"),
    ("dynamicViews", "dynamic"),
    ("deploymentViews", "deployment"),
)


def slug(name: str, empty: str = "element") -> str:
    """Lower-case ``name``; runs of characters outside ``[a-z0-9]`` become ``-``; trim ``-``."""
    s = re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")
    return s or empty


def _unique(base: str, used: set[str]) -> str:
    """``base``, or ``base-2``, ``base-3`` ... whichever is free; marks it used."""
    cand, i = base, 2
    while cand in used:
        cand, i = f"{base}-{i}", i + 1
    used.add(cand)
    return cand


def workspace_json(workspace: Any) -> Json:
    """The Structurizr JSON of a DSL workspace (a dict is passed through)."""
    if isinstance(workspace, dict):
        return workspace
    return json.loads(workspace.to_json())  # type: ignore[no-any-return]


def ordered_tags(tags: str) -> list[str]:
    """Tags of an element or relationship in the order Structurizr JSON has them."""
    return [t for t in (tags or "").split(",") if t]


def _num_key(model_id: str) -> tuple[int, str]:
    return (int(model_id), model_id) if model_id.isdigit() else (1 << 62, model_id)


def _structurizr_elements(ws: Json) -> list[tuple[Json, str, Optional[Json]]]:
    """``(raw, type, parent raw)`` in model pre-order: people, then systems with their children."""
    model = ws.get("model", {})
    out: list[tuple[Json, str, Optional[Json]]] = []
    for p in model.get("people", []):
        out.append((p, "Person", None))
    for s in model.get("softwareSystems", []):
        out.append((s, "SoftwareSystem", None))
        for c in s.get("containers", []):
            out.append((c, "Container", s))
            for k in c.get("components", []):
                out.append((k, "Component", c))
    for e in model.get("customElements", []):  # exported as type "Element", never drawn
        out.append((e, "Element", None))
    return out


def _deployment_elements(ws: Json) -> list[tuple[Json, str, Optional[Json], str]]:
    """``(raw, type, parent raw, environment name)`` of every deployment element, in model pre-order.

    A node's children come in Structurizr's order: child nodes, infrastructure nodes, software system instances,
    container instances. Old shapes are tolerated: no ``environment`` means :data:`DEFAULT_ENVIRONMENT`.
    """
    out: list[tuple[Json, str, Optional[Json], str]] = []

    def env_of(raw: Json, inherited: str) -> str:
        e = raw.get("environment")
        return str(e) if isinstance(e, str) and e else inherited

    def walk(node: Json, parent: Optional[Json], inherited: str) -> None:
        env = env_of(node, inherited)
        out.append((node, "DeploymentNode", parent, env))
        for c in node.get("children") or []:
            walk(c, node, env)
        for key, typ in (("infrastructureNodes", "InfrastructureNode"),
                         ("softwareSystemInstances", "SoftwareSystemInstance"),
                         ("containerInstances", "ContainerInstance")):
            for x in node.get(key) or []:
                out.append((x, typ, node, env))

    for n in ws.get("model", {}).get("deploymentNodes") or []:
        walk(n, None, DEFAULT_ENVIRONMENT)
    return out


def _structurizr_relationship_holders(ws: Json) -> list[Json]:
    """Every raw element that can hold relationships: static elements, then deployment elements."""
    return [r for r, _t, _p in _structurizr_elements(ws)] + [r for r, _t, _p, _e in _deployment_elements(ws)]


def _view_scope(view: Json) -> Optional[str]:
    for key in ("softwareSystemId", "containerId", "elementId"):
        if view.get(key):
            return str(view[key])
    return None


class BrokenDeployment(ValueError):
    """The deployment part of the Structurizr JSON cannot be exported (e.g. an instance of an unknown element)."""


def _element(raw: Json, typ: str, path: str, parent: Optional[str]) -> Json:
    return {
        "id": path, "modelId": str(raw["id"]), "type": typ, "parent": parent, "children": [],
        "name": raw.get("name", ""), "description": raw.get("description") or None,
        "technology": raw.get("technology") or None,
        "tags": ordered_tags(raw.get("tags", "")),
        "properties": {str(k): str(v) for k, v in sorted((raw.get("properties") or {}).items())},
        "url": raw.get("url") or None, "group": raw.get("group") or None, "views": [],
    }


def _health_checks(raw: Json) -> list[Json]:
    out: list[Json] = []
    for h in raw.get("healthChecks") or []:
        if not isinstance(h, dict):
            continue
        out.append({"name": str(h.get("name") or ""), "url": str(h.get("url") or ""),
                    "interval": int(h["interval"]) if isinstance(h.get("interval"), (int, float)) else None,
                    "timeout": int(h["timeout"]) if isinstance(h.get("timeout"), (int, float)) else None})
    return out


def export_model(workspace: Any) -> Json:
    """Return the ``buildzr.model/2`` object of ``workspace``.

    Args:
        workspace: A buildzr DSL ``Workspace`` (or its Structurizr JSON as a dict).

    Returns:
        The model as a plain dict, ``modelHash`` included. Write it with
        :func:`buildzr.site.canonical.dumps`.

    Raises:
        BrokenDeployment: An instance names an element that is not in the model, or a deployment element has no id.
    """
    ws = workspace_json(workspace)
    raws = _structurizr_elements(ws)

    # --- elements: slug paths ---------------------------------------------------
    path_of: dict[str, str] = {}  # Structurizr id -> path
    used_by_parent: dict[Optional[str], set[str]] = {None: {DEPLOY_ROOT}}  # 'deploy' is the deployment root
    elements: list[Json] = []
    by_path: dict[str, Json] = {}
    for raw, typ, parent_raw in raws:
        parent = path_of.get(parent_raw["id"]) if parent_raw else None
        used = used_by_parent.setdefault(parent, set())
        seg = _unique(slug(raw.get("name", "")), used)
        path = f"{parent}/{seg}" if parent else seg
        path_of[raw["id"]] = path
        el = _element(raw, typ, path, parent)
        if parent:
            by_path[parent]["children"].append(path)
        elements.append(el)
        by_path[path] = el

    # --- deployment: environments, then their elements ---------------------------
    deployment = _deployment_elements(ws)
    env_names: list[str] = []
    for _raw, _typ, _parent, env in deployment:
        if env not in env_names:
            env_names.append(env)
    for v in ws.get("views", {}).get("deploymentViews") or []:
        env = v.get("environment") if isinstance(v.get("environment"), str) and v.get("environment") else \
            DEFAULT_ENVIRONMENT
        if env not in env_names:
            env_names.append(env)
    used_env: set[str] = set()
    environments: list[Json] = []
    env_by_name: dict[str, Json] = {}
    for name in env_names:
        key = _unique(slug(name, empty="environment"), used_env)
        env_el: Json = {"key": key, "name": name, "id": f"{DEPLOY_ROOT}/{key}", "nodes": [], "views": []}
        environments.append(env_el)
        env_by_name[name] = env_el
    for raw, typ, parent_raw, env in deployment:
        if not isinstance(raw, dict) or raw.get("id") is None:
            raise BrokenDeployment(f"a {typ} in environment {env!r} has no id")
        if str(raw["id"]) in path_of:
            raise BrokenDeployment(f"{typ} {raw['id']} in environment {env!r} has the id of another element")
        e = env_by_name[env]
        parent = path_of.get(str(parent_raw["id"])) if parent_raw else None
        name = raw.get("name", "")
        of: Optional[str] = None
        if typ in ("ContainerInstance", "SoftwareSystemInstance"):
            ref_key = "containerId" if typ == "ContainerInstance" else "softwareSystemId"
            want = "Container" if typ == "ContainerInstance" else "SoftwareSystem"
            of = path_of.get(str(raw.get(ref_key)))
            if of is None or by_path[of]["type"] != want:
                raise BrokenDeployment(f"{typ} {raw['id']} in environment {env!r} is an instance of "
                                       f"{raw.get(ref_key)!r}, which is not a {want} of the model")
            name = by_path[of]["name"]
        base = parent if parent else e["id"]
        used = used_by_parent.setdefault(base, set())
        seg = _unique(slug(name), used)
        path = f"{base}/{seg}"
        path_of[str(raw["id"])] = path
        el = _element({**raw, "name": name}, typ, path, parent)
        el["environment"] = e["key"]
        if of is not None:
            target = by_path[of]
            el["instanceOf"] = of
            el["description"] = target["description"]
            el["technology"] = target["technology"]
            checks = _health_checks(raw)
            if checks:
                el["healthChecks"] = checks
        if typ == "DeploymentNode":
            inst = raw.get("instances")
            el["instances"] = str(inst) if inst is not None and str(inst) != "" else "1"
        if parent:
            by_path[parent]["children"].append(path)
        else:
            e["nodes"].append(path)
        elements.append(el)
        by_path[path] = el

    # --- relationships: explicit only ------------------------------------------
    explicit: list[Json] = []
    for raw in _structurizr_relationship_holders(ws):
        for r in raw.get("relationships") or []:
            if r.get("linkedRelationshipId"):
                continue
            src, dst = path_of.get(str(r.get("sourceId"))), path_of.get(str(r.get("destinationId")))
            if src is None or dst is None:
                continue
            explicit.append({"raw": r, "src": src, "dst": dst})
    explicit.sort(key=lambda x: _num_key(str(x["raw"]["id"])))
    pair_count: dict[tuple[str, str], int] = {}
    for x in explicit:
        pair_count[(x["src"], x["dst"])] = pair_count.get((x["src"], x["dst"]), 0) + 1
    used_ids: set[str] = set()
    relationships: list[Json] = []
    for x in explicit:
        r = x["raw"]
        base = f"{x['src']}->{x['dst']}"
        if pair_count[(x["src"], x["dst"])] > 1:
            base += ":" + slug(r.get("description") or "", empty="rel")
        relationships.append({
            "id": _unique(base, used_ids), "modelId": str(r["id"]),
            "source": x["src"], "destination": x["dst"],
            "description": r.get("description") or None, "technology": r.get("technology") or None,
            "tags": ordered_tags(r.get("tags", "")),
            "properties": {str(k): str(v) for k, v in sorted((r.get("properties") or {}).items())},
        })
    relationships.sort(key=lambda r: r["id"])

    # --- views ------------------------------------------------------------------
    views: list[Json] = []
    used_keys: set[str] = set()
    for list_name, kind in VIEW_KINDS:
        for v in ws.get("views", {}).get(list_name) or []:
            key = _unique(slug(v.get("key", ""), empty="view"), used_keys)
            scope_id = _view_scope(v)
            scope = path_of.get(scope_id) if scope_id else None
            mv: Json = {
                "key": key, "viewKey": v.get("key", ""), "kind": kind,
                "title": v.get("title") or v.get("description") or v.get("key", ""),
                "description": v.get("description") or None, "scope": scope, "scene": f"v/{key}",
            }
            members = {path_of[str(e["id"])] for e in v.get("elements") or [] if str(e.get("id")) in path_of}
            if kind == "deployment":
                env_name = v.get("environment") if isinstance(v.get("environment"), str) and v.get("environment") \
                    else DEFAULT_ENVIRONMENT
                view_env = env_by_name[env_name]
                mv["environment"] = view_env["key"]
                view_env["views"].append(key)
                members = {m for m in members if by_path[m].get("environment") == view_env["key"]}
                for m in list(members):  # a drawn element is drawn inside its nodes
                    p = by_path[m]["parent"]
                    while p is not None and p not in members:
                        members.add(p)
                        p = by_path[p]["parent"]
            else:
                members = {m for m in members if by_path[m]["type"] not in DEPLOYMENT_TYPES}
            views.append(mv)
            if kind == "container":  # buildzr lists components related to containers; C4 does not
                members = {m for m in members if by_path[m]["type"] != "Component"}
            elif kind == "component":
                members = {m for m in members
                           if by_path[m]["type"] != "Component" or by_path[m]["parent"] == scope}
            if kind in ("container", "component") and scope is not None:
                members.add(scope)  # drawn as the enclosing boundary
            if kind == "dynamic":  # dynamic views list their elements through the steps
                members |= {path_of[i] for r in v.get("relationships") or []
                            for i in _ends(ws, r) if i in path_of and by_path[path_of[i]]["type"] not in DEPLOYMENT_TYPES}
            for p in members:
                by_path[p]["views"].append(key)
    view_order = {v["key"]: i for i, v in enumerate(views)}
    for el in elements:
        el["views"].sort(key=view_order.__getitem__)

    model: Json = {
        "schema": MODEL_SCHEMA, "modelHash": "",
        "workspace": {"name": ws.get("name", ""), "description": ws.get("description") or None},
        "elements": elements, "relationships": relationships, "views": views,
        "deployment": {"environments": environments},
    }
    model["modelHash"] = model_hash(model)
    return model


def _ends(ws: Json, rv: Json) -> tuple[str, str]:
    """Source and destination Structurizr ids of a relationship view entry."""
    rel = all_relationships(ws).get(str(rv.get("id")))
    return (str(rel["sourceId"]), str(rel["destinationId"])) if rel else ("", "")


def all_relationships(ws: Json) -> dict[str, Json]:
    """Every relationship of the model (static and deployment elements) by Structurizr id."""
    out: dict[str, Json] = {}
    for raw in _structurizr_relationship_holders(ws):
        for r in raw.get("relationships") or []:
            out[str(r["id"])] = r
    return out


class ModelIndex:
    """Lookups over a ``buildzr.model/2`` object, with the rollup helper."""

    def __init__(self, model: Json) -> None:
        self.model = model
        self.el: dict[str, Json] = {e["id"]: e for e in model["elements"]}
        self.rel: dict[str, Json] = {r["id"]: r for r in model["relationships"]}
        self.roots = [e["id"] for e in model["elements"] if e["parent"] is None]
        self.by_model_id = {e["modelId"]: e["id"] for e in model["elements"]}
        self.rel_by_model_id = {r["modelId"]: r["id"] for r in model["relationships"]}

    def ancestors_or_self(self, path: str) -> list[str]:
        """``path`` and its ancestors, innermost first."""
        out: list[str] = []
        cur: Optional[str] = path
        while cur is not None:
            out.append(cur)
            cur = self.el[cur]["parent"]
        return out

    def in_subtree(self, path: str, root: str) -> bool:
        return root in self.ancestors_or_self(path)


def rollup(model: Json, a: str, b: str) -> list[str]:
    """Ids of explicit relationships from the subtree of ``a`` to the subtree of ``b``, sorted."""
    idx = ModelIndex(model)
    return sorted(r["id"] for r in model["relationships"]
                  if idx.in_subtree(r["source"], a) and idx.in_subtree(r["destination"], b))
