"""Cyclic vs DAG-only synthetic variants (not written to out/scenes). Prints a markdown table."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scenes as b

def outside(scene):
    ns = scene["nodes"]
    x0, y0 = min(n["x"] for n in ns), min(n["y"] for n in ns)
    x1, y1 = max(n["x"] + n["w"] for n in ns), max(n["y"] + n["h"] for n in ns)
    return sum(1 for e in scene["edges"] if any(p[0] < x0 - .5 or p[0] > x1 + .5 or p[1] < y0 - .5 or p[1] > y1 + .5 for p in e["points"])), (x0, y0, x1, y1)

print("| variant | size px | node extent (w x h) | edges with a point outside node extent | ELK median ms |\n|---|---|---|---|---|")
for name, mk in [("synthetic-120 (cyclic)", lambda: b.synthetic_120()), ("synthetic-120 DAG", lambda: b.synthetic_120(dag=True)),
                 ("synthetic-120-dense (cyclic)", lambda: b.synthetic_120(0, "d")), ("synthetic-120-dense DAG", lambda: b.synthetic_120(0, "d", dag=True))]:
    sc, rep = b.build(mk())
    o, (x0, y0, x1, y1) = outside(sc)
    print(f"| {name} | {rep['size_px'][0]:.0f} x {rep['size_px'][1]:.0f} | {x1-x0:.0f} x {y1-y0:.0f} | {o} of {rep['edges']} | {rep['elk_median5_ms']} |", flush=True)
