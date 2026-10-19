"""SPIKE: run a docs snippet and build its viewer data in the browser (Pyodide), with no Node and no subprocess.

The same Python stages as ``buildzr build`` run here: ``export_model`` -> ``build_levels`` -> ``Layouter`` (the three-pass
layout) -> ``write_workspace``. Only the ELK runner differs: instead of a Node subprocess it calls the JS function
``elkLayoutSync`` (the same elkjs 0.12.0 bundle, called synchronously in this JS realm).
"""

from __future__ import annotations

import json
import os
import shutil
import time
from typing import Any

import js  # type: ignore[import-not-found]  # Pyodide only

from buildzr.dsl import Workspace
from buildzr.dsl.factory import GenerateId
from buildzr.site.layout.passes import Layouter
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model
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
        "elements": [{"id": e["id"], "type": e["type"], "name": e["name"]} for e in model["elements"]],
        "views": [{"key": v["key"], "kind": v["kind"]} for v in model["views"]],
        "scenes": {key: len(lay.placed[key].nodes) for key in lay.placed},
        "ms": {"exec": round((t1 - t0) * 1000, 1), "export": round((t2 - t1) * 1000, 1),
               "layout": round((t3 - t2) * 1000, 1), "elk": round(runner.total_ms, 1),
               "write": round((t4 - t3) * 1000, 1), "elk_graphs": runner.calls},
    })
