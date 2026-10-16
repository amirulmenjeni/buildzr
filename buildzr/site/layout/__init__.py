"""Stage 1 of the site build: levels + model -> scenes (design note v4, sections C and I).

``layout_site(levels, model, out_dir)`` lays out the landscape and every element level with the
three-pass reserved-frame layout and every authored view with a single plain pass, then writes
``model.json``, ``index.json`` and the scene files into ``out_dir``.

Command line: ``python -m buildzr.site.layout --data DIR [--k 4]`` reads ``DIR/levels.json`` and
``DIR/model.json`` and writes the rest into ``DIR``.
"""

from __future__ import annotations

import time
from typing import Any

from buildzr.site.layout.elk import ELK_VERSION, ElkError, ElkRunner
from buildzr.site.layout.passes import Layouter
from buildzr.site.scene import write_site

__all__ = ["layout_site", "ElkError", "ELK_VERSION"]

Json = dict[str, Any]


def layout_site(levels: Json, model: Json, out_dir: str, k: float = 4.0) -> Json:
    """Lay out ``levels`` and write the data dir ``out_dir``.

    Args:
        levels: A ``buildzr.levels/2`` object.
        model: The ``buildzr.model/2`` object the levels were made from.
        out_dir: Directory to write ``model.json``, ``index.json`` and ``scene/`` into.
        k: Frame budget: a reserved frame has at most ``k`` times the area of a leaf box.

    Returns:
        Timings and metrics: ``elk_ms`` (in-process ELK time, per pass and total), ``wall_ms``,
        ``scenes``, ``elk_graphs`` and the landscape edge lengths with pinned (final) and
        unpinned (pass 2) ports.
    """
    t0 = time.perf_counter()
    if levels["modelHash"] != model["modelHash"]:
        raise ValueError(f"levels were made from {levels['modelHash']}, model is {model['modelHash']}")
    with ElkRunner() as runner:
        lay = Layouter(levels, runner, k=k)
        lay.layout_generated()
        lay.layout_views()
        elk_ms = runner.total_ms
        graphs = runner.calls
    write_site(out_dir, model, levels, lay.placed)
    return {
        "scenes": len(lay.placed),
        "elk_graphs": graphs,
        "elk_ms": round(elk_ms, 1),
        "elk_ms_by_pass": {n: round(v, 1) for n, v in sorted(lay.timings.items())},
        "wall_ms": round((time.perf_counter() - t0) * 1000, 1),
        "landscape_edge_len_pinned": round(lay.final_landscape_len, 1),
        "landscape_edge_len_unpinned": round(lay.pass2_landscape_len, 1),
        "k": k,
    }
