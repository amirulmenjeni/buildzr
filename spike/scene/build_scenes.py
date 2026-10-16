"""Build ELK-laid-out scene graphs (buildzr.scene/1) from real DSL examples and a synthetic model.

Run:  uv run --project <worktree> python spike/scene/build_scenes.py [--only VIEW ...]
Writes spike/out/scenes/<view>.scene.json, index.json, and spike/scene/metrics.json
(metrics hold timings and are NOT deterministic; scenes are).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import random
import re
import runpy
import shutil
import statistics
import subprocess
import sys
import tempfile
import time
from typing import Any

HERE = os.path.dirname(os.path.abspath(__file__))
SPIKE = os.path.dirname(HERE)
ROOT = os.path.dirname(SPIKE)
sys.path.insert(0, os.path.join(SPIKE, "tools"))
import font_metrics as fm  # noqa: E402
from scene_io import dumps, rnd, sha256_of  # noqa: E402

ELK_RUN = os.path.join(SPIKE, "layout", "elk_run.mjs")
OUT_DIR = os.path.join(SPIKE, "out", "scenes")
TMP_BASE = os.path.join(tempfile.gettempdir(), "buildzr-spike")
ELK_VERSION = "0.12.0"
REPEAT = 5
LAYOUT_OVERRIDES: dict[str, str] = {}  # root ELK options replacing the defaults in build_elk (tuning)

ELEM_W = 240
PAD = 16
MIN_H = 120
MARGIN = 12
BOUNDARY_PAD = (24, 20, 48, 20)  # top, left, bottom, right; bottom holds a 2-line label

TYPE_TEXT = {
    "Person": "Person", "SoftwareSystem": "Software System", "Container": "Container",
    "Component": "Component", "DeploymentNode": "Deployment Node",
    "InfrastructureNode": "Infrastructure Node", "SoftwareSystemInstance": "Software System",
    "ContainerInstance": "Container", "Group": "Group",
}
TYPE_TAG = {
    "Person": "Person", "SoftwareSystem": "Software System", "Container": "Container",
    "Component": "Component", "DeploymentNode": "Deployment Node",
    "InfrastructureNode": "Infrastructure Node", "SoftwareSystemInstance": "Software System Instance",
    "ContainerInstance": "Container Instance", "Group": "Group",
}
DEFAULTS = {  # fill, color, shape
    "Person": ("#08427b", "#ffffff", "Person"),
    "SoftwareSystem": ("#1168bd", "#ffffff", "Box"),
    "Container": ("#438dd5", "#ffffff", "Box"),
    "Component": ("#85bbf0", "#000000", "Box"),
    "DeploymentNode": ("#ffffff", "#000000", "Box"),
    "InfrastructureNode": ("#dddddd", "#000000", "Box"),
    "SoftwareSystemInstance": ("#1168bd", "#ffffff", "Box"),
    "ContainerInstance": ("#438dd5", "#ffffff", "Box"),
    "Group": ("#ffffff", "#444444", "Box"),
}
SHAPES = {"Box", "RoundedBox", "Person", "Cylinder", "Pipe", "Folder", "Hexagon", "Circle", "Ellipse",
          "Component", "WebBrowser", "MobileDevicePortrait", "MobileDeviceLandscape", "Robot", "Diamond"}


def slug(name: str) -> str:
    return re.sub(r"[^a-z0-9._]+", "-", name.lower()).strip("-")  # '-' is added back by the sub


def color(c: str | None) -> str | None:
    if not c:
        return None
    c = c.strip().lower()
    if re.fullmatch(r"#[0-9a-f]{6}", c):
        return c
    if re.fullmatch(r"#[0-9a-f]{3}", c):
        return "#" + "".join(ch * 2 for ch in c[1:])
    return None


def luminance(c: str) -> float:
    def ch(v: int) -> float:
        v_ = v / 255
        return v_ / 12.92 if v_ <= 0.03928 else ((v_ + 0.055) / 1.055) ** 2.4
    r, g, b = (int(c[i:i + 2], 16) for i in (1, 3, 5))
    return 0.2126 * ch(r) + 0.7152 * ch(g) + 0.0722 * ch(b)


def contrast(a: str, b: str) -> float:
    la, lb = sorted((luminance(a), luminance(b)), reverse=True)
    return (la + 0.05) / (lb + 0.05)


def darken(c: str, f: float = 0.7) -> str:
    return "#" + "".join(f"{int(int(c[i:i + 2], 16) * f):02x}" for i in (1, 3, 5))


# ---------------------------------------------------------------- intermediate model


class N:
    """A scene node before layout."""

    def __init__(self, id_: str, model_id: str, type_: str, name: str, tags: list[str], parent: "str | None",
                 role: str = "element", tech: str = "", desc: str = "", style_tags: "list[str] | None" = None):
        self.id, self.model_id, self.type, self.name, self.tags = id_, model_id, type_, name, tags
        self.parent, self.role, self.tech, self.desc = parent, role, tech, desc
        self.style_tags = style_tags if style_tags is not None else tags
        self.x = self.y = self.w = self.h = 0.0
        self.style: dict[str, Any] = {}
        self.shape = "Box"
        self.lines: list[dict[str, Any]] = []
        self.anchor = "center"


class E:
    def __init__(self, model_id: str, src: str, dst: str, desc: str, tech: str, tags: list[str]):
        self.model_id, self.src, self.dst, self.desc, self.tech, self.tags = model_id, src, dst, desc, tech, tags
        self.id = ""


class ViewModel:
    def __init__(self, key: str, kind: str, title: str, description: str, direction: str,
                 nodes: list[N], edges: list[E], styles: dict[str, Any], model_hash: str):
        self.key, self.kind, self.title, self.description, self.direction = key, kind, title, description, direction
        self.nodes, self.edges, self.styles, self.model_hash = nodes, edges, styles, model_hash


# ---------------------------------------------------------------- Structurizr JSON -> ViewModel


def split_tags(s: str) -> list[str]:
    return [t for t in (s or "").split(",") if t]


def index_model(model: dict) -> tuple[dict[str, dict], dict[str, dict]]:
    """Return (elements by id, relationships by id). Works on Structurizr JSON only."""
    els: dict[str, dict] = {}
    rels: dict[str, dict] = {}

    def add(raw: dict, kind: str, parent: "str | None") -> dict:
        rec = {"raw": raw, "kind": kind, "parent": parent, "id": raw["id"]}
        els[raw["id"]] = rec
        for r in raw.get("relationships", []):
            rels[r["id"]] = r
        return rec

    for p in model.get("people", []):
        add(p, "Person", None)
    for s in model.get("softwareSystems", []):
        add(s, "SoftwareSystem", None)
        for c in s.get("containers", []):
            add(c, "Container", s["id"])
            for k in c.get("components", []):
                add(k, "Component", c["id"])

    def dn(node: dict, parent: "str | None") -> None:
        add(node, "DeploymentNode", parent)
        for i in node.get("infrastructureNodes", []):
            add(i, "InfrastructureNode", node["id"])
        for i in node.get("softwareSystemInstances", []):
            add(i, "SoftwareSystemInstance", node["id"])
        for i in node.get("containerInstances", []):
            add(i, "ContainerInstance", node["id"])
        for ch in node.get("children", []):
            dn(ch, node["id"])

    for d in model.get("deploymentNodes", []):
        dn(d, None)
    return els, rels


def element_facts(rec: dict, els: dict[str, dict]) -> tuple[str, str, str, list[str], list[str]]:
    """name, technology, description, tags, style_tags (underlying element tags first for instances)."""
    raw, kind = rec["raw"], rec["kind"]
    tags = split_tags(raw.get("tags", ""))
    if kind in ("ContainerInstance", "SoftwareSystemInstance"):
        under = els[raw["containerId" if kind == "ContainerInstance" else "softwareSystemId"]]["raw"]
        ut = split_tags(under.get("tags", ""))
        return (under["name"], under.get("technology", ""), under.get("description", ""), tags,
                ut + [t for t in tags if t not in ut])
    return raw["name"], raw.get("technology", ""), raw.get("description", ""), tags, tags


VIEW_KINDS = {
    "systemLandscapeViews": "systemLandscape", "systemContextViews": "systemContext",
    "containerViews": "container", "componentViews": "component", "deploymentViews": "deployment",
}


def build_view_model(ws: dict, key: str) -> ViewModel:
    model_hash = sha256_of(ws)  # dumps() sorts keys
    els, rels = index_model(ws["model"])
    view = kind = None
    for vk, k in VIEW_KINDS.items():
        for v in ws["views"].get(vk, []):
            if v["key"] == key:
                view, kind = v, k
    assert view is not None and kind is not None, key
    members = [e["id"] for e in view.get("elements", [])]
    mset = set(members)
    al = view.get("automaticLayout") or {}
    direction = "RIGHT" if al.get("rankDirection") == "LeftRight" else "DOWN"
    is_dep = kind == "deployment"

    used: set[str] = set()

    def uniq(base: str) -> str:
        c, i = base, 2
        while c in used:
            c, i = f"{base}-{i}", i + 1
        used.add(c)
        return c

    # nearest ancestor present in the view
    def view_parent(mid: str) -> "str | None":
        p = els[mid]["parent"]
        while p is not None and p not in mset:
            p = els[p]["parent"]
        return p

    focal = view.get("softwareSystemId") if kind == "container" else view.get("containerId") if kind == "component" else None
    vparent = {m: (view_parent(m) if is_dep else None) for m in members}
    if not is_dep and focal is not None:
        for m in members:
            if els[m]["parent"] == focal and focal not in mset:
                vparent[m] = focal
    boundary_model_ids = {p for p in vparent.values() if p is not None}

    order: list[str] = []  # model ids in model (view) order, extra focal first
    if focal is not None and focal in boundary_model_ids and focal not in mset:
        order.append(focal)
    order.extend(members)

    nodes: dict[str, N] = {}
    scene_id: dict[str, str] = {}
    env_root = slug(view.get("environment", "")) if is_dep else None

    def make_ids(mid: str) -> str:
        if mid in scene_id:
            return scene_id[mid]
        rec = els[mid]
        name = element_facts(rec, els)[0]
        pm = vparent.get(mid)
        if pm is not None:
            base = make_ids(pm) + "/" + slug(name)
        else:
            base = (env_root + "/" if env_root else "") + slug(name)
        scene_id[mid] = uniq(base)
        return scene_id[mid]

    for mid in order:
        make_ids(mid)
    for mid in order:
        rec = els[mid]
        name, tech, desc, tags, style_tags = element_facts(rec, els)
        sid = scene_id[mid]
        nodes[sid] = N(sid, mid, rec["kind"], name, tags, None, "boundary" if mid in boundary_model_ids else "element",
                       tech, desc, style_tags)
        if mid == focal and mid not in mset:
            pass
    for mid in order:
        pm = vparent.get(mid)
        nodes[scene_id[mid]].parent = scene_id[pm] if pm else None

    # groups -> boundaries (per scope), unless the group equals the scope parent's own group
    def group_of(mid: str) -> str:
        return els[mid]["raw"].get("group", "") or ""

    scopes: dict["str | None", list[str]] = {}
    for mid in order:
        scopes.setdefault(vparent.get(mid), []).append(mid)
    for pm, mids in scopes.items():
        parent_group = group_of(pm) if pm else ""
        gnodes: dict[str, N] = {}
        for mid in mids:
            g = group_of(mid)
            if not g or g == parent_group:
                continue
            psid = scene_id[pm] if pm else None
            if g not in gnodes:
                gid = uniq((psid + "/" if psid else "") + slug(g))
                gnodes[g] = N(gid, "group:" + g, "Group", g, ["Element", "Group"], psid, "boundary")
                nodes[gid] = gnodes[g]
            nodes[scene_id[mid]].parent = gnodes[g].id

    edges: list[E] = []
    for r in view.get("relationships", []):
        rel = rels[r["id"]]
        s, d = rel["sourceId"], rel["destinationId"]
        if s in scene_id and d in scene_id:
            edges.append(E(rel["id"], scene_id[s], scene_id[d], rel.get("description", ""),
                           rel.get("technology", ""), split_tags(rel.get("tags", ""))))
    styles = ws.get("views", {}).get("configuration", {}).get("styles", {})
    title = view.get("title") or view.get("description") or key
    return ViewModel(key, kind, title, view.get("description", ""), direction, list(nodes.values()), edges, styles, model_hash)


def run_example(path: str) -> dict:
    """Execute an example with cwd in a fresh temp dir (examples call save() at import time)."""
    os.makedirs(TMP_BASE, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=TMP_BASE)
    cwd = os.getcwd()
    try:
        os.chdir(tmp)
        g = runpy.run_path(path)
    finally:
        os.chdir(cwd)
        shutil.rmtree(tmp, ignore_errors=True)
    return json.loads(g["w"].to_json())


# ---------------------------------------------------------------- synthetic model


def synthetic_120(local: float = 0.7, key: str = "synthetic-120", dag: bool = False) -> ViewModel:
    """local: probability that an edge stays inside the source's top-level boundary (0 = old dense variant)."""
    rnd_ = random.Random(42)
    tagset = ["Database", "Queue", "External", "Billing", "Legacy", "Critical"]
    nodes: list[N] = []
    used: set[str] = set()
    counter = [0]

    def mk(name: str, type_: str, parent: "str | None", role: str, **kw: Any) -> N:
        counter[0] += 1
        base = (parent + "/" if parent else "") + slug(name)
        sid = base
        i = 2
        while sid in used:
            sid, i = f"{base}-{i}", i + 1
        used.add(sid)
        tags = ["Element", TYPE_TAG[type_], *rnd_.sample(tagset, rnd_.choice([1, 2]))]
        n = N(sid, str(counter[0]), type_, name, tags, parent, role, **kw)
        nodes.append(n)
        return n

    words = ["Auth", "Billing", "Catalog", "Search", "Orders", "Ledger", "Mailer", "Gateway", "Reports", "Users",
             "Inventory", "Pricing", "Payments", "Audit", "Cache", "Scheduler", "Notifier", "Exporter"]
    tops = [mk(f"Zone {c}", "Group", None, "boundary") for c in "ABCDEF"]            # 6 depth-1
    mids = [mk(f"{t.name} Cell {i}", "Group", t.id, "boundary") for t in tops for i in (1, 2)]  # 12 depth-2
    deeps = [mk(f"{m.name} Pod", "Group", m.id, "boundary") for m in mids[::2]]      # 6 depth-3
    bounds = tops + mids + deeps                                                      # 24 boundaries
    leaves: list[N] = []
    for i in range(96):
        b = rnd_.choice(bounds)
        w1, w2 = rnd_.sample(words, 2)
        desc = " ".join(rnd_.sample(["handles", "stores", "routes", "validates", "serves", "publishes", "consumes",
                                     "aggregates", "records", "schedules", "customer", "order", "payment", "event"],
                                    rnd_.choice([0, 3, 5, 8])))
        n = mk(f"{w1} {w2} {i}", "Container", b.id, "element", tech=rnd_.choice(["Java", "Python", "Go", "PostgreSQL", "Kafka", ""]),
               desc=desc)
        leaves.append(n)
    verbs = ["Reads from", "Writes to", "Calls", "Publishes events to", "Subscribes to", "Authenticates with",
             "Sends invoices to", "Syncs with"]
    pairs: set[tuple[str, str]] = set()
    edges: list[E] = []
    while len(edges) < 200:
        if local:
            a = rnd_.choice(leaves)
            same = rnd_.random() < local
            pool = [x for x in leaves if x is not a and (x.id.split("/")[0] == a.id.split("/")[0]) == same]
            b = rnd_.choice(pool)
        else:
            a, b = rnd_.sample(leaves, 2)
        if dag and leaves.index(a) > leaves.index(b):
            a, b = b, a  # orient low index -> high index: no cycles
        if (a.id, b.id) in pairs:
            continue
        pairs.add((a.id, b.id))
        edges.append(E(str(1000 + len(edges)), a.id, b.id, rnd_.choice(verbs), rnd_.choice(["", "", "HTTPS", "gRPC", "SQL"]),
                       ["Relationship"]))
    styles = {"elements": [
        {"tag": "Database", "shape": "Cylinder"}, {"tag": "Queue", "shape": "Pipe"},
        {"tag": "External", "background": "#999999"}, {"tag": "Legacy", "background": "#8a6d3b"},
        {"tag": "Critical", "stroke": "#c0392b"}, {"tag": "Billing", "color": "#ffeb3b"}],
        "relationships": [{"tag": "Relationship", "color": "#707070"}]}
    assert len(nodes) == 120, len(nodes)
    ws_like = {"nodes": [(n.id, n.parent, n.tags) for n in nodes], "edges": [(e.src, e.dst) for e in edges]}
    note = f"{int(local * 100)}% of edges inside one top-level boundary" if local else "edges between random leaves"
    return ViewModel(key, "synthetic", "Synthetic 120-node graph (seed 42)" + ("" if local else ", dense"),
                     f"Deterministic generated model: 24 boundaries (3 levels), 96 elements, 200 edges; {note}.", "DOWN",
                     nodes, edges, styles, sha256_of(ws_like))


# ---------------------------------------------------------------- styles, sizes, ELK


def resolve_styles(vm: ViewModel) -> None:
    el_styles = vm.styles.get("elements", [])
    rel_styles = vm.styles.get("relationships", [])
    for n in vm.nodes:
        fill, fg, shape = DEFAULTS[n.type]
        fg_explicit = fill_explicit = False
        type_fill = fill
        if n.role == "boundary":
            fill = "#ffffff"  # boundaries are unfilled unless a style sets a background
        stroke = None
        fs, opacity, bw, border = 13 if n.role == "boundary" else 14, None, None, None
        order = ["Element", TYPE_TAG[n.type]] + [t for t in n.style_tags if t not in ("Element", TYPE_TAG[n.type])]
        for t in order:
            for st in el_styles:
                if st.get("tag") != t:
                    continue
                if color(st.get("background")):
                    fill, fill_explicit = color(st.get("background")), True  # type: ignore[assignment]
                if color(st.get("color")):
                    fg, fg_explicit = color(st.get("color")), True  # type: ignore[assignment]
                stroke = color(st.get("stroke")) or stroke
                if st.get("shape") in SHAPES:
                    shape = st["shape"]
                if st.get("fontSize"):
                    fs = float(st["fontSize"])
                if st.get("opacity") is not None:
                    opacity = float(st["opacity"]) / 100
                if st.get("strokeWidth"):
                    bw = float(st["strokeWidth"])
                if st.get("border"):
                    border = st["border"].lower()
        if not fg_explicit:  # no style sets a text colour: black or white, whichever contrasts more with the fill
            fg = "#000000" if contrast("#000000", fill) >= contrast("#ffffff", fill) else "#ffffff"
        if n.role == "boundary":
            style: dict[str, Any] = {"fill": fill, "stroke": stroke or (type_fill if type_fill != "#ffffff" and not fill_explicit else "#888888"), "color": fg,
                                     "fontSize": rnd(fs), "dash": [6, 4]}
            shape = "Box"
        else:
            style = {"fill": fill, "stroke": stroke or darken(fill), "color": fg, "fontSize": rnd(fs)}
            if border == "dashed":
                style["dash"] = [6, 4]
            elif border == "dotted":
                style["dash"] = [2, 3]
        if opacity is not None:
            style["opacity"] = opacity
        if bw:
            style["strokeWidth"] = rnd(bw)
        n.style, n.shape = style, shape
    for e in vm.edges:
        st_: dict[str, Any] = {"stroke": "#707070", "arrow": "end", "dash": [5, 5]}
        for t in ["Relationship"] + [t for t in e.tags if t != "Relationship"]:
            for st in rel_styles:
                if st.get("tag") != t:
                    continue
                st_["stroke"] = color(st.get("color")) or st_["stroke"]
                if st.get("thickness"):
                    st_["width"] = rnd(float(st["thickness"]))
                if st.get("style") == "Solid" or st.get("dashed") is False:
                    st_.pop("dash", None)
                elif st.get("style") == "Dotted":
                    st_["dash"] = [2, 3]
                elif st.get("style") == "Dashed":
                    st_["dash"] = [5, 5]
                if st.get("fontSize"):
                    st_["fontSize"] = rnd(float(st["fontSize"]))
                if st.get("opacity") is not None:
                    st_["opacity"] = float(st["opacity"]) / 100
        e.style = st_  # type: ignore[attr-defined]


def size_and_label(vm: ViewModel) -> None:
    for n in vm.nodes:
        fs = n.style["fontSize"]
        tech = f": {n.tech}" if n.tech else ""
        type_line = f"[{TYPE_TEXT[n.type]}{tech}]"
        if n.role == "boundary":
            lines: list[dict[str, Any]] = [{"text": n.name, "weight": "bold"}]
            if n.type != "Group":
                lines.append({"text": type_line, "size": rnd(fs - 2)})
            n.lines, n.anchor = lines, "bottom-left"
            w = max(fm.measure(n.name, fs, "bold"), fm.measure(type_line, fs - 2)) + 40
            n.w, n.h = rnd(w), MIN_H  # minimum size only; ELK computes the real one
            continue
        inner = ELEM_W - 2 * PAD
        lines = [{"text": t, "weight": "bold"} for t in fm.wrap(n.name, fs, inner, "bold")]
        lines += [{"text": t, "size": rnd(fs - 2)} for t in fm.wrap(type_line, fs - 2, inner)]
        if n.desc:
            lines += [{"text": t, "size": rnd(fs - 2)} for t in fm.wrap(n.desc, fs - 2, inner)]
        h = 2 * PAD + sum((l.get("size", fs)) * fm.LINE_HEIGHT for l in lines)
        n.lines, n.anchor, n.w, n.h = lines, "center", ELEM_W, rnd(max(MIN_H, h))


def edge_label(e: E) -> tuple[list[dict[str, Any]], float, float]:
    fs = e.style.get("fontSize", 12)  # type: ignore[attr-defined]
    lines: list[dict[str, Any]] = []
    for t in fm.wrap(e.desc, fs, 200):
        lines.append({"text": t, "size": rnd(fs)})
    if e.tech:
        lines.append({"text": f"[{e.tech}]", "size": rnd(fs - 1)})
    if not lines:
        return [], 0, 0
    w = max(fm.measure(l["text"], l["size"]) for l in lines) + 8
    h = sum(l["size"] * fm.LINE_HEIGHT for l in lines) + 4
    return lines, rnd(w), rnd(h)


def assign_edge_ids(vm: ViewModel) -> None:
    from collections import Counter
    cnt = Counter((e.src, e.dst) for e in vm.edges)
    seen: set[str] = set()
    for e in vm.edges:
        eid = f"{e.src}->{e.dst}"
        if cnt[(e.src, e.dst)] > 1:
            eid += ":" + slug(e.desc)
        c, i = eid, 2
        while c in seen:
            c, i = f"{eid}-{i}", i + 1
        seen.add(c)
        e.id = c


def build_elk(vm: ViewModel) -> tuple[dict, dict[str, tuple[list[dict], float, float]]]:
    kids: dict["str | None", list[N]] = {}
    for n in vm.nodes:
        kids.setdefault(n.parent, []).append(n)
    t, l, b, r = BOUNDARY_PAD

    def conv(n: N) -> dict:
        d: dict[str, Any] = {"id": n.id}
        if n.role == "boundary":
            d["layoutOptions"] = {
                "elk.padding": f"[top={t},left={l},bottom={b},right={r}]",
                "elk.nodeSize.constraints": "MINIMUM_SIZE",
                "elk.nodeSize.minimum": f"({n.w},{n.h})",
            }
            d["children"] = [conv(c) for c in kids.get(n.id, [])]
        else:
            d["width"], d["height"] = n.w, n.h
        return d

    opts = {
        "elk.algorithm": "layered",
        "elk.hierarchyHandling": "INCLUDE_CHILDREN",
        "elk.edgeRouting": "ORTHOGONAL",
        "elk.direction": vm.direction,
        "elk.spacing.nodeNode": "25",
        "elk.layered.spacing.nodeNodeBetweenLayers": "40",
        "elk.spacing.edgeNode": "10",
        "elk.layered.spacing.edgeNodeBetweenLayers": "10",
        "elk.spacing.edgeEdge": "10",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "10",
        "elk.spacing.edgeLabel": "4",
        "elk.layered.considerModelOrder.strategy": "NONE",
        "elk.padding": f"[top={MARGIN},left={MARGIN},bottom={MARGIN},right={MARGIN}]",
        "org.eclipse.elk.json.edgeCoords": "ROOT",
        "org.eclipse.elk.json.shapeCoords": "ROOT",
    }
    opts.update(LAYOUT_OVERRIDES)
    labels: dict[str, tuple[list[dict], float, float]] = {}
    edges = []
    for e in vm.edges:
        lines, w, h = edge_label(e)
        labels[e.id] = (lines, w, h)
        ed: dict[str, Any] = {"id": e.id, "sources": [e.src], "targets": [e.dst]}
        if lines:
            ed["labels"] = [{"id": e.id + "#label", "text": " ".join(x["text"] for x in lines), "width": w, "height": h}]
        edges.append(ed)
    graph = {"id": "root", "layoutOptions": opts, "children": [conv(n) for n in kids.get(None, [])], "edges": edges}
    return graph, labels


def run_elk(graph: dict) -> tuple[dict, dict[str, float]]:
    os.makedirs(TMP_BASE, exist_ok=True)
    tmp = tempfile.mkdtemp(dir=TMP_BASE)
    try:
        inp, outp = os.path.join(tmp, "in.json"), os.path.join(tmp, "out.json")
        with open(inp, "w", encoding="utf-8") as f:
            f.write(dumps(graph))
        t0 = time.perf_counter()
        p1 = subprocess.run(["node", ELK_RUN, inp, outp], capture_output=True, text=True, check=True)
        wall = (time.perf_counter() - t0) * 1000
        p2 = subprocess.run(["node", ELK_RUN, inp, outp, "--repeat", str(REPEAT)], capture_output=True, text=True, check=True)
        out = json.load(open(outp, encoding="utf-8"))
        first = float(re.search(r"elk_ms=([\d.]+)", p1.stderr).group(1))  # type: ignore[union-attr]
        med = float(re.search(r"elk_ms=([\d.]+)", p2.stderr).group(1))  # type: ignore[union-attr]
        return out, {"node_wall_ms": round(wall, 1), "elk_single_ms": first, "elk_median5_ms": med}
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


# ---------------------------------------------------------------- scene emit and checks


def emit_scene(vm: ViewModel, elk_in: dict, elk_out: dict, labels: dict) -> tuple[dict, dict]:
    by_id = {n.id: n for n in vm.nodes}

    def walk(c: dict) -> None:
        for ch in c.get("children", []):
            n = by_id[ch["id"]]
            n.x, n.y = ch["x"], ch["y"]
            if n.role == "boundary":
                n.w, n.h = ch["width"], ch["height"]
            walk(ch)

    walk(elk_out)
    edge_res = {e["id"]: e for e in elk_out.get("edges", [])}
    pts: dict[str, list[list[float]]] = {}
    lab: dict[str, tuple[float, float]] = {}
    for e in vm.edges:
        er = edge_res[e.id]
        sec = er["sections"][0]
        p = [[sec["startPoint"]["x"], sec["startPoint"]["y"]]]
        p += [[b["x"], b["y"]] for b in sec.get("bendPoints", [])]
        p.append([sec["endPoint"]["x"], sec["endPoint"]["y"]])
        pts[e.id] = p
        if er.get("labels"):
            lab[e.id] = (er["labels"][0]["x"], er["labels"][0]["y"])

    # bounds incl. labels, shifted so the margin box starts at 0,0
    xs, ys = [], []
    for n in vm.nodes:
        xs += [n.x, n.x + n.w]
        ys += [n.y, n.y + n.h]
    for e in vm.edges:
        for x, y in pts[e.id]:
            xs.append(x)
            ys.append(y)
        if e.id in lab:
            lx, ly = lab[e.id]
            _, w, h = labels[e.id]
            xs += [lx, lx + w]
            ys += [ly, ly + h]
    dx, dy = MARGIN - min(xs), MARGIN - min(ys)
    bounds = [0, 0, rnd(max(xs) - min(xs) + 2 * MARGIN), rnd(max(ys) - min(ys) + 2 * MARGIN)]

    kids: dict["str | None", list[N]] = {}
    for n in vm.nodes:
        kids.setdefault(n.parent, []).append(n)
    ordered: list[N] = []

    def pre(parent: "str | None") -> None:
        for n in sorted(kids.get(parent, []), key=lambda k: k.id):
            ordered.append(n)
            pre(n.id)

    pre(None)
    nodes_out = []
    for n in ordered:
        d: dict[str, Any] = {
            "id": n.id, "modelId": n.model_id, "role": n.role, "type": n.type, "parent": n.parent,
            "x": rnd(n.x + dx), "y": rnd(n.y + dy), "w": rnd(n.w), "h": rnd(n.h), "shape": n.shape,
            "style": n.style, "label": {"lines": n.lines, "anchor": n.anchor}, "tags": n.tags, "name": n.name,
        }
        if n.tech:
            d["technology"] = n.tech
        if n.desc:
            d["description"] = n.desc
        if n.role == "element":
            d["lod"] = {"detail": ["name", "type", "description"]}
        nodes_out.append(d)
    edges_out = []
    for e in sorted(vm.edges, key=lambda k: k.id):
        d = {"id": e.id, "modelId": e.model_id, "source": e.src, "target": e.dst,
             "points": [[rnd(x + dx), rnd(y + dy)] for x, y in pts[e.id]], "style": e.style,  # type: ignore[attr-defined]
             "tags": e.tags, "order": None}
        if e.id in lab:
            lines, w, h = labels[e.id]
            d["label"] = {"lines": lines, "x": rnd(lab[e.id][0] + dx), "y": rnd(lab[e.id][1] + dy), "w": w, "h": h}
        if e.desc:
            d["description"] = e.desc
        if e.tech:
            d["technology"] = e.tech
        edges_out.append(d)
    opts = elk_in["layoutOptions"]
    scene = {
        "schema": "buildzr.scene/1", "view": vm.key, "kind": vm.kind, "title": vm.title,
        "modelHash": vm.model_hash,
        "layout": {"engine": "elkjs", "version": ELK_VERSION, "inputHash": sha256_of(elk_in), "direction": vm.direction,
                   "options": {k: v for k, v in opts.items() if not k.startswith("org.eclipse.elk.json")}},
        "bounds": bounds, "nodes": nodes_out, "edges": edges_out,
    }
    if vm.description:
        scene["description"] = vm.description
    return scene, {}


def geometry_report(scene: dict) -> dict[str, Any]:
    nodes = {n["id"]: n for n in scene["nodes"]}

    def border_gap(p: list[float], n: dict) -> float:
        x0, y0, x1, y1 = n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]
        px, py = p
        if x0 <= px <= x1 and y0 <= py <= y1:
            return min(px - x0, x1 - px, py - y0, y1 - py)
        cx, cy = min(max(px, x0), x1), min(max(py, y0), y1)
        return ((px - cx) ** 2 + (py - cy) ** 2) ** 0.5

    gaps = []
    for e in scene["edges"]:
        gaps.append(border_gap(e["points"][0], nodes[e["source"]]))
        gaps.append(border_gap(e["points"][-1], nodes[e["target"]]))
    sib: dict[Any, list[dict]] = {}
    for n in scene["nodes"]:
        sib.setdefault(n["parent"], []).append(n)

    def inter(a: dict, b: dict) -> bool:
        return a["x"] < b["x"] + b["w"] and b["x"] < a["x"] + a["w"] and a["y"] < b["y"] + b["h"] and b["y"] < a["y"] + a["h"]

    overlaps = sum(inter(a, b) for g in sib.values() for i, a in enumerate(g) for b in g[i + 1:])
    leaf = [n for n in scene["nodes"] if n["role"] == "element"]
    labels = [(e["id"], e["label"]) for e in scene["edges"] if "label" in e]
    lab_node = sum(1 for _, lb in labels for n in leaf if inter(lb, n))
    lab_lab = sum(1 for i, (_, a) in enumerate(labels) for _, b in labels[i + 1:] if inter(a, b))
    low_contrast = sum(1 for n in scene["nodes"] if contrast(n["style"]["color"], n["style"]["fill"]) < 4.5)
    return {"low_contrast_nodes": low_contrast, "max_endpoint_gap_px": round(max(gaps), 3) if gaps else 0, "sibling_overlaps": overlaps,
            "edge_labels_overlapping_elements": lab_node, "edge_label_pairs_overlapping": lab_lab,
            "size_px": [scene["bounds"][2], scene["bounds"][3]], "nodes": len(scene["nodes"]), "edges": len(scene["edges"])}


def build(vm: ViewModel) -> tuple[dict, dict]:
    resolve_styles(vm)
    size_and_label(vm)
    assign_edge_ids(vm)
    elk_in, labels = build_elk(vm)
    t0 = time.perf_counter()
    elk_out, timing = run_elk(elk_in)
    scene, _ = emit_scene(vm, elk_in, elk_out, labels)
    rep = geometry_report(scene)
    rep.update(timing)
    return scene, rep


SOURCES = [
    ("examples/amazon_web_services.py", ["aws-deployment-view", "x_context_00"]),
    ("examples/system_context_and_container_view.py", ["web_app_container_view_00", "web_app_system_context_00"]),
]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", nargs="*")
    args = ap.parse_args()
    t_start = time.perf_counter()
    os.makedirs(OUT_DIR, exist_ok=True)
    index, metrics = [], {}
    jobs: list[tuple[str, Any]] = []
    for rel, keys in SOURCES:
        ws = None
        for k in keys:
            if args.only and k not in args.only:
                continue
            ws = ws or run_example(os.path.join(ROOT, rel))
            jobs.append((k, (lambda ws=ws, k=k: build_view_model(ws, k))))
    if not args.only or "synthetic-120" in args.only:
        jobs.append(("synthetic-120", synthetic_120))
    if not args.only or "synthetic-120-dense" in args.only:
        jobs.append(("synthetic-120-dense", lambda: synthetic_120(0, "synthetic-120-dense")))
    for key, mk in jobs:
        vm = mk()
        scene, rep = build(vm)
        fn = f"{key}.scene.json"
        with open(os.path.join(OUT_DIR, fn), "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps(scene))
        index.append({"view": key, "title": vm.title, "kind": vm.kind, "file": fn})
        metrics[key] = rep
        print(key, json.dumps(rep))
    if not args.only:
        index.sort(key=lambda d: d["view"])
        with open(os.path.join(OUT_DIR, "index.json"), "w", encoding="utf-8", newline="\n") as f:
            f.write(dumps(index))
    metrics["_total_build_wall_s"] = round(time.perf_counter() - t_start, 2)
    with open(os.path.join(HERE, "metrics.json"), "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=1, sort_keys=True)
    print("total wall s", metrics["_total_build_wall_s"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
