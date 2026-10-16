"""Export a buildzr workspace as ``model.json`` (``buildzr.model/2``).

The model is read from the Structurizr JSON buildzr already produces
(``Workspace.to_json()``). Only people, software systems, containers and
components are exported; deployment nodes and deployment views are left for a
later version (``deployment.environments`` is empty). Relationships buildzr
implied (Structurizr ``linkedRelationshipId``) are dropped: the viewer rolls
relationships up itself.
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
}

#: Types the level graphs draw; other types (custom elements) are exported but not drawn.
DRAWN_TYPES = ("Person", "SoftwareSystem", "Container", "Component")

#: Structurizr view lists in the order the export reads them, with the schema's ``kind``.
VIEW_KINDS = (
    ("systemLandscapeViews", "systemLandscape"),
    ("systemContextViews", "systemContext"),
    ("containerViews", "container"),
    ("componentViews", "component"),
    ("dynamicViews", "dynamic"),
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


def _view_scope(view: Json) -> Optional[str]:
    for key in ("softwareSystemId", "containerId", "elementId"):
        if view.get(key):
            return str(view[key])
    return None


def export_model(workspace: Any) -> Json:
    """Return the ``buildzr.model/2`` object of ``workspace``.

    Args:
        workspace: A buildzr DSL ``Workspace`` (or its Structurizr JSON as a dict).

    Returns:
        The model as a plain dict, ``modelHash`` included. Write it with
        :func:`buildzr.site.canonical.dumps`.
    """
    ws = workspace_json(workspace)
    raws = _structurizr_elements(ws)

    # --- elements: slug paths ---------------------------------------------------
    path_of: dict[str, str] = {}  # Structurizr id -> path
    used_by_parent: dict[Optional[str], set[str]] = {}
    elements: list[Json] = []
    by_path: dict[str, Json] = {}
    for raw, typ, parent_raw in raws:
        parent = path_of.get(parent_raw["id"]) if parent_raw else None
        used = used_by_parent.setdefault(parent, set())
        seg = _unique(slug(raw.get("name", "")), used)
        path = f"{parent}/{seg}" if parent else seg
        path_of[raw["id"]] = path
        el: Json = {
            "id": path, "modelId": str(raw["id"]), "type": typ, "parent": parent, "children": [],
            "name": raw.get("name", ""), "description": raw.get("description") or None,
            "technology": raw.get("technology") or None,
            "tags": ordered_tags(raw.get("tags", "")),
            "properties": {str(k): str(v) for k, v in sorted((raw.get("properties") or {}).items())},
            "url": raw.get("url") or None, "group": raw.get("group") or None, "views": [],
        }
        if parent:
            by_path[parent]["children"].append(path)
        elements.append(el)
        by_path[path] = el

    # --- relationships: explicit only ------------------------------------------
    explicit: list[Json] = []
    for raw, _typ, _p in raws:
        for r in raw.get("relationships", []):
            if r.get("linkedRelationshipId"):
                continue
            src, dst = path_of.get(r["sourceId"]), path_of.get(r["destinationId"])
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
        for v in ws.get("views", {}).get(list_name, []):
            key = _unique(slug(v.get("key", ""), empty="view"), used_keys)
            scope_id = _view_scope(v)
            scope = path_of.get(scope_id) if scope_id else None
            views.append({
                "key": key, "viewKey": v.get("key", ""), "kind": kind,
                "title": v.get("title") or v.get("description") or v.get("key", ""),
                "description": v.get("description") or None, "scope": scope, "scene": f"v/{key}",
            })
            members = {path_of[e["id"]] for e in v.get("elements", []) if e.get("id") in path_of}
            if kind == "container":  # buildzr lists components related to containers; C4 does not
                members = {m for m in members if by_path[m]["type"] != "Component"}
            elif kind == "component":
                members = {m for m in members
                           if by_path[m]["type"] != "Component" or by_path[m]["parent"] == scope}
            if kind in ("container", "component") and scope is not None:
                members.add(scope)  # drawn as the enclosing boundary
            if kind == "dynamic":  # dynamic views list their elements through the steps
                members |= {path_of[i] for r in v.get("relationships", [])
                            for i in _ends(ws, r) if i in path_of}
            for p in members:
                by_path[p]["views"].append(key)
    for el in elements:
        el["views"].sort(key=[v["key"] for v in views].index)

    model: Json = {
        "schema": MODEL_SCHEMA, "modelHash": "",
        "workspace": {"name": ws.get("name", ""), "description": ws.get("description") or None},
        "elements": elements, "relationships": relationships, "views": views,
        "deployment": {"environments": []},
    }
    model["modelHash"] = model_hash(model)
    return model


def _ends(ws: Json, rv: Json) -> tuple[str, str]:
    """Source and destination Structurizr ids of a relationship view entry."""
    rel = _all_relationships(ws).get(str(rv.get("id")))
    return (str(rel["sourceId"]), str(rel["destinationId"])) if rel else ("", "")


def _all_relationships(ws: Json) -> dict[str, Json]:
    """Every relationship of people, systems, containers and components by Structurizr id."""
    out: dict[str, Json] = {}
    for raw, _t, _p in _structurizr_elements(ws):
        for r in raw.get("relationships", []):
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
