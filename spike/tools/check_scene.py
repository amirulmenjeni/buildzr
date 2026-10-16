"""Check a scene file against the contract that the JSON schema cannot express.

Usage: python3 -I spike/tools/check_scene.py FILE [FILE ...]
Exit 0 when every file passes. Uses `jsonschema` for the schema itself when it is
importable, otherwise only the checks below (stdlib only).
"""
from __future__ import annotations

import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from scene_io import SCHEMA, dumps  # noqa: E402

SCHEMA_FILE = os.path.join(os.path.dirname(__file__), "..", "schema", "scene.schema.json")
EPS = 0.5  # containment tolerance in px


def _is_rounded(v: float) -> bool:
    return abs(v * 100 - round(v * 100)) < 1e-6


def check(path: str) -> list[str]:
    errs: list[str] = []
    raw = open(path, encoding="utf-8").read()
    scene = json.loads(raw)
    if raw != dumps(scene):
        errs.append("bytes are not canonical (sort_keys, compact separators, trailing newline)")
    try:
        import jsonschema  # type: ignore

        schema = json.load(open(SCHEMA_FILE, encoding="utf-8"))
        for e in jsonschema.Draft202012Validator(schema).iter_errors(scene):
            errs.append(f"schema: {list(e.absolute_path)}: {e.message}")
    except ImportError:
        if scene.get("schema") != SCHEMA:
            errs.append(f"schema must be {SCHEMA!r}")

    nodes = scene.get("nodes", [])
    by_id: dict[str, dict] = {}
    for i, n in enumerate(nodes):
        nid = n["id"]
        if nid in by_id:
            errs.append(f"duplicate node id {nid}")
        p = n["parent"]
        if p is not None:
            if p not in by_id:
                errs.append(f"node {nid}: parent {p} missing or listed after child (pre-order required)")
            else:
                pn = by_id[p]
                if pn["role"] != "boundary":
                    errs.append(f"node {nid}: parent {p} is not a boundary")
                if not (n["x"] >= pn["x"] - EPS and n["y"] >= pn["y"] - EPS
                        and n["x"] + n["w"] <= pn["x"] + pn["w"] + EPS
                        and n["y"] + n["h"] <= pn["y"] + pn["h"] + EPS):
                    errs.append(f"node {nid} not contained in parent {p}")
        for k in ("x", "y", "w", "h"):
            if not _is_rounded(n[k]):
                errs.append(f"node {nid}.{k}={n[k]} not rounded to 0.01")
        by_id[nid] = n

    # siblings sorted by id
    seen_parent_order: dict[object, str] = {}
    for n in nodes:
        prev = seen_parent_order.get(n["parent"])
        if prev is not None and prev > n["id"]:
            errs.append(f"siblings under {n['parent']} not sorted: {prev} before {n['id']}")
        seen_parent_order[n["parent"]] = n["id"]

    edges = scene.get("edges", [])
    ids = [e["id"] for e in edges]
    if ids != sorted(ids):
        errs.append("edges not sorted by id")
    if len(set(ids)) != len(ids):
        errs.append("duplicate edge id")
    for e in edges:
        for end in ("source", "target"):
            if e[end] not in by_id:
                errs.append(f"edge {e['id']}: {end} {e[end]} not a node")
        for pt in e["points"]:
            if not all(_is_rounded(c) for c in pt):
                errs.append(f"edge {e['id']}: point {pt} not rounded")
        bx, by, bw, bh = scene["bounds"]
        for pt in e["points"]:
            if not (bx - EPS <= pt[0] <= bx + bw + EPS and by - EPS <= pt[1] <= by + bh + EPS):
                errs.append(f"edge {e['id']}: point {pt} outside bounds")
    return errs


def main(argv: list[str]) -> int:
    bad = 0
    for path in argv:
        errs = check(path)
        status = "OK" if not errs else f"FAIL ({len(errs)})"
        print(f"{status}  {path}")
        for e in errs[:50]:
            print(f"    {e}")
        bad += bool(errs)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
