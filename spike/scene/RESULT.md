# Worker A result: scene graph + ELK from real DSL views

Machine: Apple M4 Pro, node v26.9.0, elkjs 0.12.0 (pinned exact, package-lock committed), buildzr from this worktree (CPython 3.10 via uv).

## Reproduce

```bash
export npm_config_cache=<cache-dir>/npm UV_CACHE_DIR=<cache-dir>/uv
(cd spike/layout && npm ci)
uv run --project <worktree> python spike/scene/build_scenes.py   # all views; --only VIEW... for a subset
uvx --from jsonschema==4.23.0 python spike/tools/check_scene.py spike/out/scenes/*.scene.json            # all 5 OK
```
Timings land in `spike/scene/metrics.json` (not deterministic, kept out of `spike/out/scenes/`).
Views: `aws-deployment-view`, `x_context_00` (amazon_web_services.py), `web_app_container_view_00`, `web_app_system_context_00` (system_context_and_container_view.py), `synthetic-120`.

## Timings (one run, ms)

| view | nodes/edges | ELK in-process, median of 5 | ELK first run (cold, in-process) | node process wall (1 run) |
|---|---|---|---|---|
| aws-deployment-view | 19 / 6 | 13.6 | 50.3 | 139.7 |
| x_context_00 | 2 / 1 | 5.0 | 33.8 | 120.9 |
| web_app_container_view_00 | 4 / 1 | 5.8 | 34.9 | 125.6 |
| web_app_system_context_00 | 4 / 1 | 6.5 | 38.0 | 122.3 |
| synthetic-120 | 120 / 200 | 510.4 | 613.7 | 703.1 |

Total `build_scenes.py` wall time for all 5 views: 4.6 s. That includes running the two example files, and spawning node twice per view (once for the single run, once for `--repeat 5`).
Node startup plus the 1.6 MB bundle load is about 90-100 ms; that is most of the wall time on small views.

## Determinism

Four runs: two plain, `PYTHONHASHSEED=1`, `PYTHONHASHSEED=2`; `shasum` per file.
- `synthetic-120` was byte-identical in all four runs.
- The four DSL-derived views differ in every run, even with unset seed. After removing `tags` and `modelHash` from both files the scenes are identical (checked for x_context_00 and aws-deployment-view across two runs): geometry, ids, styles, `inputHash` and edge points are stable.
- Two causes, both in the model and not in the scene stage:
  1. Tag order within one element changes with the hash seed (e.g. `["Element","Person"]` vs `["Person","Element"]`). This is the expected worker C fix.
  2. `modelHash` changes because the Structurizr JSON contains random `buildzr-styleelements-<uuid4>` style tags (appear in `tags` and in `configuration.styles`). Second source of non-determinism that the tag-order fix alone will not remove. The new tag in `tags` also shows in the diff (`buildzr-styleelements-14423eae…` vs `…80c698dd…`).
- I did not re-run the same seed twice (uuids would differ anyway).

## Geometry (programmatic, `geometry_report` in build_scenes.py)

| view | size px (w x h) | max edge-endpoint gap to source/target border | sibling overlaps | edge labels overlapping elements | label/label overlaps |
|---|---|---|---|---|---|
| aws-deployment-view | 1821.36 x 788 | 0.0 | 0 | 0 | 0 |
| x_context_00 | 264 x 456.75 | 0 | 0 | 0 | 0 |
| web_app_container_view_00 | 826.88 x 288 | 0 | 0 | 0 | 0 |
| web_app_system_context_00 | 923.28 x 216 | 0 | 0 | 0 | 0 |
| synthetic-120 | 22089.89 x 12401 | 0.0 | 0 | 0 | 0 |

- Containment: `check_scene.py` passes on all five (tolerance 0.5 px).
- Edge coordinates: set `org.eclipse.elk.json.edgeCoords` and `shapeCoords` to `ROOT` and put all edges at the root. I checked that it matters: for the AWS view the first edge starts at (292,168) with ROOT but (260,132) with CONTAINER or INHERIT (offset 32,36 = the region's origin), so the border-gap check is not vacuous. With ROOT every endpoint lies exactly on the border (gap 0.0, max over all endpoints).
- Edge labels are ELK-placed (`labels` on each edge); none overlaps an element box. I counted only element-role nodes, not boundary corner labels.
- AWS scene: 1821 x 788 px including 12 px margin (the v1 dagre/ELK comparison in the draft had 2720 x 941 with other settings).

## Not verified / looks wrong

- No visual check (nothing rendered). Only numbers.
- `synthetic-120` is 22090 x 12401 px: usable for timing and for stress-testing the viewer, but not a readable picture. Edges mostly cross boundaries; spacing is generous (nodeNode 40, between layers 80). Not tuned.
- Boundary label fit: the boundary gets a minimum size from its label width (`elk.nodeSize.minimum`), the label itself is drawn bottom-left in 48 px bottom padding. I did not check that long labels fit when ELK makes the box wider than the minimum, or that edges avoid the label area.
- Group boundaries: implemented (same-scope group names; skipped when equal to the parent's own group), but the container view with groups was only inspected through the geometry numbers, not by eye. In `web_app_container_view_00` the group "My Company" wraps the system boundary (4 nodes).
- Container view: the example lists only the 2 containers; the system boundary is added by me from `softwareSystemId`. People/other systems appear only if the view lists them.
- Styles: Structurizr-like defaults (Person #08427b, System #1168bd, Container #438dd5, Component #85bbf0) and tag styles `background/color/stroke/shape/fontSize/opacity/strokeWidth/border`; relationship `color/thickness/style/dashed/fontSize/opacity`. Tag precedence: Element, type tag, then the rest in model order; container instances also inherit the container's tags for styling (so the AWS Database instance is a Cylinder). `stroke` default is the fill darkened to 70%. Not compared with Structurizr's real rendering. Style `width/height` of element and `metadata/description` toggles are ignored.
- Element sizing uses the stub font metrics (0.56/0.60 em); will change when worker C's real table lands, and `inputHash` with it.
- Dynamic views, component views and `link.view` are not produced. Component view path is implemented but untested.
- ELK in-process times come from a single machine, one session; the "first run" column includes JIT warm-up.

---

# Follow-up: locality variant and spacing tuning

## Variants

- `synthetic-120` (new default): same 120 nodes (24 boundaries over 3 levels, 96 elements) and 200 edges, but each edge's target is picked inside the source's top-level boundary with probability 0.7. Measured: 147 of 200 edges (73.5%) stay inside one top-level boundary.
- `synthetic-120-dense`: the previous generator (random leaf pairs), unchanged and byte-identical in structure to the first `synthetic-120`.
- Both are deterministic (`random.Random(42)`); both were byte-identical between a default run and a `PYTHONHASHSEED=7` run.

## Spacing experiments

Run: `uv run --project <worktree> python spike/scene/tune_spacing.py [letters]`. Each row is relative to the first-commit defaults (nodeNode 40, between layers 80, edgeNode 20/20, edgeEdge 15/15, considerModelOrder NODES_AND_EDGES, DOWN, ORTHOGONAL) with only the listed options changed. Size = scene bounds in px, ELK = in-process median of 5 (ms; run-to-run noise is about +-15%). Every row had max endpoint gap 0.0, 0 sibling overlaps and 0 label/element overlaps.

| set | options | synthetic-120 px | ms | dense px | ms |
|---|---|---|---|---|---|
| A | baseline | 10771 x 12322 | 228 | 22090 x 12401 | 542 |
| B | nodeNode 25, layers 40 | 10771 x 12312 | 241 | 22090 x 12401 | 563 |
| C | nodeNode 20, layers 40 | 10771 x 12312 | 218 | 22090 x 12401 | 619 |
| D | B + edgeNode 10, edgeEdge 10 | 10576 x 11862 | 221 | 21260 x 11171 | 561 |
| E | B + aspectRatio 1.6 | 10771 x 12312 | 240 | 22090 x 12401 | 529 |
| F | B + aspectRatio 1.6 + wrapping MULTI_EDGE | 10771 x 12312 | 217 | 22090 x 12401 | 556 |
| G | B, considerModelOrder NONE | 8491 x 12067 | 263 | 19975 x 12271 | 309 |
| H | G + edgeNode 10, edgeEdge 10 | **8236 x 11682** | 232 | **18979 x 11041** | 307 |
| I | G + direction RIGHT | 19475 x 4577 | 236 | 16565 x 9975 | 298 |
| J | G + layering LONGEST_PATH | 8491 x 12067 | 239 | 19113 x 12646 | 313 |
| K | G + layering COFFMAN_GRAHAM | 9977 x 12112 | 226 | 20679 x 12346 | 358 |
| L | G + aspectRatio 1.6 + wrapping MULTI_EDGE | 8491 x 12067 | 228 | 19975 x 12271 | 306 |
| M | G + aspectRatio 1.6 + wrapping SINGLE_EDGE | 8491 x 12067 | 237 | 19975 x 12271 | 326 |
| N | G + POLYLINE routing | 8655 x 17624 | 247 | 20052 x 29581 | 295 |
| O | G + SPLINES routing | 8655 x 14170 | 243 | 20052 x 17120 | 335 |
| P | H + direction RIGHT | 19100 x 4325 | 269 | 15485 x 9096 | 301 |

Findings:
- Node and layer spacing hardly change the size (A to C). `aspectRatio` and `wrapping` had no effect at all on these graphs (E, F, L, M): sizes are identical to their base rows. I did not find out why.
- The only large effect is `considerModelOrder` NONE instead of NODES_AND_EDGES: -21% width on the local variant, -10% on the dense one, and dense ELK time drops from about 550 to about 305 ms. Edge spacing 10 then gives another 3-6%.
- The layout is still 8000-19000 px wide and 11000-12000 px tall. My hypothesis (not verified) is that this is layer count: random edges among 96 nodes give long chains, and a layered layout needs about one 240+ px layer per hop, so the size follows the longest path and not the spacing. Real C4 views are much shallower; the 70% locality barely changes that. A fairer next test would be a generator with a bounded depth.
- POLYLINE and SPLINES routing were taller than ORTHOGONAL; I kept ORTHOGONAL.

## Picked

Set **H** is now the default for all views: nodeNode 25, nodeNodeBetweenLayers 40, edgeNode 10, edgeNodeBetweenLayers 10, edgeEdge 10, edgeEdgeBetweenLayers 10, `considerModelOrder.strategy` NONE, ORTHOGONAL, direction from the view. `LAYOUT_OVERRIDES` in `build_scenes.py` changes root options for experiments. Direction RIGHT (P) gives a smaller area, but it would be a per-view choice and I left the synthetic views on DOWN. Caveat on H: dropping model order means siblings are not guaranteed to follow the order in the model; I did not check the effect on the small views by eye. x_context_00 got shorter (456 -> 377 px) and web_app_system_context_00 narrower (923 -> 843 px); the AWS view is the same size (1821 x 788).

## Re-check with the new defaults

`check_scene.py` (with jsonschema 4.23.0): all 6 scenes OK.

| view | size px | ELK median ms | node wall ms | gap | sibling overlaps | labels over elements |
|---|---|---|---|---|---|---|
| aws-deployment-view | 1821.36 x 788 | 13.3 | 143 | 0.0 | 0 | 0 |
| x_context_00 | 264 x 376.75 | 5.1 | 125 | 0 | 0 | 0 |
| web_app_container_view_00 | 826.88 x 288 | 5.5 | 128 | 0 | 0 | 0 |
| web_app_system_context_00 | 843.28 x 216 | 6.2 | 129 | 0 | 0 | 0 |
| synthetic-120 | 8236.04 x 11681.75 | 259 | 468 | 0.0 | 0 | 0 |
| synthetic-120-dense | 18978.79 x 11041 | 319 | 555 | 0.0 | 0 | 0 |

`index.json` now lists 6 views. Label/label overlaps are 0 everywhere. Not verified: the scenes were not rendered.

---

# Follow-up 2: text contrast fix and DAG hypothesis

## (1) White text on white fill

Cause: DEFAULTS used white text for most types and only an explicit `color` in a style overrode it, so a style that sets just `background: #ffffff` kept white text. Fix in `resolve_styles`: when no tag style sets `color`, text is `#000000` or `#ffffff`, whichever has the higher WCAG contrast ratio against the resolved fill. An explicit style `color` is always respected. The geometry report has a new `low_contrast_nodes` count (nodes with ratio < 4.5 between `style.color` and `style.fill`).

Result: `aws-deployment-view` and `x_context_00` now have fill `#ffffff`, color `#000000`. `low_contrast_nodes` is 0 for the four real views. It is **24 for both synthetic views**: these are the `Billing`-tagged elements: I checked that exactly 24 nodes in `synthetic-120` have text `#ffeb3b`, the explicit colour the test style gives that tag. I left the synthetic styles alone. All 6 scenes pass `check_scene.py`. Default-colour nodes on dark fills (Person, System, Container) still get white text; Component (#85bbf0) gets black text.

## (2) Are the synthetic widths caused by cycles (feedback edges)?

`spike/scene/dag_test.py` (prints this table; variants are not written to `out/scenes`). DAG = each edge oriented from the lower to the higher leaf index, so no cycles. "Outside" = edges having any point beyond the bounding box of all nodes, on any side (so the count is wider than the lead's 68 "left of every node").

| variant | size px | node extent (w x h) | edges with a point outside node extent | ELK median ms |
|---|---|---|---|---|
| synthetic-120 (cyclic) | 8236 x 11682 | 6333 x 11548 | 26 of 200 | 223 |
| synthetic-120 DAG | 11573 x 12323 | 10115 x 12189 | 18 of 200 | 216 |
| synthetic-120-dense (cyclic) | 18979 x 11041 | 12431 x 10717 | 83 of 200 | 282 |
| synthetic-120-dense DAG | 19466 x 10981 | 13535 x 10657 | 80 of 200 | 279 |

Verdict: **the hypothesis is not supported.** Removing the cycles does not make the layout narrower: the DAG variants are as wide or wider (11573 vs 8236 and 19466 vs 18979), and 18 and 80 edges still have points outside the node extent. Feedback edges can account for some of those outside edges (the cyclic variants have more of them in the local case, 26 vs 18) but not for the size. Part of the size comes from the nodes themselves: even the node extent alone is 6300-13500 px wide. What does cause the outside edges was not investigated; candidates are edges that cross boundaries (ELK routes them around the hierarchy) and the layer count I guessed at earlier, but neither was tested. The earlier single-seed caveat applies: one seed per variant, and the DAG orientation also changes which pairs the generator accepts.

## (1b) Unfilled boundaries

Boundaries (role=boundary) now default to fill `#ffffff`, with the type colour as stroke (software-system boundary: `#1168bd`; deployment nodes and groups have a white/neutral type colour, so they keep stroke `#888888`) and dark text from the contrast rule. A style that explicitly sets `background` for one of the boundary's tags still wins, and then the stroke is `#888888` unless a style sets it. `web_app_container_view_00`: the "Corporate Web App" boundary is now fill `#ffffff`, stroke `#1168bd`, text `#000000`. AWS deployment nodes are unchanged. The synthetic views still show some filled boundaries (and 24 low-contrast nodes) because their test styles set `background`/`color` on tags such as `Legacy`, `External` and `Billing`, which the boundaries also carry. All 6 scenes pass `check_scene.py`. Not rendered.
