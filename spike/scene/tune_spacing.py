"""Spacing experiments: python tune_spacing.py  (prints a markdown table). Uses build_scenes.LAYOUT_OVERRIDES."""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import build_scenes as b

# Defaults of the first commit; the sets below are measured relative to these (build_scenes.py defaults have since changed to set H).
BASE = {"elk.spacing.nodeNode": "40", "elk.layered.spacing.nodeNodeBetweenLayers": "80", "elk.spacing.edgeNode": "20",
        "elk.layered.spacing.edgeNodeBetweenLayers": "20", "elk.spacing.edgeEdge": "15",
        "elk.layered.spacing.edgeEdgeBetweenLayers": "15", "elk.layered.considerModelOrder.strategy": "NODES_AND_EDGES"}
SETS = {
    "A baseline (nodeNode 40, layers 80)": {},
    "B nodeNode 25, layers 40": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40"},
    "C nodeNode 20, layers 40": {"elk.spacing.nodeNode": "20", "elk.layered.spacing.nodeNodeBetweenLayers": "40"},
    "D B + edgeNode 10, edgeEdge 10": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40",
                                       "elk.spacing.edgeNode": "10", "elk.layered.spacing.edgeNodeBetweenLayers": "10",
                                       "elk.spacing.edgeEdge": "10", "elk.layered.spacing.edgeEdgeBetweenLayers": "10"},
    "E B + aspectRatio 1.6": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.aspectRatio": "1.6"},
    "F B + wrapping MULTI_EDGE ratio 1.6": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40",
                                            "elk.aspectRatio": "1.6", "elk.layered.wrapping.strategy": "MULTI_EDGE"},
    "G B w/o considerModelOrder": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40",
                                   "elk.layered.considerModelOrder.strategy": "NONE"},
    "H G + edge spacing 10": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.spacing.edgeNode": "10", "elk.layered.spacing.edgeNodeBetweenLayers": "10", "elk.spacing.edgeEdge": "10", "elk.layered.spacing.edgeEdgeBetweenLayers": "10"},
    "I G + direction RIGHT": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.direction": "RIGHT"},
    "J G + layering LONGEST_PATH": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.layered.layering.strategy": "LONGEST_PATH"},
    "K G + layering COFFMAN_GRAHAM": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.layered.layering.strategy": "COFFMAN_GRAHAM"},
    "L G + wrapping MULTI_EDGE ratio 1.6": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.aspectRatio": "1.6", "elk.layered.wrapping.strategy": "MULTI_EDGE"},
    "M G + SINGLE_EDGE wrapping ratio 1.6": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.aspectRatio": "1.6", "elk.layered.wrapping.strategy": "SINGLE_EDGE"},
    "N G + POLYLINE routing": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.edgeRouting": "POLYLINE"},
    "O G + SPLINES routing": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.edgeRouting": "SPLINES"},
    "P G + direction RIGHT + edge spacing 10": {"elk.spacing.nodeNode": "25", "elk.layered.spacing.nodeNodeBetweenLayers": "40", "elk.layered.considerModelOrder.strategy": "NONE", "elk.direction": "RIGHT", "elk.spacing.edgeNode": "10", "elk.layered.spacing.edgeNodeBetweenLayers": "10", "elk.spacing.edgeEdge": "10", "elk.layered.spacing.edgeEdgeBetweenLayers": "10"},
}
VIEWS = {"synthetic-120": lambda: b.synthetic_120(), "synthetic-120-dense": lambda: b.synthetic_120(0, "synthetic-120-dense")}
print("| options | view | size px | ELK median ms | gap | overlaps | label/elem overlaps |\n|---|---|---|---|---|---|---|")
for name, ov in SETS.items():
    if len(sys.argv) > 1 and name[0] not in sys.argv[1]: continue
    b.LAYOUT_OVERRIDES.clear(); b.LAYOUT_OVERRIDES.update({**BASE, **ov})
    for v, mk in VIEWS.items():
        scene, rep = b.build(mk())
        print(f"| {name} | {v} | {rep['size_px'][0]:.0f} x {rep['size_px'][1]:.0f} | {rep['elk_median5_ms']} | {rep['max_endpoint_gap_px']} | {rep['sibling_overlaps']} | {rep['edge_labels_overlapping_elements']} |", flush=True)
