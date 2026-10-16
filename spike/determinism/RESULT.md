# Determinism spike (worker C)

Branch `spike/determinism`. macOS (arm64, CPython 3.10.20) host, plus one Linux data point from the devcontainer (aarch64, 3.10.21). Windows not tested.

## 1. Problem evidence (`before.txt`, unmodified code, seeds 1 vs 2)
`seeds.py` runs 5 examples (all ran; none skipped) in subprocesses with `PYTHONHASHSEED=n`, stubbing `Workspace.save` to capture `w.to_json()` (the examples otherwise write files, `workspace_extension.py` writes next to itself).
All 5 files differ, unmasked and masked:

| example | differing lines (unmasked / masked) |
|---|---|
| amazon_web_services | 44 / 38 |
| deployment_groups | 14 / 14 |
| dynamic_view | 32 / 32 |
| system_context_and_container_view | 10 / 10 |
| workspace_extension | 4 / 4 |

Typical: `"Element,Person"` vs `"Person,Element"`; `"Amazon Web Services - EC2 Instance,Element,Deployment Node"` vs `"Deployment Node,Amazon Web Services - EC2 Instance,Element"`. Unmasked also shows random `buildzr-styleelements-<uuid4 hex>` tags (`--mask-uuids` masks dashed UUIDs and bare 32-hex runs).

## 2. What changed
- `buildzr/dsl/relations.py`: new generic `OrderedSet[T]` (a `set` subclass with a side `dict`, so `__iter__` is insertion-ordered) and alias `OrderedTags = OrderedSet[str]`. `_Relationship._tags` uses it. Existing `','.join(self._tags)` sites then become deterministic unchanged; so does `add_tags` in `interfaces/interfaces.py` (not my file, it does `','.join(self.tags)` and `self.tags.update`, which work through the subclass).
- `buildzr/dsl/dsl.py`:
  - `_tags` of SoftwareSystem, Person, DeploymentNode-like `Element`, Container, Component, DeploymentNode, InfrastructureNode, SoftwareSystemInstance, ContainerInstance, and the 5 `_from_model` constructors (split of `model.tags`) use `OrderedTags`. Default tags stay first (`Element,Person`).
  - `_relationships` of the same element classes is an `OrderedSet` (set iteration of relationship objects hashed by address made view relationship lists vary between runs, seen in `workspace_extension`, masked run).
  - `DynamicView`: `element_ids` set of strings (seed dependent) became an insertion-ordered dict (`dsl.py` ~2942/2993/3006).
  - `StyleElements` / `StyleRelationships`: `uuid4()` replaced by `_style_tag(prefix, on, props)` = `<prefix>-<sha256(json(selector keys + style props))[:12]>`.
- Public API types: `tags` still typed `Set[str]` (an `OrderedSet` is a `set`). Behaviour changes: a plain `set`/`frozenset` of str passed as `tags=` is added in sorted order (it has no order of its own); lists/tuples/dicts keep theirs. Plain-set results from `|`, `&`, `-` are unordered (see below).
- Style tag choice: a hash of selector plus style properties, not a counter. It is independent of creation order and process, and stable across seeds and runs. The style properties are part of the hash so that two colliding selectors (e.g. two lambdas, which can only be keyed by `module.qualname`) collide only when their style is identical, which is harmless. Element/relationship selectors use `ClassName:<id>`, which still depends on the global ID counter (out of scope). Prefix kept as `buildzr-styleelements-` / `buildzr-stylerelationships-` (not `buildzr-style-`) to avoid breaking anything matching on it.
- Not touched: the global ID counter.

## 3. After (`after.txt`, `after-linux.txt`)
macOS: seeds 1, 2, 3 and three more runs of seed 1, unmasked and masked: every file byte-identical. Linux devcontainer seeds 1, 2, 3: identical, and identical to macOS seed 1 byte-for-byte (same Python minor, different patch/OS).
Rechecked after restoring `@dataclass` on `With` and again after the set-algebra change (macOS seeds 1/2 identical, and identical to the earlier output): seeds 1/2 identical and identical to the earlier output.

Extra nondeterminism found beyond tag order and uuid (both fixed above): `DynamicView` element id order (seed dependent) and element `_relationships` set order (address dependent, run to run).

## 4. Tests
Devcontainer came up (`devcontainer up` ran in the background and I did not time it; the lead saw the container about 2 minutes old; no worktree problem). `uv sync --all-extras --locked` then `uv run pytest --mypy --ignore tests/test_workspaces.py tests`: **283 passed, mypy: no issues in 22 files** (first run, before the follow-up). After the follow-up (OrderedSet set algebra + `tests/test_tag_order.py`, 7 new tests): **290 passed, mypy: no issues in 23 files**. `tests/test_workspaces.py` (Java) NOT run. No existing test files changed; set-equality assertions on tags still hold. New: `tests/test_tag_order.py` (With constructs; default-first tags for Person/Software System/Container/DeploymentNode/relationship and `add_tags`; subprocess `to_json()` identical under PYTHONHASHSEED 1, 2, 3; OrderedSet operators and in-place operators).
Side effect: the devcontainer replaced the worktree's `.venv` with a Linux one. On the host I used `UV_PROJECT_ENVIRONMENT=<cache-dir>/venv-determinism` so host runs do not fight over it.

## 5. Set operators audit (`|`, `&`, `-`, `.union`...)
Follow-up: `OrderedSet` now also overrides `|`, `&`, `-`, `^` (and reflected forms), `intersection`, `difference`, `symmetric_difference`, `intersection_update`, `symmetric_difference_update`, `__iand__`, `__isub__`, `__ixor__`; results are `OrderedSet` with the left operand's order first (tested). Earlier grep of dsl.py, relations.py, expression.py, interfaces.py found no such operator applied to `_tags` or `_relationships`; plain-set uses left alone: `expression.py:80-83` (builds a plain `set` via `.union` for lambda filters, membership only), `dsl.py:3273` (membership), `dsl.py:1713` (boolean test).
Also: `With(tags={...})` regression found by lead review (my edit dropped `@dataclass` from `With`) is fixed; host check prints `With(tags={'a'}, properties=None, url=None)`.

## 6. Font metrics
`spike/tools/font_metrics.py` + `font_metrics.json` (1 KB). Font: Inter from `@fontsource/inter@5.3.0` (.woff latin 400 and 700), licence SIL OFL-1.1, parsed with `opentype.js@2.0.0` by `spike/determinism/fontgen/gen.mjs` (unitsPerEm 2048, no kerning, ASCII 32-126, other chars use the table average: regular 1150, bold 1203 units). `FONT_FAMILY = "Inter"`. Signatures unchanged. Samples (`font_samples.txt`, px):

| text | Inter | old stub |
|---|---|---|
| "Amazon Web Services" 14 regular | 149.81 | 148.96 |
| same, bold | 154.81 | 159.60 |
| "iiiiiiii" 14 | 27.12 | 62.72 |
| "WWWWWWWW" 14 | 110.36 | 62.72 |
| "Hello, world!" 12 | 70.99 | 87.36 |

## 7. Reproduce
```bash
export UV_CACHE_DIR=<cache-dir>/uv npm_config_cache=<cache-dir>/npm
export UV_PROJECT_ENVIRONMENT=<cache-dir>/venv-determinism
W=<worktree>; cd $W
uv run --project $W python spike/determinism/seeds.py 1 2 3 --out spike/determinism/out/a            # add --mask-uuids for masked
uv run --project $W python spike/determinism/seeds.py 1 --tag run2 --out spike/determinism/out/a
python3 spike/determinism/compare.py spike/determinism/out/a/1 spike/determinism/out/a/2
# before: check out master's buildzr/ (git checkout master -- buildzr) and run the same
devcontainer up --workspace-folder . && devcontainer exec --workspace-folder . uv sync --all-extras --locked
devcontainer exec --workspace-folder . uv run pytest --mypy --ignore tests/test_workspaces.py tests
devcontainer exec --workspace-folder . env TMPDIR_ROOT=/tmp uv run python spike/determinism/seeds.py 1 2 3 --out spike/determinism/out/linux
cd spike/determinism/fontgen && npm ci && node gen.mjs
```

## 8. NOT verified
- Windows; Linux only on aarch64/3.10 in the container, macOS only arm64/3.10, other Python versions untested.
- `tests/test_workspaces.py` (Java/Structurizr CLI) not run.
- Scene-level comparison (lead, at integration).
- Only 5 examples; `system_landscape`, notebooks, `to_plantuml` untested.
- Global ID counter still creation-order dependent (out of scope); style tags for element selectors embed those ids.
- `before.txt` was produced on the pre-fix code at commit `5a85594`+tools; `fontgen/package-lock.json` pins versions.
