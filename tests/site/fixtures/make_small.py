"""Write the hand-made 'small' fixture: model.json, index.json and its scenes.

Run: ``uv run python tests/site/fixtures/make_small.py``. The output under
``tests/site/fixtures/small/`` is committed; this script documents how the hand
layout was made (coordinates below are chosen by hand, engine "hand").

Model: 2 people, 3 systems; Billing has 3 containers; Billing API has 3
components. Scenes: landscape, e/billing, e/billing/api and the two authored views
v/landscape and v/billing-containers.
"""

from __future__ import annotations

import hashlib
import os
import sys
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.abspath(os.path.join(HERE, "..", "..", "..")))

from buildzr.site.canonical import (  # noqa: E402
    INDEX_SCHEMA,
    MODEL_SCHEMA,
    SCENE_SCHEMA,
    dumps,
    model_hash,
)

OUT = os.path.join(HERE, "small")

# --- model -------------------------------------------------------------------

E: list[dict[str, Any]] = []


def el(id_: str, mid: str, type_: str, name: str, desc: str | None = None,
       tech: str | None = None, extra_tags: tuple[str, ...] = (), views: tuple[str, ...] = (),
       props: dict[str, str] | None = None) -> None:
    parent = id_.rsplit("/", 1)[0] if "/" in id_ else None
    E.append({"id": id_, "modelId": mid, "type": type_, "parent": parent, "children": [],
              "name": name, "description": desc, "technology": tech,
              "tags": ["Element", {"SoftwareSystem": "Software System"}.get(type_, type_), *extra_tags],
              "properties": props or {}, "url": None, "group": None, "views": list(views)})


V_LAND, V_CONT = "landscape", "billing-containers"
el("customer", "1", "Person", "Customer", "Pays invoices online.", views=(V_LAND, V_CONT))
el("support-agent", "2", "Person", "Support Agent", "Handles refunds.", views=(V_LAND,))
el("billing", "3", "SoftwareSystem", "Billing", "Invoices customers and takes payments.",
   views=(V_LAND, V_CONT), props={"owner": "payments-team"})
el("billing/web", "4", "Container", "Web App", "Customer billing portal.", "TypeScript, React",
   views=(V_CONT,))
el("billing/api", "5", "Container", "Billing API", "Invoicing and payment API.", "Go",
   views=(V_CONT,))
el("billing/api/invoicer", "6", "Component", "Invoicer", "Builds monthly invoices.", "Go",
   views=())
el("billing/api/payments", "7", "Component", "Payments", "Charges cards.", "Go",
   extra_tags=("PCI",), views=())
el("billing/api/ledger-repo", "8", "Component", "Ledger Repo", "Ledger persistence.", "Go, sqlc",
   views=())
el("billing/db", "9", "Container", "Billing DB", "Invoices and ledger.", "PostgreSQL",
   extra_tags=("Database",), views=(V_CONT,))
el("crm", "10", "SoftwareSystem", "CRM", "Customer records.", extra_tags=("External",),
   views=(V_LAND, V_CONT))
el("email", "11", "SoftwareSystem", "Email", "Sends e-mail.", extra_tags=("External",),
   views=(V_LAND,))
by_id = {e["id"]: e for e in E}
for e in E:
    if e["parent"]:
        by_id[e["parent"]]["children"].append(e["id"])

R: list[dict[str, Any]] = []


def rel(id_: str, mid: str, src: str, dst: str, desc: str, tech: str | None = None) -> None:
    R.append({"id": id_, "modelId": mid, "source": src, "destination": dst, "description": desc,
              "technology": tech, "tags": ["Relationship"], "properties": {}})


rel("customer->billing/web:uses", "20", "customer", "billing/web", "Uses", "HTTPS")
rel("customer->billing/web:pays", "21", "customer", "billing/web", "Pays", "HTTPS")
rel("billing/web->billing/api", "22", "billing/web", "billing/api", "Calls", "JSON/HTTPS")
rel("billing/web->billing/api/payments", "23", "billing/web", "billing/api/payments", "Submits payment", "JSON/HTTPS")
rel("billing/api/invoicer->crm", "24", "billing/api/invoicer", "crm", "Reads customers", "HTTPS")
rel("billing/api/invoicer->email", "25", "billing/api/invoicer", "email", "Sends invoices", "SMTP")
rel("billing/api/invoicer->billing/api/payments", "26", "billing/api/invoicer", "billing/api/payments", "Charges")
rel("billing/api/payments->billing/db", "27", "billing/api/payments", "billing/db", "Writes payments", "SQL")
rel("billing/api/ledger-repo->billing/db", "28", "billing/api/ledger-repo", "billing/db", "Reads and writes", "SQL")
rel("crm->billing/api", "29", "crm", "billing/api", "Requests refunds", "HTTPS")
rel("support-agent->crm", "30", "support-agent", "crm", "Uses", "HTTPS")
R.sort(key=lambda r: r["id"])

VIEWS = [
    {"key": V_LAND, "viewKey": "Landscape", "kind": "systemLandscape", "title": "System landscape",
     "description": None, "scope": None, "scene": f"v/{V_LAND}"},
    {"key": V_CONT, "viewKey": "Billing-Containers", "kind": "container", "title": "Billing - containers",
     "description": None, "scope": "billing", "scene": f"v/{V_CONT}"},
]

MODEL: dict[str, Any] = {"schema": MODEL_SCHEMA, "modelHash": "",
                         "workspace": {"name": "Small fixture", "description": "Hand-written v4 interface fixture."},
                         "elements": E, "relationships": R, "views": VIEWS, "deployment": {"environments": []}}
MODEL["modelHash"] = model_hash(MODEL)
MH = MODEL["modelHash"]

# --- scenes ------------------------------------------------------------------

STYLE = {
    "Person": {"fill": "#08427b", "stroke": "#052e56", "color": "#ffffff", "fontSize": 16},
    "SoftwareSystem": {"fill": "#1168bd", "stroke": "#0b4884", "color": "#ffffff", "fontSize": 16},
    "External": {"fill": "#999999", "stroke": "#6b6b6b", "color": "#000000", "fontSize": 16},
    "Container": {"fill": "#438dd5", "stroke": "#2e6295", "color": "#000000", "fontSize": 16},
    "Component": {"fill": "#85bbf0", "stroke": "#5d82a8", "color": "#000000", "fontSize": 16},
}
TYPE_LABEL = {"Person": "Person", "SoftwareSystem": "Software System", "Container": "Container",
              "Component": "Component"}
EDGE_STYLE = {"stroke": "#707070", "arrow": "end", "width": 1.5}


def node(id_: str, x: float, y: float, w: float = 240, h: float = 140,
         frame: dict[str, Any] | None = None, desc_lines: tuple[str, ...] = ()) -> dict[str, Any]:
    e = by_id[id_]
    t = e["type"]
    style = dict(STYLE["External" if "External" in e["tags"] else t])
    kind = f"[{TYPE_LABEL[t]}: {e['technology']}]" if e["technology"] else f"[{TYPE_LABEL[t]}]"
    lines = [{"text": e["name"], "tier": 0, "weight": "bold"}, {"text": kind, "tier": 1, "size": 12}]
    lines += [{"text": d, "tier": 2, "size": 12} for d in desc_lines]
    shape = {"Person": "Person"}.get(t, "Cylinder" if "Database" in e["tags"] else "Box")
    n: dict[str, Any] = {"id": id_, "modelId": e["modelId"], "role": "element", "type": t, "parent": None,
                         "x": x, "y": y, "w": w, "h": h, "shape": shape, "style": style,
                         "label": {"lines": lines, "anchor": "top" if frame else "center"},
                         "tags": e["tags"], "name": e["name"]}
    if frame:
        n["frame"] = frame
    return n


def edge(src: Any, dst: Any, pts: list[list[float]], rels: list[str]) -> dict[str, Any]:
    def name(end: Any) -> str:
        return end if isinstance(end, str) else f"port:{end['port']}"
    return {"id": f"{name(src)}->{name(dst)}", "source": src, "target": dst, "points": pts,
            "count": len(rels), "rels": sorted(rels), "style": dict(EDGE_STYLE)}


def scene(key: str, kind: str, scope: str | None, title: str, bounds: list[float],
          ports: list[dict[str, Any]], nodes: list[dict[str, Any]], edges: list[dict[str, Any]]) -> dict[str, Any]:
    return {"schema": SCENE_SCHEMA, "key": key, "level": {"kind": kind, "scope": scope}, "title": title,
            "modelHash": MH, "layout": {"engine": "hand", "version": "1", "inputHash": "sha256:unknown", "passes": 1},
            "bounds": bounds, "ports": sorted(ports, key=lambda p: p["id"]),
            "nodes": sorted(nodes, key=lambda n: n["id"]), "edges": sorted(edges, key=lambda e: e["id"])}


def port(id_: str, x: float, y: float, side: str) -> dict[str, Any]:
    return {"id": id_, "x": x, "y": y, "side": side}


P = lambda pid: {"port": pid}  # noqa: E731

# e/billing/api: 880 x 340, components 240x140 in one row at y=100.
API_PORTS = [
    port("billing/web->billing/api", 440, 0, "N"),
    port("port:crm->billing->billing/api", 760, 0, "N"),
    port("billing/api->port:billing->crm", 100, 340, "S"),
    port("billing/api->billing/db", 440, 340, "S"),
    port("billing/api->port:billing->email", 0, 200, "W"),
]
S_API = scene("e/billing/api", "element", "billing/api", "Billing API", [0, 0, 880, 340], API_PORTS, [
    node("billing/api/invoicer", 40, 100),
    node("billing/api/payments", 320, 100),
    node("billing/api/ledger-repo", 600, 100),
], [
    edge(P("billing/web->billing/api"), "billing/api/payments", [[440, 0], [440, 100]],
         ["billing/web->billing/api/payments"]),
    edge("billing/api/invoicer", P("billing/api->port:billing->crm"), [[100, 240], [100, 340]],
         ["billing/api/invoicer->crm"]),
    edge("billing/api/invoicer", P("billing/api->port:billing->email"), [[40, 200], [0, 200]],
         ["billing/api/invoicer->email"]),
    edge("billing/api/invoicer", "billing/api/payments", [[280, 170], [320, 170]],
         ["billing/api/invoicer->billing/api/payments"]),
    edge("billing/api/payments", P("billing/api->billing/db"), [[440, 240], [440, 340]],
         ["billing/api/payments->billing/db"]),
    edge("billing/api/ledger-repo", P("billing/api->billing/db"), [[720, 240], [720, 300], [440, 300], [440, 340]],
         ["billing/api/ledger-repo->billing/db"]),
])

# e/billing: 840 x 840; Billing API is a frame at (200, 320), scale 0.5 -> 440 x 170.
BILLING_PORTS = [
    port("customer->billing", 420, 0, "N"),
    port("billing->crm", 250, 840, "S"),
    port("billing->email", 0, 420, "W"),
    port("crm->billing", 840, 250, "E"),
]
S_BILLING = scene("e/billing", "element", "billing", "Billing", [0, 0, 840, 840], BILLING_PORTS, [
    node("billing/web", 300, 80),
    node("billing/api", 200, 320, 440, 170,
         frame={"scene": "e/billing/api", "scale": 0.5, "children": 3, "childType": "Component"}),
    node("billing/db", 360, 600),
], [
    edge(P("customer->billing"), "billing/web", [[420, 0], [420, 80]],
         ["customer->billing/web:pays", "customer->billing/web:uses"]),
    edge("billing/web", "billing/api", [[420, 220], [420, 320]],
         ["billing/web->billing/api", "billing/web->billing/api/payments"]),
    edge("billing/api", P("billing->crm"), [[250, 490], [250, 840]], ["billing/api/invoicer->crm"]),
    edge("billing/api", P("billing->email"), [[200, 420], [0, 420]], ["billing/api/invoicer->email"]),
    edge(P("crm->billing"), "billing/api", [[840, 250], [580, 250], [580, 320]], ["crm->billing/api"]),
    edge("billing/api", "billing/db", [[420, 490], [420, 600]],
         ["billing/api/ledger-repo->billing/db", "billing/api/payments->billing/db"]),
])

# landscape: Billing is a frame at (300, 260), scale 0.5 -> 420 x 420.
S_LAND = scene("landscape", "landscape", None, "Small fixture", [0, 0, 840, 1260], [], [
    node("customer", 390, 60),
    node("billing", 300, 260, 420, 420,
         frame={"scene": "e/billing", "scale": 0.5, "children": 3, "childType": "Container"}),
    node("email", 20, 400),
    node("crm", 305, 820),
    node("support-agent", 305, 1080),
], [
    edge("customer", "billing", [[510, 200], [510, 260]],
         ["customer->billing/web:pays", "customer->billing/web:uses"]),
    edge("billing", "crm", [[425, 680], [425, 820]], ["billing/api/invoicer->crm"]),
    edge("billing", "email", [[300, 470], [260, 470]], ["billing/api/invoicer->email"]),
    edge("crm", "billing", [[545, 890], [800, 890], [800, 385], [720, 385]], ["crm->billing/api"]),
    edge("support-agent", "crm", [[425, 1080], [425, 960]], ["support-agent->crm"]),
])

# v/billing-containers: authored container view, Billing as a boundary (no frames, no ports).
bnd = {"id": "billing", "modelId": "3", "role": "boundary", "type": "SoftwareSystem", "parent": None,
       "x": 40, "y": 240, "w": 560, "h": 640, "shape": "Box",
       "style": {"fill": "#ffffff", "stroke": "#1168bd", "color": "#1168bd", "fontSize": 16, "dash": [6, 4]},
       "label": {"lines": [{"text": "Billing", "tier": 0, "weight": "bold"},
                           {"text": "[Software System]", "tier": 1, "size": 12}], "anchor": "bottom-left"},
       "tags": by_id["billing"]["tags"], "name": "Billing"}
inner = [node("billing/web", 200, 280), node("billing/api", 200, 500), node("billing/db", 200, 700)]
for n in inner:
    n["parent"] = "billing"
inner[2]["y"] = 700
bnd["h"] = 900 - 240
S_VIEW = scene(f"v/{V_CONT}", "view", V_CONT, "Billing - containers", [0, 0, 960, 940], [],
               [bnd, *inner, node("customer", 200, 40), node("crm", 680, 500)], [
    edge("customer", "billing/web", [[320, 180], [320, 280]],
         ["customer->billing/web:pays", "customer->billing/web:uses"]),
    edge("billing/web", "billing/api", [[320, 420], [320, 500]],
         ["billing/web->billing/api", "billing/web->billing/api/payments"]),
    edge("billing/api", "crm", [[440, 550], [680, 550]], ["billing/api/invoicer->crm"]),
    edge("crm", "billing/api", [[680, 600], [440, 600]], ["crm->billing/api"]),
    edge("billing/api", "billing/db", [[320, 640], [320, 700]],
         ["billing/api/ledger-repo->billing/db", "billing/api/payments->billing/db"]),
])
# Pre-order with siblings sorted by id: boundary, its children, then the other roots.
S_VIEW["nodes"] = [bnd, *sorted(inner, key=lambda n: n["id"]), node("crm", 680, 500), node("customer", 200, 40)]

# v/landscape: the authored landscape view, same geometry as the landscape level but no frames.
S_VLAND = {**S_LAND, "key": f"v/{V_LAND}", "level": {"kind": "view", "scope": V_LAND}, "title": "System landscape",
           "nodes": [{k: v for k, v in n.items() if k != "frame"} | {"label": {**n["label"], "anchor": "center"}}
                     for n in S_LAND["nodes"]]}

def main() -> None:
    files: dict[str, dict[str, str]] = {}

    def put(rel: str, obj: Any) -> dict[str, str]:
        path = os.path.join(OUT, rel)
        os.makedirs(os.path.dirname(path), exist_ok=True)
        text = dumps(obj)
        with open(path, "w", encoding="utf-8", newline="\n") as f:
            f.write(text)
        return {"file": rel, "hash": "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()}

    model_entry = put("model.json", MODEL)
    for s in (S_LAND, S_BILLING, S_API, S_VIEW, S_VLAND):
        files[s["key"]] = put(f"scene/{s['key']}.json", s)
    put("index.json", {"schema": INDEX_SCHEMA, "modelHash": MH, "model": model_entry, "scenes": files})
    put("levels.json", levels([S_LAND, S_BILLING, S_API, S_VLAND, S_VIEW]))


def levels(scenes: list[dict[str, Any]]) -> dict[str, Any]:
    """The level graphs these scenes were laid out from (scene minus geometry; see levels.schema.json)."""
    out = []
    parent_of = {"e/billing": S_LAND, "e/billing/api": S_BILLING}
    for s in scenes:
        ports = []
        if s["key"] in parent_of:
            scope = s["level"]["scope"]
            for e in parent_of[s["key"]]["edges"]:
                if scope in (e["source"], e["target"]):
                    ports.append({"id": e["id"], "dir": "in" if e["target"] == scope else "out"})
        nodes = []
        for n in s["nodes"]:
            e = by_id.get(n["id"])
            lines = [dict(ln) for ln in n["label"]["lines"]]
            if e and e["description"] and n["role"] == "element":
                lines.append({"text": e["description"], "tier": 2, "size": 12})
            ln: dict[str, Any] = {k: n[k] for k in ("id", "modelId", "role", "type", "parent", "name", "tags",
                                                    "shape", "style") if k in n}
            ln["lines"] = lines
            if "frame" in n:
                ln["children"] = n["frame"]["children"]
                ln["childType"] = n["frame"]["childType"]
            nodes.append(ln)
        edges = [{k: e[k] for k in ("id", "source", "target", "rels", "style")} | {"lines": []} for e in s["edges"]]
        out.append({"key": s["key"], "level": s["level"], "title": s["title"],
                    "ports": sorted(ports, key=lambda p: p["id"]), "nodes": nodes, "edges": edges})
    return {"schema": "buildzr.levels/2", "modelHash": MH, "levels": out}


if __name__ == "__main__":
    main()
