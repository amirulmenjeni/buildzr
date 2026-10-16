# Viewer spike (throwaway, local branches only)

Answers design-viewer-v3 section J. The lead integrates on `spike/integration`.
The workers branch from it and own disjoint paths, so merges do not conflict.

| Path | Owner | Branch |
|---|---|---|
| `spike/schema/`, `spike/fixtures/`, `spike/tools/scene_io.py`, `spike/tools/check_scene.py`, `spike/README.md` | lead | spike/integration |
| `spike/layout/` (node + elkjs 0.12.0), `spike/scene/` (Python), `spike/out/scenes/` | worker A | spike/scene-elk |
| `spike/viewer/` (Vite + React + @xyflow/react) | worker B | spike/viewer |
| `buildzr/dsl/dsl.py`, `buildzr/dsl/relations.py` (tag order), `spike/determinism/`, `spike/tools/font_metrics.py` (+ data file next to it) | worker C | spike/determinism |

Do not edit a path that another worker owns. If you need a contract change, ask the lead.

## Scene graph contract (`buildzr.scene/1`)

The schema is `spike/schema/scene.schema.json` and the hand-written example is
`spike/fixtures/aws-mini.scene.json` (regenerate with `make_fixture.py`). Rules
that the schema cannot express are checked by `spike/tools/check_scene.py`:

- **Absolute coordinates**, y down, rounded to 0.01 with `scene_io.rnd` (integers written without `.0`, no `-0`).
- **Node order:** pre-order depth-first, so every parent comes before its children. Siblings are sorted by `id`.
- **Edge order:** sorted by `id`.
- **Containment:** a child rectangle lies inside its parent rectangle. Only `role: "boundary"` nodes have children.
- **IDs:** path slugs (`live/amazon-web-services/ap-southeast-1/dns-router`), lower-case `[a-z0-9._-]` segments joined by `/`. `slug(name)` = lower-case, runs of other characters become `-`, strip `-`. Collision: append `-2`, `-3`, … in model order. Deployment elements are rooted at the environment slug (`live/...`). Edge id = `source->target`, plus `:slug(description)` only when a pair has several. buildzr's numeric id goes in `modelId`.
- **Edge points:** absolute polyline `[start, bend..., end]` taken from ELK sections. Note that ELK reports edge coordinates relative to the edge's container; try `"org.eclipse.elk.json.edgeCoords": "ROOT"` and `"org.eclipse.elk.json.shapeCoords": "ROOT"` first, and verify against a manual conversion.
- **Canonical bytes:** `scene_io.dumps` (sorted keys, compact, UTF-8, trailing `\n`). Every hash is `sha256:` + hex of canonical bytes.
- **Labels are pre-wrapped** with `spike/tools/font_metrics.py` (`measure`, `wrap`, `LINE_HEIGHT`). Renderers must not re-wrap.
- **Tags** keep the order they have in the model. Do not sort them in the scene stage, so that the tag-order fix shows end to end.

Check a file: `python3 -I spike/tools/check_scene.py FILE...`. To include the JSON
schema, run it with `uvx --from jsonschema==4.23.0 python spike/tools/check_scene.py FILE...`.

## Environment rules (all workers)

- Stay inside the agents working directory (`<agents-dir>`). Export these before running npm, npx, playwright or uv, so caches stay there too:
  `export npm_config_cache=<cache-dir>/npm PLAYWRIGHT_BROWSERS_PATH=<cache-dir>/ms-playwright UV_CACHE_DIR=<cache-dir>/uv`
- No git push, no PRs, no `gh` writes, no global installs, no sudo. Commit locally on your own branch only.
- buildzr examples call `save()` at import time. Run them with the cwd set to a temporary directory (`mktemp -d` under `<cache-dir>/tmp/`), never from a repo root.
- Run buildzr through the worktree's uv project (`uv run --project <your worktree> python ...`). The repo's own test suite (`pytest`) runs in the devcontainer (see AGENTS.md); the spike scripts run on the macOS host because the spike measures macOS.
