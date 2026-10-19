"""SPIKE: run a docs snippet and build its viewer data in the browser (Pyodide), with no Node and no subprocess.

The same Python stages as ``buildzr build`` run here: ``export_model`` -> ``build_levels`` -> ``Layouter`` (the three-pass
layout) -> ``write_workspace``. Only the ELK runner differs: instead of a Node subprocess it calls the JS function
``elkLayoutSync`` (the same elkjs 0.12.0 bundle, called synchronously in this JS realm).
"""

from __future__ import annotations

import json
import os
import re
import shutil
import time
from typing import Any

import js  # type: ignore[import-not-found]  # Pyodide only

from buildzr.dsl import Workspace
from buildzr.dsl.factory import GenerateId
from buildzr.site.layout.passes import Layouter
from buildzr.site.levels import build_levels
from buildzr.site.model import DRAWN_TYPES, export_model
from buildzr.site.scene import write_workspace

Json = dict[str, Any]


class JsElkRunner:
    """Same interface as :class:`buildzr.site.layout.elk.ElkRunner`, backed by elkjs in this JS realm."""

    def __init__(self) -> None:
        self.total_ms = 0.0
        self.calls = 0

    def layout(self, graphs: dict[str, Json]) -> dict[str, Json]:
        if not graphs:
            return {}
        resp = json.loads(js.elkLayoutSync(json.dumps(graphs, separators=(",", ":"))))
        out: dict[str, Json] = {}
        for name, r in resp.items():
            if "error" in r:
                raise RuntimeError(f"ELK failed on {name}: {r['error']}")
            self.total_ms += float(r["ms"])
            out[name] = r["graph"]
        self.calls += len(out)
        return out


FOCUS = re.compile(r"^\s*#\s*focus:\s*(\S+)\s*$", re.M)
#: View kinds the model canvas cannot show: a snippet that defines one of these is about that view.
OWN_CANVAS = ("deployment", "dynamic")


def focus_for(code: str, model: Json) -> Json:
    """Where the viewer opens for a snippet: ``{"route": "#/...", "why": ...}``.

    1. ``# focus: <element id>`` (the viewer's id, e.g. ``shop/api``) or ``# focus: view:<key>``: that.
    2. The snippet defines a deployment or dynamic view: the first such view (the model canvas cannot show it).
    3. Otherwise the model canvas, with the last-created element that has children expanded (its ancestors too).
    4. Nothing has children: the whole landscape.
    """
    ids = {e["id"] for e in model["elements"]}
    m = FOCUS.search(code)
    if m:
        target = m.group(1)
        if target.startswith("view:"):
            key = target[5:]
            if key not in {v["key"] for v in model["views"]}:
                raise ValueError(f"# focus: no view {key!r}")
            return {"route": "#/v/" + key, "why": "marker"}
        if target not in ids:
            raise ValueError(f"# focus: no element {target!r}; ids: {sorted(ids)}")
        el = next(e for e in model["elements"] if e["id"] == target)
        path = target if el["children"] else (el["parent"] or "")
        return {"route": f"#/m/{path}?sel={target}" if path else f"#/m?sel={target}", "why": "marker"}
    own = [v for v in model["views"] if v["kind"] in OWN_CANVAS]
    if own:
        return {"route": "#/v/" + own[0]["key"], "why": f"{own[0]['kind']} view"}
    drawn = [e for e in model["elements"] if e["type"] in DRAWN_TYPES and e["children"]]
    if drawn:
        last = max(drawn, key=lambda e: int(e["modelId"]) if str(e["modelId"]).isdigit() else -1)
        return {"route": "#/m/" + last["id"], "why": "last element with children"}
    return {"route": "#/m", "why": "landscape"}


def run_snippet(code: str, out_dir: str = "/rc/out", k: float = 4.0) -> str:
    """Execute ``code``, build the last workspace it made into ``out_dir``; return a JSON summary with every file."""
    created: list[Any] = []
    orig = Workspace.__init__

    def rec(self: Any, *a: Any, **kw: Any) -> None:
        orig(self, *a, **kw)
        created.append(self)

    GenerateId.reset()  # ids start at 1 for every snippet, as in a fresh process
    Workspace.__init__ = rec  # type: ignore[method-assign]
    t0 = time.perf_counter()
    try:
        exec(compile(code, "<snippet>", "exec"), {"__name__": "__main__"})
    finally:
        Workspace.__init__ = orig  # type: ignore[method-assign]
    if not created:
        raise RuntimeError("the snippet created no Workspace")
    t1 = time.perf_counter()
    ws = created[-1]
    model = export_model(ws)
    levels = build_levels(ws, model, text_color="wcag")
    t2 = time.perf_counter()
    runner = JsElkRunner()
    lay = Layouter(levels, runner, k=k)  # type: ignore[arg-type]
    lay.layout_generated()
    lay.layout_views()
    t3 = time.perf_counter()
    shutil.rmtree(out_dir, ignore_errors=True)
    index = write_workspace(out_dir, model, levels, lay.placed)
    files: dict[str, str] = {}
    for root, _dirs, names in os.walk(out_dir):
        for n in names:
            p = os.path.join(root, n)
            with open(p, encoding="utf-8") as f:
                files[os.path.relpath(p, out_dir)] = f.read()
    t4 = time.perf_counter()
    return json.dumps({
        "files": files,
        "index": index,
        "focus": focus_for(code, model),
        "workspace_json": ws.to_json(),
        "elements": [{"id": e["id"], "type": e["type"], "name": e["name"]} for e in model["elements"]],
        "views": [{"key": v["key"], "kind": v["kind"]} for v in model["views"]],
        "scenes": {key: len(lay.placed[key].nodes) for key in lay.placed},
        "ms": {"exec": round((t1 - t0) * 1000, 1), "export": round((t2 - t1) * 1000, 1),
               "layout": round((t3 - t2) * 1000, 1), "elk": round(runner.total_ms, 1),
               "write": round((t4 - t3) * 1000, 1), "elk_graphs": runner.calls},
    })
