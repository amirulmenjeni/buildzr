"""Check model.json, index.json and scene files against the v4 contract.

The JSON schemas in ``buildzr/site/schema/`` cover shapes; this module checks
what they cannot: canonical bytes, containment, pre-order, rollup counts,
frames and port continuity across levels (design note v4, sections C and I).

Usage::

    python -m buildzr.site.check DATA_DIR        # dir holding index.json
    python -m buildzr.site.check --json DATA_DIR # also print the metrics as JSON

Exit status 0 when there are no errors. :func:`check_built` returns a
:class:`Report` whose ``metrics`` the acceptance tests assert on.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import math
import os
import re
import sys
import time
from dataclasses import dataclass, field
from typing import Any, Iterable, Optional

import jsonschema  # type: ignore[import-untyped]

from buildzr.site.canonical import INDEX_SCHEMA, MODEL_SCHEMA, SCENE_SCHEMA, dumps, model_hash

DEPLOYMENT_TYPES = ("DeploymentNode", "InfrastructureNode", "ContainerInstance", "SoftwareSystemInstance")
INSTANCE_OF = {"ContainerInstance": "Container", "SoftwareSystemInstance": "SoftwareSystem"}

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
    with open(os.path.join(SCHEMA_DIR, schema_file), encoding="utf-8") as f:
        schema = json.load(f)
    return [f"schema {list(e.absolute_path)}: {e.message}"
            for e in jsonschema.Draft202012Validator(schema).iter_errors(obj)]


def _rounded(v: float) -> bool:
    return abs(v * 100 - round(v * 100)) < 1e-6


# A ``file`` entry of index.json: relative, ``/``-separated, safe characters only, no ``.`` or ``..``
# segment (``fullmatch``: Python's ``$`` would let a trailing newline through). The same rule is the
# ``pattern`` of ``file`` in schema/index.schema.json.
_FILE_RE = re.compile(r"^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$")


class _Timeout(Exception):
    """Raised by :meth:`_Deadline.check` once the time limit is over."""


class _Deadline:
    """Cooperative time limit: call :meth:`check` between phases and inside long loops."""

    def __init__(self, seconds: Optional[float]) -> None:
        self.seconds = seconds
        self.end = None if seconds is None else time.monotonic() + seconds

    def check(self) -> None:
        if self.end is not None and time.monotonic() > self.end:
            raise _Timeout()


def _short(v: Any) -> str:
    r = repr(v)
    return r if len(r) <= 80 else r[:77] + "..."


def _safe_file(data_dir: str, rel: Any) -> Optional[str]:
    """Return the real path of ``data_dir/rel`` or None if ``rel`` is not a relative path inside ``data_dir``.

    ``rel`` must match :data:`_FILE_RE` and have no ``.`` or ``..`` segment; after symlinks are resolved
    the path must still be inside the real ``data_dir``. Nothing is opened here.
    """
    if not isinstance(rel, str) or not _FILE_RE.fullmatch(rel) or any(seg in (".", "..") for seg in rel.split("/")):
        return None
    root = os.path.realpath(data_dir)
    real = os.path.realpath(os.path.join(root, *rel.split("/")))
    if os.path.commonpath([root, real]) != root or real == root:
        return None
    return real


def _read_json(path: str, rep: Report, where: str, expect_hash: Optional[str] = None) -> Optional[Any]:
    """Read ``path`` once, check its hash if given, parse it and check the bytes are canonical.

    Every failure (unreadable, not a regular file, not UTF-8, not JSON, too deeply nested) is an error in
    ``rep`` and the result is None.
    """
    try:
        if not os.path.isfile(path):
            raise OSError("not a regular file")
        with open(path, "rb") as f:
            data = f.read()
    except OSError as e:
        rep.err(where, f"cannot read {path}: {e}")
        return None
    if expect_hash is not None:
        h = "sha256:" + hashlib.sha256(data).hexdigest()
        if h != expect_hash:
            rep.err(where, f"hash {expect_hash} != file bytes {h}")
    try:
        raw = data.decode("utf-8")
        obj = json.loads(raw)
    except (ValueError, RecursionError) as e:  # UnicodeDecodeError and JSONDecodeError are ValueErrors
        rep.err(where, f"not valid UTF-8 JSON: {type(e).__name__}: {str(e)[:120]}")
        return None
    try:
        canonical = raw == dumps(obj)
    except (ValueError, RecursionError, TypeError):
        canonical = False
    if not canonical:
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
        out: list[str] = []
        cur: Optional[str] = path
        while cur is not None and len(out) <= len(self.el):  # bounded: a parent cycle must not hang
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
    envs = {env["key"]: env for env in model["deployment"]["environments"]}
    if len(envs) != len(model["deployment"]["environments"]):
        rep.err(where, "duplicate environment key")
    for e in model["elements"]:
        if e["id"] in seen:
            rep.err(where, f"duplicate element id {e['id']}")
        p = e["parent"]
        deployed = e["type"] in DEPLOYMENT_TYPES
        if p is not None:
            if p not in seen:
                rep.err(where, f"element {e['id']}: parent {p} missing or after child (pre-order)")
            elif e["id"] not in seen[p]["children"]:
                rep.err(where, f"element {e['id']} not in children of {p}")
            if not e["id"].startswith(p + "/"):
                rep.err(where, f"element {e['id']}: path does not extend parent path {p}")
        elif deployed:
            if e["type"] != "DeploymentNode" or e["id"].count("/") != 2:
                rep.err(where, f"element {e['id']}: a top-level deployment element must be a DeploymentNode "
                               "with the id deploy/<environment>/<name>")
        elif "/" in e["id"]:
            rep.err(where, f"root element {e['id']} has a nested path")
        if deployed:
            _check_deployment_element(e, seen, envs, rep, where)
        else:
            if e["id"].split("/")[0] == "deploy":
                rep.err(where, f"element {e['id']}: only deployment elements use the root 'deploy'")
            for k in ("environment", "instanceOf", "instances", "healthChecks"):
                if k in e:
                    rep.err(where, f"element {e['id']}: {k} is only for deployment elements")
            if "metadata" in e and e["type"] != "Element":
                rep.err(where, f"element {e['id']}: metadata is only for custom elements")
            if e["type"] == "Element" and (p is not None or e["children"]):
                rep.err(where, f"element {e['id']}: a custom element is a root with no children")
        seen[e["id"]] = e
    for env in envs.values():
        if env["id"] != f"deploy/{env['key']}":
            rep.err(where, f"environment {env['key']}: id {env['id']} != deploy/{env['key']}")
        for n in env["nodes"]:
            if n not in seen or seen[n]["parent"] is not None or seen[n].get("environment") != env["key"]:
                rep.err(where, f"environment {env['key']}: node {n} is not one of its top-level deployment nodes")
        tops = [e["id"] for e in model["elements"] if e["parent"] is None and e.get("environment") == env["key"]]
        if tops != env["nodes"]:
            rep.err(where, f"environment {env['key']}: nodes {env['nodes']} != its top-level nodes {tops}")
    for e in model["elements"]:
        for c in e["children"]:
            if c not in seen or seen[c]["parent"] != e["id"]:
                rep.err(where, f"element {e['id']}: child {c} missing or with another parent")
    views = {v["key"] for v in model["views"]}
    if len(views) != len(model["views"]):
        rep.err(where, "duplicate view key")
    for v in model["views"]:
        if (v["kind"] == "deployment") != ("environment" in v):
            rep.err(where, f"view {v['key']}: environment is required on deployment views and only there")
        elif v["kind"] == "deployment":
            env = envs.get(v["environment"])
            if env is None:
                rep.err(where, f"view {v['key']}: unknown environment {v['environment']}")
            elif v["key"] not in env["views"]:
                rep.err(where, f"view {v['key']}: not in the views of environment {v['environment']}")
    for env in envs.values():
        for k in env["views"]:
            if not any(v["key"] == k and v.get("environment") == env["key"] for v in model["views"]):
                rep.err(where, f"environment {env['key']}: view {k} is not one of its deployment views")
    kinds = {v["key"]: v for v in model["views"]}
    for e in model["elements"]:
        for k in e["views"]:
            v = kinds.get(k)
            if v is None:
                continue
            if (v["kind"] == "deployment") != (e["type"] in DEPLOYMENT_TYPES):
                rep.err(where, f"element {e['id']}: a {e['type']} cannot be in the {v['kind']} view {k}")
            elif v["kind"] == "deployment" and e.get("environment") != v.get("environment"):
                rep.err(where, f"element {e['id']}: in view {k} of another environment")
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


def _check_deployment_element(e: Json, seen: dict[str, Json], envs: dict[str, Json], rep: Report, where: str) -> None:
    """Rules of one deployment element; ``seen`` holds the elements before it (parents and instanceOf targets)."""
    env = e.get("environment")
    if env not in envs:
        rep.err(where, f"element {e['id']}: unknown environment {env!r}")
    elif not e["id"].startswith(envs[env]["id"] + "/"):
        rep.err(where, f"element {e['id']}: id does not start with {envs[env]['id']}/")
    p = e["parent"]
    if p is not None and p in seen and (seen[p]["type"] != "DeploymentNode" or seen[p].get("environment") != env):
        rep.err(where, f"element {e['id']}: parent {p} is not a deployment node of environment {env}")
    if e["type"] != "DeploymentNode" and e["children"]:
        rep.err(where, f"element {e['id']}: a {e['type']} has no children")
    if ("instances" in e) != (e["type"] == "DeploymentNode"):
        rep.err(where, f"element {e['id']}: instances is required on deployment nodes and only there")
    want = INSTANCE_OF.get(e["type"])
    if want is None:
        if "instanceOf" in e or "healthChecks" in e:
            rep.err(where, f"element {e['id']}: instanceOf and healthChecks are only for instances")
    elif e.get("instanceOf") not in seen or seen[e["instanceOf"]]["type"] != want:
        rep.err(where, f"element {e['id']}: instanceOf {e.get('instanceOf')!r} is not a {want}")


# --- one scene -----------------------------------------------------------------


def check_scene(scene: Json, rep: Report, mi: Optional[ModelIndex] = None,
                deadline: Optional[_Deadline] = None) -> dict[str, Any]:
    """Check one scene on its own (plus rollups against the model if given). Returns metrics."""
    dl = deadline or _Deadline(None)
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
        if "instances" in n and n["type"] != "DeploymentNode":
            rep.err(where, f"node {nid}: only deployment nodes carry instances")
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
        out: set[str] = set()
        cur: Optional[str] = nid
        while cur is not None and cur in by_id and cur not in out:  # `not in out`: a parent cycle must not hang
            out.add(cur)
            cur = by_id[cur]["parent"]
        return out

    for e in scene["edges"]:
        dl.check()
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

    if mi is not None and kind == "view":
        mv = next((v for v in mi.model["views"] if v["key"] == scene["level"]["scope"]), None)
        if mv is None:
            rep.err(where, f"scope {scene['level']['scope']} is not a view of the model")
        elif mv["kind"] == "deployment":
            for n in scene["nodes"]:
                el = mi.el.get(n["id"])
                if el is None or el["type"] not in DEPLOYMENT_TYPES or el.get("environment") != mv["environment"]:
                    rep.err(where, f"node {n['id']}: not a deployment element of environment {mv['environment']}")
                elif n["type"] != el["type"]:
                    rep.err(where, f"node {n['id']}: type {n['type']} != model type {el['type']}")
                elif n.get("instances", "1") != el.get("instances", "1"):
                    rep.err(where, f"node {n['id']}: instances {n.get('instances', '1')} != model {el.get('instances', '1')}")
            members = {e["id"] for e in mi.model["elements"] if mv["key"] in e["views"]}
            drawn_ids = {n["id"] for n in scene["nodes"]}
            if members != drawn_ids:
                rep.err(where, f"nodes {sorted(members ^ drawn_ids)[:10]} differ from the elements of view {mv['key']}")
        else:
            for n in scene["nodes"]:
                if n["type"] in DEPLOYMENT_TYPES:
                    rep.err(where, f"node {n['id']}: a {n['type']} in the {mv['kind']} view {mv['key']}")
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
                dl.check()  # each rollup scans every relationship, so look at the clock per pair
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


def check_frames(scenes: dict[str, Json], rep: Report, mi: Optional[ModelIndex],
                 deadline: Optional[_Deadline] = None) -> dict[str, Any]:
    """Frames and ports: child scene placement, port sets, continuity, rels conservation."""
    dl = deadline or _Deadline(None)
    m: dict[str, Any] = {"frames": 0, "ports": 0, "port_gap_px": 0.0, "port_sides_kept": 0}
    for key, parent in scenes.items():
        dl.check()
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
                dl.check()
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


def check_built(data_dir: str, timeout: Optional[float] = 60, require_build_json: bool = False) -> Report:
    """Check index.json, model.json and every scene under ``data_dir``.

    Safe on untrusted input: every ``file`` in index.json must be a relative path inside ``data_dir``
    (nothing outside it is opened), and any problem, including an unexpected exception, is returned as an
    error, never raised. ``timeout`` (seconds, ``None`` for no limit) stops the check with the error
    ``check exceeded N s``; it is cooperative, so it is looked at between phases and inside the long loops.
    ``<data_dir>/../build.json`` is checked when present (``require_build_json``: it must be there).
    """
    rep = Report()
    dl = _Deadline(timeout)
    try:
        _check_built(data_dir, rep, dl, require_build_json)
    except _Timeout:
        rep.err("check", f"check exceeded {timeout:g} s")
    except Exception as e:  # untrusted input must never crash the caller
        rep.err("check", f"internal error while checking: {type(e).__name__}: {str(e)[:200]}")
    return rep


def _guarded(rep: Report, where: str, fn: Any, *args: Any, **kw: Any) -> Any:
    """Run one check phase; an unexpected exception becomes an error and the other phases still run."""
    try:
        return fn(*args, **kw)
    except _Timeout:
        raise
    except Exception as e:
        rep.err(where, f"malformed content, check aborted: {type(e).__name__}: {str(e)[:200]}")
        return None


def _check_build_json(data_dir: str, index: Json, rep: Report, required: bool) -> None:
    path = os.path.join(os.path.dirname(os.path.realpath(data_dir)), "build.json")
    if os.path.islink(path) or not os.path.lexists(path):
        if os.path.islink(path):
            rep.err("build.json", "must be a regular file, not a symlink")
        elif required:
            rep.err("build.json", "missing")
        return
    info = _read_json(path, rep, "build.json")
    if info is None:
        return
    if not isinstance(info, dict) or not isinstance(info.get("modelHash"), str):
        rep.err("build.json", "must be an object with a modelHash string")
    elif info["modelHash"] != index["modelHash"]:
        rep.err("build.json", f"modelHash {info['modelHash']} != index.json modelHash {index['modelHash']}")


def _check_built(data_dir: str, rep: Report, dl: _Deadline, require_build_json: bool) -> None:
    real_index = _safe_file(data_dir, "index.json")
    if real_index is None:
        rep.err("index.json", "is not inside the data directory")
        return
    index = _read_json(real_index, rep, "index.json")
    if index is None:
        return
    if not isinstance(index, dict):
        rep.err("index.json", "must be a JSON object")
        return
    for e in _schema_errors(index, "index.schema.json"):
        rep.err("index.json", e)
    if index.get("schema") != INDEX_SCHEMA:
        return
    # What the checker itself relies on, checked again so that nothing below can be misled by a bad entry.
    def entry_ok(entry: Any, where: str) -> bool:
        if not (isinstance(entry, dict) and isinstance(entry.get("file"), str) and isinstance(entry.get("hash"), str)):
            rep.err(where, "index entry must be an object with string 'file' and 'hash'")
            return False
        if _safe_file(data_dir, entry["file"]) is None:
            rep.err(where, f"file {_short(entry['file'])} is not a relative path inside data/ "
                           "(letters, digits, . _ - and /; no '.' or '..' segment)")
            return False
        return True

    if not isinstance(index.get("modelHash"), str) or not isinstance(index.get("scenes"), dict) \
            or not isinstance(index.get("model"), dict):
        rep.err("index.json", "needs a string modelHash, an object model and an object scenes")
        return
    dl.check()

    def load_entry(entry: Json, where: str) -> Optional[Any]:
        if not entry_ok(entry, where):
            return None
        real = _safe_file(data_dir, entry["file"])
        assert real is not None
        return _read_json(real, rep, where, expect_hash=entry["hash"])

    _check_build_json(data_dir, index, rep, require_build_json)
    model = load_entry(index["model"], "model.json")
    mi = None
    if model is not None and not isinstance(model, dict):
        rep.err("model.json", "must be a JSON object")
        model = None
    if model is not None:
        _guarded(rep, "model.json", check_model, model, rep)
        mi = _guarded(rep, "model.json", ModelIndex, model)
        if index["modelHash"] != model.get("modelHash"):
            rep.err("index.json", "modelHash differs from model.json")
    scenes: dict[str, Json] = {}
    for key, entry in sorted(index["scenes"].items()):
        dl.check()
        s = load_entry(entry, f"scene {key}")
        if s is not None and not isinstance(s, dict):
            rep.err(f"scene {key}", "must be a JSON object")
        elif s is not None:
            if s.get("key") != key:
                rep.err(f"scene {key}", f"file declares key {s.get('key')}")
            scenes[key] = s
    totals: dict[str, Any] = {"scenes": len(scenes), "nodes": 0, "edges": 0, "bad_edges": 0, "edge_end_gap_px": 0.0}
    for key, s in scenes.items():
        dl.check()
        sm = _guarded(rep, f"scene {key}", check_scene, s, rep, mi, dl)
        if sm is not None:
            for k in ("nodes", "edges", "bad_edges"):
                totals[k] += sm[k]
            totals["edge_end_gap_px"] = max(totals["edge_end_gap_px"], sm["edge_end_gap_px"])
        if model is not None and s.get("modelHash") != model.get("modelHash"):
            rep.err(f"scene {key}", "modelHash differs from model.json")
    if model is not None:
        views = _guarded(rep, "model.json", lambda: [(v["key"], v["scene"]) for v in model["views"]]) or []
        for vkey, vscene in views:
            if vscene not in index["scenes"]:
                rep.err("index.json", f"view {vkey}: scene {vscene} missing")
        if "landscape" not in index["scenes"]:
            rep.err("index.json", "no landscape scene")
    fm = _guarded(rep, "frames", check_frames, scenes, rep, mi, dl)
    if fm is not None:
        totals.update(fm)
    totals = {k: round(v, 2) if isinstance(v, float) else v for k, v in totals.items()}
    rep.metrics["scenes"] = totals


def main(argv: Optional[Iterable[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m buildzr.site.check", description=__doc__.splitlines()[0])
    ap.add_argument("data_dir", nargs="+", help="directory holding index.json")
    ap.add_argument("--json", action="store_true", help="print metrics as JSON")
    ap.add_argument("--max-errors", type=int, default=50)
    ap.add_argument("--timeout", type=float, default=60, help="seconds for the whole check per directory (0: no limit)")
    ap.add_argument("--require-build-json", action="store_true", help="a missing ../build.json is an error")
    args = ap.parse_args(list(argv) if argv is not None else None)
    bad = 0
    for d in args.data_dir:
        rep = check_built(d, timeout=args.timeout or None, require_build_json=args.require_build_json)
        print(f"{'OK' if rep.ok else f'FAIL ({len(rep.errors)})'}  {d}")
        for e in rep.errors[: args.max_errors]:
            print(f"    {e}")
        if args.json:
            print(json.dumps(rep.metrics, sort_keys=True))
        bad += not rep.ok
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
