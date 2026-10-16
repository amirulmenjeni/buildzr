"""Check model.json, index.json and scene files against the v4 contract.

The JSON schemas in ``buildzr/site/schema/`` cover shapes; this module checks
what they cannot: canonical bytes, containment, pre-order, rollup counts,
frames and port continuity across levels (design note v4, sections C and I).

Usage::

    python -m buildzr.site.check DATA_DIR        # dir holding index.json
    python -m buildzr.site.check --json DATA_DIR # also print the metrics as JSON

Exit status 0 when there are no errors. :func:`check_site` returns a
:class:`Report` whose ``metrics`` the acceptance tests assert on.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import sys
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

from buildzr.site.canonical import INDEX_SCHEMA, MODEL_SCHEMA, SCENE_SCHEMA, dumps, model_hash

SCHEMA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "schema")
EPS = 0.5  # containment / border tolerance, px
PORT_EPS = 1.5  # port continuity tolerance, px (design I, stage 1)

Json = dict[str, Any]


@dataclass
class Report:
    """Errors found plus the numbers the acceptance criteria quote."""

    errors: list[str] = field(default_factory=list)
    metrics: dict[str, Any] = field(default_factory=dict)

    def err(self, where: str, msg: str) -> None:
        self.errors.append(f"{where}: {msg}")

    @property
    def ok(self) -> bool:
        return not self.errors


# --- helpers -------------------------------------------------------------------


def _schema_errors(obj: Any, schema_file: str) -> list[str]:
    try:
        import jsonschema  # type: ignore[import-untyped]
    except ImportError:  # pragma: no cover - jsonschema is a dev dependency
        return []
    with open(os.path.join(SCHEMA_DIR, schema_file), encoding="utf-8") as f:
        schema = json.load(f)
    return [f"schema {list(e.absolute_path)}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(obj)]


def _rounded(v: float) -> bool:
    return abs(v * 100 - round(v * 100)) < 1e-6


def _load(path: str, rep: Report, where: str) -> Optional[Any]:
    try:
        with open(path, encoding="utf-8") as f:
            raw = f.read()
    except OSError as e:
        rep.err(where, f"cannot read {path}: {e}")
        return None
    obj = json.loads(raw)
    if raw != dumps(obj):
        rep.err(where, "bytes are not canonical (sort_keys, compact separators, trailing newline)")
    return obj


def _seg_hits_rect(p: list[float], q: list[float], r: tuple[float, float, float, float]) -> bool:
    """True if segment p-q passes through the interior of rect r (shrunk by 1 px)."""
    x0, y0, x1, y1 = r[0] + 1, r[1] + 1, r[0] + r[2] - 1, r[1] + r[3] - 1
    if x0 >= x1 or y0 >= y1:
        return False
    # Liang-Barsky clipping
    dx, dy = q[0] - p[0], q[1] - p[1]
    t0, t1 = 0.0, 1.0
    for pp, qq in ((-dx, p[0] - x0), (dx, x1 - p[0]), (-dy, p[1] - y0), (dy, y1 - p[1])):
        if pp == 0:
            if qq < 0:
                return False
        else:
            t = qq / pp
            if pp < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
            if t0 > t1:
                return False
    return t1 - t0 > 1e-9


def _dist_to_border(pt: list[float], n: Json) -> float:
    x, y = pt
    x0, y0, x1, y1 = n["x"], n["y"], n["x"] + n["w"], n["y"] + n["h"]
    inside = x0 <= x <= x1 and y0 <= y <= y1
    if inside:
        return float(min(x - x0, x1 - x, y - y0, y1 - y))
    dx = max(x0 - x, 0, x - x1)
    dy = max(y0 - y, 0, y - y1)
    return float(math.hypot(dx, dy))


# --- model ---------------------------------------------------------------------


class ModelIndex:
    """Lookups over a buildzr.model/2 object."""

    def __init__(self, model: Json) -> None:
        self.model = model
        self.el = {e["id"]: e for e in model["elements"]}
        self.rel = {r["id"]: r for r in model["relationships"]}
        self.roots = [e["id"] for e in model["elements"] if e["parent"] is None]

    def ancestors_or_self(self, path: str) -> list[str]:
        out = []
        cur: Optional[str] = path
        while cur is not None:
            out.append(cur)
            cur = self.el[cur]["parent"] if cur in self.el else None
        return out

    def in_subtree(self, path: str, root: str) -> bool:
        return root in self.ancestors_or_self(path)

    def rollup(self, a: str, b: str) -> list[str]:
        """Ids of explicit relationships from subtree(a) to subtree(b), sorted."""
        return sorted(r["id"] for r in self.model["relationships"]
                      if self.in_subtree(r["source"], a) and self.in_subtree(r["destination"], b))


def check_model(model: Json, rep: Report, where: str = "model.json") -> None:
    """Check a model.json object (already loaded)."""
    for e in _schema_errors(model, "model.schema.json"):
        rep.err(where, e)
    if model.get("schema") != MODEL_SCHEMA:
        return
    if model["modelHash"] != model_hash(model):
        rep.err(where, f"modelHash {model['modelHash']} != computed {model_hash(model)}")
    seen: dict[str, Json] = {}
    for e in model["elements"]:
        if e["id"] in seen:
            rep.err(where, f"duplicate element id {e['id']}")
        p = e["parent"]
        if p is not None:
            if p not in seen:
                rep.err(where, f"element {e['id']}: parent {p} missing or after child (pre-order)")
            elif e["id"] not in seen[p]["children"]:
                rep.err(where, f"element {e['id']} not in children of {p}")
            if not e["id"].startswith(p + "/"):
                rep.err(where, f"element {e['id']}: path does not extend parent path {p}")
        elif "/" in e["id"]:
            rep.err(where, f"root element {e['id']} has a nested path")
        seen[e["id"]] = e
    for e in model["elements"]:
        for c in e["children"]:
            if c not in seen or seen[c]["parent"] != e["id"]:
                rep.err(where, f"element {e['id']}: child {c} missing or with another parent")
    views = {v["key"] for v in model["views"]}
    if len(views) != len(model["views"]):
        rep.err(where, "duplicate view key")
    for e in model["elements"]:
        for v in e["views"]:
            if v not in views:
                rep.err(where, f"element {e['id']}: unknown view {v}")
    ids = [r["id"] for r in model["relationships"]]
    if ids != sorted(ids):
        rep.err(where, "relationships not sorted by id")
    if len(set(ids)) != len(ids):
        rep.err(where, "duplicate relationship id")
    for r in model["relationships"]:
        for end in ("source", "destination"):
            if r[end] not in seen:
                rep.err(where, f"relationship {r['id']}: {end} {r[end]} not an element")
    rep.metrics.setdefault("model", {}).update(
        elements=len(model["elements"]), relationships=len(ids), views=len(views))


# --- one scene -----------------------------------------------------------------


def check_scene(scene: Json, rep: Report, mi: Optional[ModelIndex] = None) -> dict[str, Any]:
    """Check one scene on its own (plus rollups against the model if given). Returns metrics."""
    where = f"scene {scene.get('key', '?')}"
    m: dict[str, Any] = {"nodes": 0, "edges": 0, "bad_edges": 0, "edge_end_gap_px": 0.0}
    for e in _schema_errors(scene, "scene.schema.json"):
        rep.err(where, e)
    if scene.get("schema") != SCENE_SCHEMA:
        return m
    kind = scene["level"]["kind"]
    bx, by, bw, bh = scene["bounds"]
    if kind == "element":
        if bx != 0 or by != 0:
            rep.err(where, "element scene bounds must start at (0, 0)")
        if scene["key"] != f"e/{scene['level']['scope']}":
            rep.err(where, f"key {scene['key']} does not match scope {scene['level']['scope']}")
    elif scene["ports"]:
        rep.err(where, "ports are only allowed in element scenes")
    by_id: dict[str, Json] = {}
    last_sibling: dict[Any, str] = {}
    for n in scene["nodes"]:
        nid = n["id"]
        if nid in by_id:
            rep.err(where, f"duplicate node id {nid}")
        p = n["parent"]
        if p is not None:
            if p not in by_id:
                rep.err(where, f"node {nid}: parent {p} missing or after child (pre-order)")
            else:
                pn = by_id[p]
                if pn["role"] != "boundary":
                    rep.err(where, f"node {nid}: parent {p} is not a boundary")
                if not (n["x"] >= pn["x"] - EPS and n["y"] >= pn["y"] - EPS
                        and n["x"] + n["w"] <= pn["x"] + pn["w"] + EPS
                        and n["y"] + n["h"] <= pn["y"] + pn["h"] + EPS):
                    rep.err(where, f"node {nid} not inside parent {p}")
        if not (n["x"] >= bx - EPS and n["y"] >= by - EPS and n["x"] + n["w"] <= bx + bw + EPS
                and n["y"] + n["h"] <= by + bh + EPS):
            rep.err(where, f"node {nid} outside scene bounds")
        for k in ("x", "y", "w", "h"):
            if not _rounded(n[k]):
                rep.err(where, f"node {nid}.{k}={n[k]} not rounded to 0.01")
        prev = last_sibling.get(p)
        if prev is not None and prev > nid:
            rep.err(where, f"siblings under {p} not sorted: {prev} before {nid}")
        last_sibling[p] = nid
        if "frame" in n and n["role"] != "element":
            rep.err(where, f"node {nid}: only element nodes carry a frame")
        if "frame" in n and kind == "view":
            rep.err(where, f"node {nid}: authored views have no frames")
        by_id[nid] = n
    m["nodes"] = len(by_id)

    ports = {p["id"]: p for p in scene["ports"]}
    if [p["id"] for p in scene["ports"]] != sorted(ports):
        rep.err(where, "ports not sorted by id / duplicate port")
    for p in scene["ports"]:
        want = {"N": abs(p["y"] - by), "S": abs(p["y"] - by - bh), "W": abs(p["x"] - bx), "E": abs(p["x"] - bx - bw)}
        if want[p["side"]] > EPS:
            rep.err(where, f"port {p['id']} not on its side {p['side']} (off by {want[p['side']]:.2f})")

    ids = [e["id"] for e in scene["edges"]]
    if ids != sorted(ids):
        rep.err(where, "edges not sorted by id")
    if len(set(ids)) != len(ids):
        rep.err(where, "duplicate edge id")

    def anc(nid: str) -> set[str]:
        out = set()
        cur: Optional[str] = nid
        while cur is not None and cur in by_id:
            out.add(cur)
            cur = by_id[cur]["parent"]
        return out

    for e in scene["edges"]:
        ew = f"{where} edge {e['id']}"
        ends: list[Optional[str]] = []
        for end_key, pt in (("source", e["points"][0]), ("target", e["points"][-1])):
            end = e[end_key]
            if isinstance(end, dict):
                pid = end["port"]
                ends.append(None)
                if pid not in ports:
                    rep.err(ew, f"{end_key} port {pid} not in ports")
                else:
                    gap = math.hypot(pt[0] - ports[pid]["x"], pt[1] - ports[pid]["y"])
                    m["edge_end_gap_px"] = max(m["edge_end_gap_px"], gap)
                    if gap > PORT_EPS:
                        rep.err(ew, f"{end_key} point {pt} is {gap:.2f} px from port {pid}")
            else:
                ends.append(end)
                if end not in by_id:
                    rep.err(ew, f"{end_key} {end} not a node")
                else:
                    gap = _dist_to_border(pt, by_id[end])
                    m["edge_end_gap_px"] = max(m["edge_end_gap_px"], gap)
                    if gap > PORT_EPS:
                        rep.err(ew, f"{end_key} point {pt} is {gap:.2f} px from the border of {end}")
        for pt in e["points"]:
            if not all(_rounded(c) for c in pt):
                rep.err(ew, f"point {pt} not rounded")
            if not (bx - EPS <= pt[0] <= bx + bw + EPS and by - EPS <= pt[1] <= by + bh + EPS):
                rep.err(ew, f"point {pt} outside bounds")
        if e["count"] != len(e["rels"]) or e["rels"] != sorted(set(e["rels"])):
            rep.err(ew, "count != len(rels) or rels not sorted/unique")
        related: set[str] = set()
        for end_id in ends:
            if end_id is not None:
                related |= anc(end_id)
        hit = False
        for n in scene["nodes"]:
            if n["id"] in related:
                continue
            # Edges may cross boundaries (groups, view boundaries) whose children they connect.
            if n["role"] == "boundary" and any(n["id"] in anc(x) for x in ends if x):
                continue
            r = (n["x"], n["y"], n["w"], n["h"])
            if any(_seg_hits_rect(p, q, r) for p, q in zip(e["points"], e["points"][1:])):
                hit = True
                rep.err(ew, f"passes through unrelated node {n['id']}")
                break
        m["bad_edges"] += hit
        if mi is not None:
            for rid in e["rels"]:
                if rid not in mi.rel:
                    rep.err(ew, f"rel {rid} not in model.json")
            src, dst = ends
            if src is not None and dst is not None and src in mi.el and dst in mi.el and kind != "view":
                expected = mi.rollup(src, dst)
                if e["rels"] != expected:
                    rep.err(ew, f"rels {e['rels']} != rollup {expected}")
    m["edges"] = len(scene["edges"])

    if mi is not None and kind in ("landscape", "element"):
        if kind == "landscape":
            expect = set(mi.roots)
        else:
            scope = scene["level"]["scope"]
            expect = set(mi.el[scope]["children"]) if scope in mi.el else set()
            if scope not in mi.el:
                rep.err(where, f"scope {scope} not an element")
        known = {"Person", "SoftwareSystem", "Container", "Component"}
        expect = {x for x in expect if mi.el[x]["type"] in known}
        got = {n["id"] for n in scene["nodes"] if n["role"] == "element"}
        if got != expect:
            rep.err(where, f"element nodes {sorted(got ^ expect)} differ from the model level")
        for n in scene["nodes"]:
            if n["role"] != "element" or n["id"] not in mi.el:
                continue
            kids = mi.el[n["id"]]["children"]
            if bool(kids) != ("frame" in n):
                rep.err(where, f"node {n['id']}: frame present={'frame' in n} but model children={len(kids)}")
            elif kids and n["frame"]["children"] != len(kids):
                rep.err(where, f"node {n['id']}: frame.children {n['frame']['children']} != {len(kids)}")
        # every explicit relationship between two different nodes of this level is drawn
        level_nodes = sorted(got)
        drawn = {(e["source"], e["target"]) for e in scene["edges"]
                 if isinstance(e["source"], str) and isinstance(e["target"], str)}
        for a in level_nodes:
            for b in level_nodes:
                if a != b and (a, b) not in drawn and mi.rollup(a, b):
                    rep.err(where, f"missing rolled-up edge {a}->{b} ({len(mi.rollup(a, b))} rels)")
    return m


# --- across scenes -------------------------------------------------------------


def _endpoint_point(edge: Json, node_id: str) -> tuple[Optional[str], list[float]]:
    """Which end of a parent edge touches node_id, and its point."""
    if edge["target"] == node_id:
        return "target", edge["points"][-1]
    if edge["source"] == node_id:
        return "source", edge["points"][0]
    return None, edge["points"][0]


def check_frames(scenes: dict[str, Json], rep: Report, mi: Optional[ModelIndex]) -> dict[str, Any]:
    """Frames and ports: child scene placement, port sets, continuity, rels conservation."""
    m: dict[str, Any] = {"frames": 0, "ports": 0, "port_gap_px": 0.0, "port_sides_kept": 0}
    for key, parent in scenes.items():
        for n in parent["nodes"]:
            fr = n.get("frame")
            if not fr:
                continue
            m["frames"] += 1
            where = f"scene {key} frame {n['id']}"
            child = scenes.get(fr["scene"])
            if child is None:
                rep.err(where, f"child scene {fr['scene']} missing")
                continue
            if child["level"]["scope"] != n["id"]:
                rep.err(where, f"child scene scope {child['level']['scope']} != {n['id']}")
            s = fr["scale"]
            cbx, cby, cbw, cbh = child["bounds"]
            if abs(n["w"] - s * cbw) > EPS or abs(n["h"] - s * cbh) > EPS:
                rep.err(where, f"frame {n['w']}x{n['h']} != scale {s} x child bounds {cbw}x{cbh}")
            incident = {e["id"]: e for e in parent["edges"] if n["id"] in (e["source"], e["target"])}
            cports = {p["id"]: p for p in child["ports"]}
            if set(incident) != set(cports):
                rep.err(where, f"child ports {sorted(cports)} != parent edges at the frame {sorted(incident)}")
            for pid, p in cports.items():
                pe = incident.get(pid)
                if pe is None:
                    continue
                m["ports"] += 1
                end, ppt = _endpoint_point(pe, n["id"])
                gx, gy = n["x"] + s * (p["x"] - cbx), n["y"] + s * (p["y"] - cby)
                gap = math.hypot(gx - ppt[0], gy - ppt[1])
                m["port_gap_px"] = max(m["port_gap_px"], gap)
                if gap > PORT_EPS:
                    rep.err(where, f"port {pid}: child port maps to ({gx:.2f}, {gy:.2f}), parent edge ends at {ppt}, gap {gap:.2f} px")
                # side as seen in the parent
                side_d = {"N": abs(ppt[1] - n["y"]), "S": abs(ppt[1] - n["y"] - n["h"]),
                          "W": abs(ppt[0] - n["x"]), "E": abs(ppt[0] - n["x"] - n["w"])}
                if side_d[p["side"]] <= PORT_EPS:
                    m["port_sides_kept"] += 1
                else:
                    rep.err(where, f"port {pid}: side {p['side']} but the parent edge meets another side")
                # direction and rels conservation
                users = [ce for ce in child["edges"]
                         if {"port": pid} in (ce["source"], ce["target"])]
                inner_rels: list[str] = []
                for ce in users:
                    want_key = "source" if end == "target" else "target"
                    if ce[want_key] != {"port": pid}:
                        rep.err(where, f"child edge {ce['id']} uses port {pid} against the parent edge's direction")
                    inner_rels += ce["rels"]
                if len(inner_rels) != len(set(inner_rels)):
                    rep.err(where, f"port {pid}: a relationship continues through two child edges")
                extra = set(inner_rels) - set(pe["rels"])
                if extra:
                    rep.err(where, f"port {pid}: child rels {sorted(extra)} not in parent edge")
                if mi is not None:
                    # every parent rel whose inner end lies strictly below the frame element continues
                    for rid in pe["rels"]:
                        r = mi.rel.get(rid)
                        if r is None:
                            continue
                        inner_end = r["destination"] if end == "target" else r["source"]
                        if inner_end != n["id"] and rid not in inner_rels:
                            rep.err(where, f"port {pid}: rel {rid} does not continue inside")
    return m


def check_site(data_dir: str) -> Report:
    """Check index.json, model.json and every scene under ``data_dir``."""
    rep = Report()
    index = _load(os.path.join(data_dir, "index.json"), rep, "index.json")
    if index is None:
        return rep
    for e in _schema_errors(index, "index.schema.json"):
        rep.err("index.json", e)
    if index.get("schema") != INDEX_SCHEMA:
        return rep

    def load_entry(entry: Json, where: str) -> Optional[Any]:
        path = os.path.join(data_dir, entry["file"])
        if os.path.exists(path):
            with open(path, "rb") as f:
                h = "sha256:" + hashlib.sha256(f.read()).hexdigest()
            if h != entry["hash"]:
                rep.err(where, f"hash {entry['hash']} != file bytes {h}")
        return _load(path, rep, where)

    model = load_entry(index["model"], "model.json")
    mi = None
    if model is not None:
        check_model(model, rep)
        mi = ModelIndex(model)
        if index["modelHash"] != model.get("modelHash"):
            rep.err("index.json", "modelHash differs from model.json")
    scenes: dict[str, Json] = {}
    for key, entry in sorted(index["scenes"].items()):
        s = load_entry(entry, f"scene {key}")
        if s is not None:
            if s.get("key") != key:
                rep.err(f"scene {key}", f"file declares key {s.get('key')}")
            scenes[key] = s
    totals: dict[str, Any] = {"scenes": len(scenes), "nodes": 0, "edges": 0, "bad_edges": 0, "edge_end_gap_px": 0.0}
    for key, s in scenes.items():
        sm = check_scene(s, rep, mi)
        for k in ("nodes", "edges", "bad_edges"):
            totals[k] += sm[k]
        totals["edge_end_gap_px"] = max(totals["edge_end_gap_px"], sm["edge_end_gap_px"])
        if model is not None and s.get("modelHash") != model.get("modelHash"):
            rep.err(f"scene {key}", "modelHash differs from model.json")
    if model is not None:
        for v in model["views"]:
            if v["scene"] not in index["scenes"]:
                rep.err("index.json", f"view {v['key']}: scene {v['scene']} missing")
        if "landscape" not in index["scenes"]:
            rep.err("index.json", "no landscape scene")
    totals.update(check_frames(scenes, rep, mi))
    totals = {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()}
    rep.metrics["scenes"] = totals
    return rep


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m buildzr.site.check", description=__doc__.splitlines()[0])
    ap.add_argument("data_dir", nargs="+", help="directory holding index.json")
    ap.add_argument("--json", action="store_true", help="print metrics as JSON")
    ap.add_argument("--max-errors", type=int, default=50)
    args = ap.parse_args(list(argv) if argv is not None else None)
    bad = 0
    for d in args.data_dir:
        rep = check_site(d)
        print(f"{'OK' if rep.ok else f'FAIL ({len(rep.errors)})'}  {d}")
        for e in rep.errors[: args.max_errors]:
            print(f"    {e}")
        if args.json:
            print(json.dumps(rep.metrics, sort_keys=True))
        bad += not rep.ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
