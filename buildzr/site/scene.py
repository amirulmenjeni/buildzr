"""Emit ``buildzr.scene/2`` files and ``index.json`` from laid-out levels.

Input: the ``buildzr.levels/2`` object (what to draw) and the :class:`~buildzr.site.layout.passes.Placed`
geometry of every level. Output: ``DATA_DIR/model.<h8>.json``, ``index.json`` and
``scene/<key>.<h8>.json`` (h8 = first 8 hex digits of the file's sha256), all canonical.
"""

from __future__ import annotations

import hashlib
import os
from typing import Any, Optional

from buildzr.site.canonical import INDEX_SCHEMA, SCENE_SCHEMA, dumps, rnd
from buildzr.site.layout.elk import ELK_VERSION
from buildzr.site.layout.passes import Placed

Json = dict[str, Any]

ANCHOR = {"frame": "top", "element": "center", "boundary": "bottom-left"}


def _preorder(nodes: list[Json]) -> list[Json]:
    kids: dict[Optional[str], list[Json]] = {}
    for n in nodes:
        kids.setdefault(n["parent"], []).append(n)
    out: list[Json] = []

    def walk(parent: Optional[str]) -> None:
        for n in sorted(kids.get(parent, []), key=lambda k: k["id"]):
            out.append(n)
            walk(n["id"])
    walk(None)
    return out


def _line(ln: Json) -> Json:
    out = {k: v for k, v in ln.items() if k in ("text", "tier", "weight", "size", "italic")}
    if "size" in out:
        out["size"] = rnd(out["size"])
    return out


def _end(e: Any) -> Any:
    return {"port": e["port"]} if isinstance(e, dict) else e


def emit_scene(level: Json, placed: Placed, model_hash: str) -> Json:
    """Build the scene object of one level."""
    nodes: list[Json] = []
    for n in _preorder(level["nodes"]):
        x, y, w, h = placed.nodes[n["id"]]
        frame = "children" in n and level["level"]["kind"] != "view"
        d: Json = {
            "id": n["id"], "role": n["role"], "type": n["type"], "parent": n["parent"],
            "x": rnd(x), "y": rnd(y), "w": rnd(w), "h": rnd(h), "shape": n["shape"], "style": n["style"],
            "label": {"lines": [_line(ln) for ln in placed.labels[n["id"]]],
                      "anchor": ANCHOR["frame" if frame else n["role"]]},
            "tags": n["tags"], "name": n["name"],
        }
        if "modelId" in n:
            d["modelId"] = n["modelId"]
        if frame:
            d["frame"] = {"scene": "e/" + n["id"], "scale": placed.scales[n["id"]], "children": n["children"]}
            if "childType" in n:
                d["frame"]["childType"] = n["childType"]
        nodes.append(d)
    edges: list[Json] = []
    for e in sorted(level["edges"], key=lambda k: k["id"]):
        pe = placed.edges[e["id"]]
        d = {
            "id": e["id"], "source": _end(e["source"]), "target": _end(e["target"]),
            "points": [[rnd(x), rnd(y)] for x, y in pe["points"]],
            "count": len(e["rels"]), "rels": sorted(e["rels"]), "style": e["style"],
        }
        if "label" in pe:
            lab = pe["label"]
            d["label"] = {"lines": [_line(ln) for ln in lab["lines"]],
                          "x": rnd(lab["x"]), "y": rnd(lab["y"]), "w": rnd(lab["w"]), "h": rnd(lab["h"])}
        if e.get("order") is not None:
            d["order"] = e["order"]
        edges.append(d)
    layout: Json = {
        "engine": "elkjs", "version": ELK_VERSION, "inputHash": placed.input_hash, "passes": max(1, placed.passes),
        "options": placed.options,
    }
    if placed.fallback:
        layout["fallback"] = placed.fallback
    return {
        "schema": SCENE_SCHEMA, "key": level["key"], "level": level["level"], "title": level["title"],
        "modelHash": model_hash, "layout": layout, "bounds": [rnd(v) for v in placed.bounds],
        "ports": [{"id": p["id"], "x": rnd(p["x"]), "y": rnd(p["y"]), "side": p["side"]} for p in placed.ports],
        "nodes": nodes, "edges": edges,
    }


def scene_path(key: str, h8: str) -> str:
    """Relative path (under the data dir) of the scene file of ``key``."""
    return f"scene/{key}.{h8}.json"


def model_path(h8: str) -> str:
    """Relative path (under the data dir) of the model file; the hash in the name keeps two deploys apart."""
    return f"model.{h8}.json"


def _write_bytes(path: str, data: bytes) -> None:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "wb") as f:
        f.write(data)


def write_site(out_dir: str, model: Json, levels: Json, placed: dict[str, Placed]) -> Json:
    """Write model.<h8>.json, index.json and every scene into ``out_dir``. Returns the index object."""
    model_bytes = dumps(model).encode("utf-8")
    model_digest = hashlib.sha256(model_bytes).hexdigest()
    model_rel = model_path(model_digest[:8])
    _write_bytes(os.path.join(out_dir, model_rel), model_bytes)
    index: Json = {
        "schema": INDEX_SCHEMA, "modelHash": model["modelHash"],
        "model": {"file": model_rel, "hash": "sha256:" + model_digest},
        "scenes": {},
    }
    for level in levels["levels"]:
        data = dumps(emit_scene(level, placed[level["key"]], model["modelHash"])).encode("utf-8")
        digest = hashlib.sha256(data).hexdigest()
        rel = scene_path(level["key"], digest[:8])
        _write_bytes(os.path.join(out_dir, rel), data)
        index["scenes"][level["key"]] = {"file": rel, "hash": "sha256:" + digest}
    _write_bytes(os.path.join(out_dir, "index.json"), dumps(index).encode("utf-8"))
    return index
