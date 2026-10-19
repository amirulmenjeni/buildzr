"""SPIKE (Question B): build the same wrapped snippets with the normal path (CPython + Node runner) to compare.

    uv run python spike/runcode/cpython_build.py OUT WRAPPED.py...
"""

import json
import os
import sys
import time

from buildzr.dsl import Workspace
from buildzr.dsl.factory import GenerateId
from buildzr.site.layout import layout_workspace
from buildzr.site.levels import build_levels
from buildzr.site.model import export_model

out = sys.argv[1]
for path in sys.argv[2:]:
    name = os.path.splitext(os.path.basename(path))[0]
    created: list = []
    orig = Workspace.__init__

    def rec(self, *a, **kw):  # type: ignore[no-untyped-def]
        orig(self, *a, **kw)
        created.append(self)

    GenerateId.reset()  # ids start at 1 for every snippet, as in a fresh process
    Workspace.__init__ = rec  # type: ignore[method-assign]
    try:
        exec(compile(open(path).read(), path, "exec"), {"__name__": "__main__"})
    except Exception as e:  # noqa: BLE001
        print(json.dumps({"snippet": name, "error": repr(e)}))
        continue
    finally:
        Workspace.__init__ = orig  # type: ignore[method-assign]
    t0 = time.perf_counter()
    model = export_model(created[-1])
    levels = build_levels(created[-1], model, text_color="wcag")
    m = layout_workspace(levels, model, os.path.join(out, name))
    print(json.dumps({"snippet": name, "wall_ms": round((time.perf_counter() - t0) * 1000, 1), "elk_ms": m["elk_ms"]}))
