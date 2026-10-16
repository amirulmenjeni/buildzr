"""Three-pass reserved-frame layout (design note v4, section C, "Edge continuity across levels").

Ported from the spike's ``port_exp2.py`` and generalised from two levels to any depth.

Levels form a tree: ``landscape`` -> ``e/<system>`` -> ``e/<system>/<container>``. A node that has
children in the next level is a *frame*: in its parent level it is a box of reserved size, and the
child level is drawn scaled down inside it. Three passes, each over all levels of one depth at a time
(one ELK batch per depth, one Node process for the whole build):

1. **Sizes, bottom-up.** Each element level is laid out as a compound (its scope) without ports; the
   frame it needs in the parent is reserved from that size (:func:`reserve`).
2. **Sides, top-down.** Each level that has frames is laid out with the reserved sizes. The side and
   the order in which every rolled-up edge meets each frame is recorded.
3. **Final, bottom-up.** Each element level is laid out as a compound whose ports are ``FIXED_ORDER``
   with the sides recorded by its parent, and whose frame children are *leaves* with ``FIXED_POS``
   ports at the child's final port position times its scale. The landscape comes last.

Ports are 0x0, so ELK puts them exactly on the border and edges end exactly on them. ELK honours the
side of a compound's ports (``FIXED_ORDER`` + ``elk.port.side``) but not reliably their order within a
side (``elk.port.index`` is ignored, the ``ports`` array order is not always followed), so the layout
relies on sides only and lists ports sorted by side and position along the side from pass 2.
"""

from __future__ import annotations

import hashlib
import json
import math
from dataclasses import dataclass, field
from typing import Any, Optional

from buildzr.site import fonts
from buildzr.site.canonical import dumps
from buildzr.site.layout.elk import ELK_VERSION, ElkRunner

Json = dict[str, Any]

LEAF_W, LEAF_H = fonts.ELEM_W, 140  # nominal leaf box, the unit of the frame area budget
MARGIN = 12  # landscape / view margin, px
COMPOUND_PAD = (40, 20, 20, 20)  # top, left, bottom, right: a scope's inside padding
BOUNDARY_PAD = (24, 20, 48, 20)  # authored views: boundary padding, the bottom holds the label
MIN_BOUNDARY_H = 120
SIZE_PASS_SLACK = 1.25  # pass 1 pads the header band by this factor so the final pass rarely has to redo it
HEADER_MARGIN = 8  # px between a frame's label and its first child row, in parent scale
EDGE_LABEL_W = 200
ELK_JSON_PREFIX = "org.eclipse.elk.json."

OPTS: dict[str, str] = {
    "elk.algorithm": "layered",
    "elk.hierarchyHandling": "INCLUDE_CHILDREN",
    "elk.edgeRouting": "ORTHOGONAL",
    "elk.direction": "DOWN",
    "elk.spacing.nodeNode": "25",
    "elk.layered.spacing.nodeNodeBetweenLayers": "40",
    "elk.spacing.edgeNode": "10",
    "elk.layered.spacing.edgeNodeBetweenLayers": "10",
    "elk.spacing.edgeEdge": "10",
    "elk.layered.spacing.edgeEdgeBetweenLayers": "10",
    "elk.spacing.edgeLabel": "4",
    "elk.layered.considerModelOrder.strategy": "NONE",
    "org.eclipse.elk.json.edgeCoords": "ROOT",
    "org.eclipse.elk.json.shapeCoords": "ROOT",
}

SIDE_OF = {"NORTH": "N", "EAST": "E", "SOUTH": "S", "WEST": "W"}
CLOCKWISE = {"NORTH": 0, "EAST": 1, "SOUTH": 2, "WEST": 3}


def _pad(p: tuple[int, int, int, int]) -> str:
    return f"[top={p[0]},left={p[1]},bottom={p[2]},right={p[3]}]"


def reserve(w: float, h: float, k: float) -> tuple[float, float, float]:
    """Reserve a frame for an inner layout of ``w`` x ``h``: area at most ``k`` leaf boxes.

    Returns ``(frame_w, frame_h, scale)``. The scale is uniform and at most 1; an inner layout is
    at least a leaf box (its compound has that minimum size), so the frame never has less area
    than a leaf.
    """
    s = min(1.0, math.sqrt(k * LEAF_W * LEAF_H / (w * h)))
    s = math.floor(s * 1e6) / 1e6
    return round(w * s, 2), round(h * s, 2), s


def input_hash(graph: Json) -> str:
    """``sha256:<hex>`` of the canonical ELK input."""
    return "sha256:" + hashlib.sha256(dumps(graph).encode("utf-8")).hexdigest()


def _border(pt: tuple[float, float], r: tuple[float, float, float, float]) -> tuple[str, float]:
    """Nearest border of rect ``r`` (x, y, w, h) to ``pt``: ('NORTH'.., position along that border)."""
    x, y, w, h = r
    d = {"NORTH": abs(pt[1] - y), "SOUTH": abs(pt[1] - y - h), "WEST": abs(pt[0] - x), "EAST": abs(pt[0] - x - w)}
    side = min(d, key=lambda s: (d[s], CLOCKWISE[s]))
    return side, (pt[0] - x if side in ("NORTH", "SOUTH") else pt[1] - y)


def section_points(edge: Json) -> list[tuple[float, float]]:
    """Polyline of an ELK edge result: start, bend points, end."""
    sec = edge["sections"][0]
    pts = [(sec["startPoint"]["x"], sec["startPoint"]["y"])]
    pts += [(b["x"], b["y"]) for b in sec.get("bendPoints", [])]
    pts.append((sec["endPoint"]["x"], sec["endPoint"]["y"]))
    return pts


@dataclass
class Placed:
    """Geometry of one laid-out level, in the level's local coordinates."""

    key: str
    bounds: tuple[float, float, float, float]
    nodes: dict[str, tuple[float, float, float, float]]  # id -> x, y, w, h
    labels: dict[str, list[Json]]  # node id -> wrapped label lines
    ports: list[Json]  # {"id", "x", "y", "side"} sorted by id (element levels)
    edges: dict[str, Json]  # edge id -> {"points": [...], "label": {...}?}
    input_hash: str
    options: dict[str, str]
    passes: int
    scales: dict[str, float] = field(default_factory=dict)  # frame node id -> scale
    fallback: Optional[str] = None


class Layouter:
    """Lays out every level of a ``buildzr.levels/2`` object."""

    def __init__(self, levels: Json, runner: ElkRunner, k: float = 4.0) -> None:
        self.runner = runner
        self.k = k
        self.lv: dict[str, Json] = {lv["key"]: lv for lv in levels["levels"]}
        self.order = [lv["key"] for lv in levels["levels"]]
        self.nodes: dict[str, dict[str, Json]] = {k_: {n["id"]: n for n in lv["nodes"]} for k_, lv in self.lv.items()}
        self.leaf: dict[tuple[str, str], tuple[int, int, list[Json]]] = {}
        self.elabel: dict[tuple[str, str], tuple[list[Json], float, float]] = {}
        self.frames: dict[str, dict[str, str]] = {}  # level key -> node id -> child level key
        for key, lv in self.lv.items():
            self.frames[key] = {}
            for n in lv["nodes"]:
                if "children" in n:
                    ck = "e/" + n["id"]
                    if ck not in self.lv:
                        raise ValueError(f"level {key}: node {n['id']} has children but level {ck} is missing")
                    self.frames[key][n["id"]] = ck
            if lv["level"]["kind"] != "view":
                for n in lv["nodes"]:
                    if n["role"] == "element" and n["id"] not in self.frames[key]:
                        fs = float(n["style"].get("fontSize", 16))
                        self.leaf[(key, n["id"])] = fonts.leaf_size(n["lines"], fs)
            for e in lv["edges"]:
                self.elabel[(key, e["id"])] = self._edge_label(e)
        self.scope_node: dict[str, Json] = {}  # element level -> its node in the parent level
        for key, fr in self.frames.items():
            for nid, ck in fr.items():
                self.scope_node[ck] = self.nodes[key][nid]
        self.top_pad: dict[str, int] = {}  # element level -> inner top padding (header band), px
        self.cache: dict[str, Json] = {}
        self.timings: dict[str, float] = {}
        self.runs = {key: 0 for key in self.lv}
        # results
        self.fsz1: dict[str, tuple[float, float, float]] = {}  # pass-1 frame size per element level
        self.fsz: dict[str, tuple[float, float, float]] = {}  # final frame size
        self.sides: dict[str, dict[str, tuple[str, int]]] = {}  # element level -> port id -> side, index
        self.portpt: dict[str, dict[str, tuple[float, float]]] = {}  # element level -> port id -> local point
        self.placed: dict[str, Placed] = {}
        self.pass2_landscape_len = 0.0
        self.final_landscape_len = 0.0

    # --- labels and boxes -------------------------------------------------------

    @staticmethod
    def _edge_label(e: Json) -> tuple[list[Json], float, float]:
        fs = float(e["style"].get("fontSize", 12))
        lines = fonts.wrap(e.get("lines", []), EDGE_LABEL_W, fs)
        if not lines:
            return [], 0.0, 0.0
        w = fonts.widest(lines, fs) + 8
        h = fonts.text_height(lines, fs) + 4
        return lines, round(w, 2), round(h, 2)

    def depth(self, key: str) -> int:
        return 0 if key == "landscape" else key.count("/")

    def element_keys(self) -> list[str]:
        return [k for k in self.order if self.lv[k]["level"]["kind"] == "element"]

    # --- header band ---------------------------------------------------------------

    def header_height(self, key: str, frame_w: float) -> float:
        """Height of the frame label (tiers 0 and 1) as drawn on the frame node in the parent scene."""
        n = self.scope_node[key]
        fs = float(n["style"].get("fontSize", 16))
        lines = fonts.wrap([ln for ln in n["lines"] if ln["tier"] <= 1], frame_w - 2 * fonts.PAD, fs)
        return fonts.text_height(lines, fs)

    def pad_needed(self, key: str, w: float, h: float) -> int:
        """Inner top padding so that the scaled header band (label + margin) fits above the children."""
        fw, _, s = reserve(w, h, self.k)
        return int(math.ceil((self.header_height(key, fw) + HEADER_MARGIN) / s - 1e-6))

    def _fit_pads(self, keys: list[str], mode: str, timing: str) -> dict[str, Json]:
        """Lay out ``keys``, raising each level's top padding until its header band fits (normally one extra layout)."""
        results: dict[str, Json] = {}
        todo = list(keys)
        for _ in range(5):
            out = self._timed(timing, {k: self.elk_graph(k, mode) for k in todo})
            again = []
            for k in todo:
                comp = out[k]["children"][0]
                p0 = self.top_pad.get(k, COMPOUND_PAD[0])
                need = p0
                for _ in range(20):  # closed form: raising the top padding only adds to the height
                    nxt = max(need, self.pad_needed(k, comp["width"], comp["height"] + need - p0))
                    if nxt == need:
                        break
                    need = nxt
                results[k] = out[k]
                if need > p0:
                    self.top_pad[k] = need
                    if mode == "size":  # only the size is used: the height grows by the padding added
                        need = int(math.ceil(need * SIZE_PASS_SLACK))  # final layouts are a bit larger
                        self.top_pad[k] = need
                        comp["height"] += need - p0
                    else:
                        again.append(k)
            if not again:
                return results
            todo = again
        raise ValueError(f"header band of {todo} does not converge")

    # --- ELK graphs -------------------------------------------------------------

    def _node_size(self, key: str, nid: str, mode: str) -> tuple[float, float]:
        ck = self.frames[key].get(nid)
        if ck is None:
            w, h, _ = self.leaf[(key, nid)]
            return w, h
        f = (self.fsz if mode == "final" else self.fsz1)[ck]
        return f[0], f[1]

    @staticmethod
    def _boundary(n: Json, children: list[Json]) -> Json:
        """A group or view boundary: a compound with a label strip at the bottom and a minimum width."""
        fs = float(n["style"].get("fontSize", 16))
        w = fonts.widest(n["lines"], fs) + 40
        return {"id": n["id"], "layoutOptions": {
            "elk.padding": _pad(BOUNDARY_PAD), "elk.nodeSize.constraints": "MINIMUM_SIZE",
            "elk.nodeSize.minimum": f"({round(w, 2)},{MIN_BOUNDARY_H})"}, "children": children}

    def elk_graph(self, key: str, mode: str) -> Json:
        """ELK input of a landscape or element level. ``mode``: 'size' | 'sides' | 'final'."""
        lv = self.lv[key]
        kind = lv["level"]["kind"]
        opts = dict(OPTS)
        port_edge_ids: dict[str, set[str]] = {}
        kids: dict[Optional[str], list[Json]] = {}
        for n in lv["nodes"]:
            kids.setdefault(n["parent"], []).append(n)

        def conv(n: Json) -> Json:
            nid = n["id"]
            if n["role"] == "boundary":
                return self._boundary(n, [conv(c) for c in kids.get(nid, [])])
            w, h = self._node_size(key, nid, mode)
            node: Json = {"id": nid, "width": w, "height": h}
            ck = self.frames[key].get(nid)
            if ck is not None:
                port_edge_ids[nid] = {p["id"] for p in self.lv[ck]["ports"]}
                if mode == "final":
                    s_ = self.fsz[ck][2]
                    ports = []
                    for p in self.lv[ck]["ports"]:
                        px, py = self.portpt[ck][p["id"]]
                        ports.append({"id": f"{nid}|{p['id']}", "width": 0, "height": 0,
                                      "x": round(px * s_, 4), "y": round(py * s_, 4),
                                      "layoutOptions": {"elk.port.side": self.sides[ck][p["id"]][0]}})
                    if ports:
                        node["ports"] = ports
                        node["layoutOptions"] = {"elk.portConstraints": "FIXED_POS"}
            return node

        children = [conv(n) for n in kids.get(None, [])]
        if kind == "landscape":
            opts["elk.padding"] = _pad((MARGIN,) * 4)  # type: ignore[arg-type]
            top: Json = {"id": "root", "layoutOptions": opts, "children": children}
        else:
            opts["elk.padding"] = _pad((0, 0, 0, 0))
            scope = lv["level"]["scope"]
            copts = {"elk.padding": _pad((self.top_pad.get(key, COMPOUND_PAD[0]),) + COMPOUND_PAD[1:]), "elk.nodeSize.constraints": "MINIMUM_SIZE",
                     "elk.nodeSize.minimum": f"({LEAF_W},{LEAF_H})"}
            comp: Json = {"id": scope, "layoutOptions": copts, "children": children}
            if mode != "size" and lv["ports"]:
                comp["layoutOptions"]["elk.portConstraints"] = "FIXED_ORDER"
                comp["ports"] = [
                    {"id": "port:" + p["id"], "width": 0, "height": 0,
                     "layoutOptions": {"elk.port.side": self.sides[key][p["id"]][0]}}
                    for p in sorted(lv["ports"], key=lambda p: self.sides[key][p["id"]][1])]
            top = {"id": "root", "layoutOptions": opts, "children": [comp]}
        edges: list[Json] = []
        for e in lv["edges"]:
            ends: list[str] = []
            skip = False
            for end_key in ("source", "target"):
                end = e[end_key]
                if isinstance(end, dict):
                    if mode == "size":
                        skip = True
                        break
                    ends.append("port:" + end["port"])
                elif mode == "final" and e["id"] in port_edge_ids.get(end, ()):
                    ends.append(f"{end}|{e['id']}")
                else:
                    ends.append(end)
            if skip:
                continue
            ed: Json = {"id": e["id"], "sources": [ends[0]], "targets": [ends[1]]}
            lines, lw, lh = self.elabel[(key, e["id"])]
            if lines:
                ed["labels"] = [{"id": e["id"] + "#label", "text": " ".join(x["text"] for x in lines),
                                 "width": lw, "height": lh}]
            edges.append(ed)
        top["edges"] = edges
        return top

    def run(self, graphs: dict[str, Json]) -> dict[str, Json]:
        """Lay out ``graphs`` with identical inputs shared across the whole build."""
        keys = {name: hashlib.sha256(json.dumps(g, sort_keys=True).encode()).hexdigest() for name, g in graphs.items()}
        todo = {}
        for name, g in graphs.items():
            if keys[name] not in self.cache and keys[name] not in {keys[n] for n in todo}:
                todo[name] = g
        if todo:
            out = self.runner.layout(todo)
            for name, res in out.items():
                self.cache[keys[name]] = res
        return {name: self.cache[keys[name]] for name in graphs}

    # --- passes -------------------------------------------------------------------

    def layout_generated(self) -> None:
        """Run the three passes over the landscape and all element levels."""
        elem = self.element_keys()
        max_d = max((self.depth(k) for k in elem), default=0)
        by_depth = {d: [k for k in ["landscape"] + elem if self.depth(k) == d and k in self.lv] for d in range(max_d + 1)}
        # pass 1: sizes, bottom-up
        for d in range(max_d, 0, -1):
            keys = by_depth[d]
            for k, res in self._fit_pads(keys, "size", "pass1").items():
                comp = res["children"][0]
                self.runs[k] += 1
                self.fsz1[k] = reserve(comp["width"], comp["height"], self.k)
        # pass 2: sides, top-down
        for d in range(0, max_d + 1):
            keys = [k for k in by_depth[d] if self.frames[k]]
            graphs = {k: self.elk_graph(k, "sides") for k in keys}
            for k, res in self._timed("pass2", graphs).items():
                self.runs[k] += 1
                self._record_sides(k, res)
                if k == "landscape":
                    self.pass2_landscape_len = self._edge_length(res)
        # pass 3: final, bottom-up
        for d in range(max_d, -1, -1):
            keys = by_depth[d]
            elem_keys = [k for k in keys if k != "landscape"]
            results = self._fit_pads(elem_keys, "final", "pass3") if elem_keys else {}
            if "landscape" in keys:
                results["landscape"] = self._timed("pass3", {"landscape": self.elk_graph("landscape", "final")})["landscape"]
            for k in keys:
                self.runs[k] += 1
                self._place(k, self.elk_graph(k, "final"), results[k])
        self.final_landscape_len = self._edge_length_placed("landscape")

    def _timed(self, name: str, graphs: dict[str, Json]) -> dict[str, Json]:
        t0 = self.runner.total_ms
        out = self.run(graphs)
        self.timings[name] = self.timings.get(name, 0.0) + (self.runner.total_ms - t0)
        return out

    @staticmethod
    def _edge_length(res: Json) -> float:
        total = 0.0
        for e in res.get("edges", []):
            pts = section_points(e)
            total += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        return total

    def _edge_length_placed(self, key: str) -> float:
        total = 0.0
        for e in self.placed[key].edges.values():
            pts = e["points"]
            total += sum(math.hypot(b[0] - a[0], b[1] - a[1]) for a, b in zip(pts, pts[1:]))
        return total

    @staticmethod
    def _rects(res: Json) -> dict[str, tuple[float, float, float, float]]:
        out = {}

        def walk(n: Json) -> None:
            for c in n.get("children", []):
                out[c["id"]] = (c["x"], c["y"], c["width"], c["height"])
                walk(c)
        walk(res)
        return out

    def _record_sides(self, key: str, res: Json) -> None:
        """From a pass-2 layout: side and order of every edge at every frame child."""
        rects = self._rects(res)
        per_child: dict[str, list[tuple[str, str, float]]] = {}
        frames = self.frames[key]
        for e in res["edges"]:
            pts = section_points(e)
            src, tgt = e["sources"][0], e["targets"][0]
            for nid, pt in ((src, pts[0]), (tgt, pts[-1])):
                if nid in frames:
                    side, along = _border(pt, rects[nid])
                    per_child.setdefault(nid, []).append((e["id"], side, along))
        for nid, ck in frames.items():
            items = per_child.get(nid, [])

            def sort_key(t: tuple[str, str, float]) -> tuple[int, float, str]:
                eid, side, al = t
                return (CLOCKWISE[side], al, eid)
            info = {eid: (side, i) for i, (eid, side, _) in enumerate(sorted(items, key=sort_key))}
            want = {p["id"] for p in self.lv[ck]["ports"]}
            if set(info) != want:
                raise ValueError(f"level {ck}: ports {sorted(want ^ set(info))} not found in the layout of {key}")
            self.sides[ck] = info

    def _place(self, key: str, graph: Json, res: Json) -> None:
        lv = self.lv[key]
        kind = lv["level"]["kind"]
        rects = self._rects(res)
        if kind == "landscape":
            ox = oy = 0.0
            comp = None
        else:
            comp = res["children"][0]
            ox, oy = comp["x"], comp["y"]
        nodes: dict[str, tuple[float, float, float, float]] = {}
        labels: dict[str, list[Json]] = {}
        scales: dict[str, float] = {}
        frame_ids = self.frames[key]
        for n in lv["nodes"]:
            x, y, w, h = rects[n["id"]]
            nodes[n["id"]] = (x - ox, y - oy, w, h)
            fs = float(n["style"].get("fontSize", 16))
            if n["role"] == "boundary":
                labels[n["id"]] = n["lines"]
            elif n["id"] in frame_ids:
                labels[n["id"]] = fonts.wrap(n["lines"], w - 2 * fonts.PAD, fs)
                scales[n["id"]] = self.fsz[frame_ids[n["id"]]][2]
            else:
                labels[n["id"]] = self.leaf[(key, n["id"])][2]
        edges: dict[str, Json] = {}
        res_edges = {e["id"]: e for e in res["edges"]}
        for e in lv["edges"]:
            re_ = res_edges[e["id"]]
            ed: Json = {"points": [(x - ox, y - oy) for x, y in section_points(re_)]}
            lines, lw, lh = self.elabel[(key, e["id"])]
            if lines and re_.get("labels"):
                lab = re_["labels"][0]
                ed["label"] = {"lines": lines, "x": lab["x"] - ox, "y": lab["y"] - oy, "w": lw, "h": lh}
            edges[e["id"]] = ed
        opts = {k_: v for k_, v in graph["layoutOptions"].items() if not k_.startswith(ELK_JSON_PREFIX)}
        if kind == "landscape":
            bounds = self._extent_bounds(nodes, edges, res)
            dx, dy = -bounds[0], -bounds[1]
            nodes = {i: (x + dx, y + dy, w, h) for i, (x, y, w, h) in nodes.items()}
            for ed in edges.values():
                ed["points"] = [(x + dx, y + dy) for x, y in ed["points"]]
                if "label" in ed:
                    ed["label"]["x"] += dx
                    ed["label"]["y"] += dy
            bounds = (0.0, 0.0, bounds[2], bounds[3])
            ports: list[Json] = []
        else:
            assert comp is not None
            bw, bh = comp["width"], comp["height"]
            bounds = (0.0, 0.0, bw, bh)
            ports = []
            ppt: dict[str, tuple[float, float]] = {}
            for p in comp.get("ports", []):
                pid = p["id"][len("port:"):]
                px, py = p["x"] - ox, p["y"] - oy
                ppt[pid] = (px, py)
                ports.append({"id": pid, "x": px, "y": py, "side": SIDE_OF[self.sides[key][pid][0]]})
            ports.sort(key=lambda p: p["id"])
            self.portpt[key] = ppt
            self.fsz[key] = reserve(bw, bh, self.k)
        self.placed[key] = Placed(key=key, bounds=bounds, nodes=nodes, labels=labels, ports=ports, edges=edges,
                                  input_hash=input_hash(graph), options=opts, passes=self.runs[key],
                                  scales=scales)

    @staticmethod
    def _extent_bounds(nodes: dict[str, tuple[float, float, float, float]], edges: dict[str, Json],
                       res: Json) -> tuple[float, float, float, float]:
        xs: list[float] = []
        ys: list[float] = []
        for x, y, w, h in nodes.values():
            xs += [x, x + w]
            ys += [y, y + h]
        for ed in edges.values():
            for x, y in ed["points"]:
                xs.append(x)
                ys.append(y)
            if "label" in ed:
                lab = ed["label"]
                xs += [lab["x"], lab["x"] + lab["w"]]
                ys += [lab["y"], lab["y"] + lab["h"]]
        if not xs:
            return (0.0, 0.0, 2.0 * MARGIN, 2.0 * MARGIN)
        x0, y0 = min(xs) - MARGIN, min(ys) - MARGIN
        return (x0, y0, max(xs) + MARGIN - x0, max(ys) + MARGIN - y0)

    # --- authored views: a single plain pass ------------------------------------------

    def view_graph(self, key: str) -> Json:
        lv = self.lv[key]
        kids: dict[Optional[str], list[Json]] = {}
        for n in lv["nodes"]:
            kids.setdefault(n["parent"], []).append(n)

        def conv(n: Json) -> Json:
            fs = float(n["style"].get("fontSize", 16))
            if n["role"] == "boundary":
                return self._boundary(n, [conv(c) for c in kids.get(n["id"], [])])
            w_, h_, wrapped = fonts.leaf_size(n["lines"], fs)
            self.leaf[(key, n["id"])] = (int(w_), h_, wrapped)
            return {"id": n["id"], "width": w_, "height": h_}

        opts = dict(OPTS)
        opts["elk.padding"] = _pad((MARGIN,) * 4)  # type: ignore[arg-type]
        edges = []
        for e in lv["edges"]:
            ed: Json = {"id": e["id"], "sources": [e["source"]], "targets": [e["target"]]}
            lines, lw, lh = self.elabel[(key, e["id"])]
            if lines:
                ed["labels"] = [{"id": e["id"] + "#label", "text": " ".join(x["text"] for x in lines),
                                 "width": lw, "height": lh}]
            edges.append(ed)
        return {"id": "root", "layoutOptions": opts, "children": [conv(n) for n in kids.get(None, [])], "edges": edges}

    def layout_views(self) -> None:
        keys = [k for k in self.order if self.lv[k]["level"]["kind"] == "view"]
        graphs = {k: self.view_graph(k) for k in keys}
        for k, res in self._timed("views", graphs).items():
            self.runs[k] += 1
            lv = self.lv[k]
            rects = self._rects(res)
            nodes = {n["id"]: rects[n["id"]] for n in lv["nodes"]}
            labels: dict[str, list[Json]] = {}
            for n in lv["nodes"]:
                labels[n["id"]] = n["lines"] if n["role"] == "boundary" else self.leaf[(k, n["id"])][2]
            res_edges = {e["id"]: e for e in res["edges"]}
            edges: dict[str, Json] = {}
            for e in lv["edges"]:
                re_ = res_edges[e["id"]]
                ed: Json = {"points": section_points(re_)}
                lines, lw, lh = self.elabel[(k, e["id"])]
                if lines and re_.get("labels"):
                    lab = re_["labels"][0]
                    ed["label"] = {"lines": lines, "x": lab["x"], "y": lab["y"], "w": lw, "h": lh}
                edges[e["id"]] = ed
            bounds = self._extent_bounds(nodes, edges, res)
            dx, dy = -bounds[0], -bounds[1]
            nodes = {i: (x + dx, y + dy, w, h) for i, (x, y, w, h) in nodes.items()}
            for ed in edges.values():
                ed["points"] = [(x + dx, y + dy) for x, y in ed["points"]]
                if "label" in ed:
                    ed["label"]["x"] += dx
                    ed["label"]["y"] += dy
            opts = {k_: v for k_, v in graphs[k]["layoutOptions"].items() if not k_.startswith(ELK_JSON_PREFIX)}
            self.placed[k] = Placed(key=k, bounds=(0.0, 0.0, bounds[2], bounds[3]), nodes=nodes, labels=labels,
                                    ports=[], edges=edges, input_hash=input_hash(graphs[k]), options=opts,
                                    passes=1)


__all__ = ["Layouter", "Placed", "reserve", "ELK_VERSION"]
