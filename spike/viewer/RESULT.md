# Worker B result: React Flow viewer spike

Machine: Apple M4 Pro, macOS 15.7.5, Node 26.9.0, npm 11.19.1. Headless Chromium (Playwright chromium-headless-shell 156.0.8078.4), viewport 1600x1000.
Pinned versions (package.json, exact, `package-lock.json` committed): react / react-dom 19.3.1, @xyflow/react 12.12.0, vite 8.3.4, typescript 7.0.2, @vitejs/plugin-react 6.1.2, playwright 1.64.1, rollup-plugin-visualizer 7.1.1.

## Reproduce

```bash
export npm_config_cache=<cache-dir>/npm PLAYWRIGHT_BROWSERS_PATH=<cache-dir>/ms-playwright
cd spike/viewer
npm ci && npx playwright install chromium
node scripts/make_synthetic.mjs                 # writes public/scenes/synthetic-gen.scene.json
python3 -I ../tools/check_scene.py public/scenes/*.scene.json
npm run build                                   # tsc --noEmit && vite build
node scripts/verify.mjs                         # starts its own static server over dist/, exits non-zero on failure
npx vite build --config scripts/vite.baseline.config.ts   # React-only baseline -> dist-baseline/
npx vite build --config scripts/vite.stats.config.ts      # per-package stats -> .stats/stats.json
```
Screenshots go to `<shots-dir>/viewer-*.png`.
Real scenes from worker A: copy `*.scene.json` into `public/scenes/` and add `{"view","title","kind","file"}` rows to `public/scenes/index.json`, then rebuild. The `synthetic-gen` scene is my own (view key `synthetic-gen`, so it will not clash with the real `synthetic-120`).

## 1. Filtering never moves anything (PASS)

Checks per scene: store positions (`__spike.positions()`, from `internals.positionAbsolute`) exact equality, DOM `getBoundingClientRect` of every `.react-flow__node` within 0.01px, and at least one node whose computed opacity dropped.

| view | step | nodes | dimmed nodes | undimmed | dimmed edges | store diffs | DOM diffs | max DOM delta px |
|---|---|---|---|---|---|---|---|---|
| aws-mini | search "router" | 10 | 9 | 1 | 3 | 0 | 0 | 0 |
| aws-mini | tags OR (Infrastructure Node, Container Instance) | 10 | 6 | 4 | 0 | 0 | 0 | 0 |
| aws-mini | tags AND (same two) | 10 | 10 | 0 | 3 | 0 | 0 | 0 |
| aws-mini | search "router" + tag Infrastructure Node | 10 | 9 | 1 | 3 | 0 | 0 | 0 |
| synthetic-gen | search "tech 3" | 120 | 94 | 26 | 182 | 0 | 0 | 0 |
| synthetic-gen | tags OR (Green, Cache) | 120 | 48 | 72 | 105 | 0 | 0 | 0 |
| synthetic-gen | tags AND (Green, Cache) | 120 | 102 | 18 | 194 | 0 | 0 | 0 |
| synthetic-gen | search + tag Green | 120 | 111 | 9 | 198 | 0 | 0 | 0 |

Note: "tags AND" on aws-mini dims everything, because no node carries both tags. That is correct behaviour, but it makes a weak visual test; the first search test on the synthetic scene with the query "node 0" matched most nodes, so I changed it to "tech 3".
Filter state is in the hash: `#/v/<view>?q=..&tags=a,b&mode=and`. The hash is rewritten on every input change (no debounce).
A search term matches case-insensitively as a substring over name, id, type, technology, description and tags; several words are ANDed. A boundary node can match too, and is highlighted like any other node.

## 2. Edge z-order with nested children

- Edges: custom type `elk`, drawn from `points` (rounded corners, radius 6, marker-end triangle, dash from the scene), label placed with `EdgeLabelRenderer` at the scene's absolute `label.x/y`. Every node has two invisible 1px handles (left target, right source, `isConnectable=false`); the custom edge ignores `sourceX/targetY` etc., so handles do not influence the path. Handles are required: without them React Flow does not render the edge at all.
- Experiment: `zIndex: 1000` on every edge versus no `zIndex` (`/?nozindex=1#/v/aws-mini`, crops `viewer-edge-crossing-nested.png` and `viewer-edge-crossing-nested-nozindex.png`). **The two crops are identical in the AWS scene**: React Flow's default already lifts an edge between nested nodes above the boundary boxes, and the edge crosses three boundary borders visibly. So the `zIndex` I set is probably unnecessary here; I kept it as a safeguard but did NOT find a case where it mattered. Where it would matter (edge whose endpoints have different nesting depth vs. an unrelated sibling boundary drawn later) I did not test.
- Edge labels are rendered in the separate `EdgeLabelRenderer` layer, so they are always above nodes (I also set `zIndex: 2000` on the label div, which has no effect on that layer's ordering relative to nodes).
- Boundary fills are opaque `#ffffff` in the scene, so a boundary drawn after an unrelated edge would hide it. Not observed, not tested beyond the two scenes.

## 3. Timing (headless, M4 Pro, scene served from a local static server)

Cold load = new browser context per run (empty cache), 5 runs, `performance.now()` at the moment all nodes have measured size and handle bounds, taken from navigation start (includes fetching the JS/CSS and the scene JSON):

| scene | nav start -> all nodes initialised | + 2 animation frames |
|---|---|---|
| synthetic-gen (120 nodes, 200 edges, 104 KB JSON) | median 64 ms (63, 64, 64, 64, 64) | median 71 ms |

Filter toggle on the same scene (click a tag chip, time to the second `requestAnimationFrame` after the click, 10 clicks): median 32.8 ms (32 to 33 ms). That is two frames at 60 Hz, so the real cost is below what this method can resolve; do not read it as 33 ms of work. Headless Chromium on a fast machine; a laptop with a real GPU or a slow device will differ. `useNodesInitialized()` returned true at the time of reading, but in my first run `ready` never fired when I gated on it alone (cause not found), so readiness is derived from the node lookup (every node has `measured.width` and `handleBounds`); the hook value is recorded in `__spike.metrics.hookInitialized`.
Real `synthetic-120` from worker A was NOT measured (not yet available when I finished).

## 4. Bundle size (`vite build`, minified, no sourcemaps)

| asset | raw bytes | gzip -9 bytes |
|---|---|---|
| index-*.js | 407,158 | 127,050 |
| index-*.css | 16,256 | 2,832 |
| index.html | 407 | 274 |
| total (excluding scenes) | 423,881 | 130,174 |

Attribution by difference with a React-only "hello" baseline (`scripts/vite.baseline.config.ts`): baseline JS = 219.5 kB raw / 68.6 kB gzip (vite's gzip figure, level 6; react + react-dom). So everything that is not React is about 187.7 kB raw / ~60 kB gzip in the JS: @xyflow/react + @xyflow/system + d3-* (zoom, drag, selection, transition, interpolate, color, timer, dispatch, ease) + zustand + classcat, plus my app code. From the unminified stats (`.stats/stats.json`) my own `src/` is about 17 kB unminified (~6.5 kB gzip), @xyflow/react+system about 239 kB unminified of which d3 pieces are another ~97 kB unminified. React Flow CSS is 16 kB raw / 2.8 kB gzip.
That is the whole viewer at about 130 kB gzip, with react-dom ~ half of it. It lands in the design's 100 to 150 kB guess.
(The design note's number is not directly comparable if the wheel also ships fonts/icons; none included here.)

## 5. Accessibility (observed only, nothing built)

- React Flow gives every node wrapper `tabindex=0`, `role="group"`, `aria-roledescription="node"`; they are in the Tab order after the toolbar. In this spike each node has TWO stops, because my custom node component also sets `tabIndex=0` on its inner div (my mistake; remove it to get one stop per node).
- Tab order follows DOM order = scene order (pre-order, parents first): boundary, its child, ...
- Focusing a node and pressing Enter: nothing selected (`.selected` count 0 in my run). Arrow keys: no node moves, the viewport does not pan, and focus stays on the same node. (Selection by click works; `selectable: true`.) So keyboard navigation between nodes by direction, activation and "open details" are all things we would have to build.
- Edges are not focusable (set `focusable: false`), no accessible name on nodes beyond the visible text.

## What looks wrong in the screenshots

(`<shots-dir>/`: viewer-aws-mini, viewer-synthetic-gen, the two `-filtered`, and the two edge-crossing crops.)

- aws-mini: boundary labels at the bottom-left collide with the border of the nested child boundary (for example "Autoscaling Group" is struck through by the dashed border of "Amazon EC2 - Ubuntu Server"; "Amazon Web Services" by the ap-southeast-1 border). This comes from the hand-written fixture geometry (the parent's bottom padding is smaller than the label), not from the viewer; ELK must reserve label space at the bottom of boundaries.
- aws-mini: the Load Balancer line "[Infrastructure Node: Elastic Load Balancer]" is wider than the 220px box and sticks out on both sides. The pre-wrapped lines were measured with a different font than the browser's Helvetica/Arial fallback (I render with `font-family: Helvetica, Arial, sans-serif`, no bundled font). Needs the bundled font from worker C to be loaded in the viewer.
- aws-mini: the "Fowards requests to" label sits over the vertical edge's neighbourhood and the "Forwards requests to" label sits on the horizontal line stub below; fixture placement, fine.
- synthetic-gen: edges are randomly generated three-segment lines with no routing, so they run through unrelated nodes and labels; unreadable by construction, it is a load test not a layout test. At fit-to-view zoom (about 0.4) all text is tiny.
- Person shape is a rough guess (circle plus rounded rect); cylinder is fine; all other shapes fall back to Box.
- The search/tag toolbar is an overlay on top of the canvas; with many tags it wraps to several rows and covers the top of the diagram. The minimap shows nodes as plain grey blocks (no colours).
- Highlight outline (orange, 3px) is drawn outside the node and can overlap neighbours; dimmed nodes at 0.15 are still just readable on screen.

## What I did NOT verify

- Real scenes from worker A (none seen), including the real `synthetic-120`; the other `web_app_container_view_00` / `aws-deployment-view`.
- Browsers other than headless Chromium; no Safari/Firefox; no real GPU, no touch, no HiDPI screenshots.
- Edge z-order in cases other than the AWS scene (see above), edges whose endpoints are boundaries, and edge label collisions.
- Memory use, scroll/zoom frame rate, and anything above 120 nodes (the design mentions about 1,000).
- Edge hit-testing and edge selection (disabled), double click / drill-down, details panel, "fit to results" (not built).
- Startup of the page with `npm run dev`; only the production build was tested.
- The `useNodesInitialized` mystery above.
- Scene `lod`, `link`, `opacity` for nodes are only partly honoured (`opacity` yes; `lod`, `link` ignored); label `anchor: top-left` is implemented but never exercised.


---

# Follow-up (second pass): real scenes, bundled Inter, overflow check

Merged `spike/integration` (worker A's scenes, worker C's Inter metrics). Changes: `scripts/sync_scenes.mjs` (copies `../out/scenes/*.json` incl. `index.json` into `public/scenes/`, keeps the `aws-mini` and `synthetic-gen` rows), `@fontsource/inter` **5.3.0** exact, imports only `latin-400.css` and `latin-700.css`, all text `font-family: Inter` (no CDN), the extra `tabIndex` removed.
Reproduce: `node scripts/sync_scenes.mjs && npm run build && node scripts/verify.mjs` (env vars as above). Raw output of my last run: `<cache-dir>/tmp/viewer/verify2.out`.
Verify now derives its query and tags from each scene: the query is the full lower-case name of a middle element, the tags are the two tags nearest to a third of the nodes whose union does not cover every node.

## A. Position invariance, all 7 scenes (PASS)

28 steps (7 scenes x search, tags OR, tags AND, search+tags): store diffs 0, DOM diffs 0, max DOM delta 0.0000 px, and at least one node's opacity changed in every step. Examples of the dim counts: aws-deployment-view search 17 of 19 dimmed, tags-or 11 of 19; synthetic-120 search 119 of 120, tags-or 55 of 120, tags-and 117 of 120 (3 stay lit). (The first run of this pass failed two steps because my auto-picked search word "node" matched every node, and my tag pair covered all nodes in web_app_system_context_00; those were test-selection bugs, fixed in `verify.mjs`, not viewer bugs.)

## B. Label overflow with bundled Inter (rendered width of each label line vs node width, measured in the browser after `document.fonts.ready`, divided by viewport zoom)

| scene | lines | overflowing | Inter loaded |
|---|---|---|---|
| aws-deployment-view | 48 | 0 | yes |
| synthetic-120 | 348 | 0 | yes |
| web_app_container_view_00 | 7 | 0 | yes |
| web_app_system_context_00 | 6 | 0 | yes |
| x_context_00 | 5 | 0 | yes |
| aws-mini (old hand-written fixture) | 24 | 1 | yes |
| synthetic-gen (my generator) | 240 | 0 | yes |

So worker A's wrapped lines fit when rendered with Inter 5.3.0 at the declared sizes. The one overflow is my old fixture ("[Infrastructure Node: Elastic Load Balancer]" 248.1px > 220), which was wrapped with the old metrics. Only widths are checked, not line heights or the vertical fit of the whole label block. Boundary labels are measured against the boundary's width, which is a weak check (a boundary label has room to spare).

## C. Timing, real synthetic-120 (120 nodes, 200 edges, dense variant; 21,154 x 12,351 bounds), headless Chromium, M4 Pro

- Cold load (new context each, 5 runs), navigation start to all nodes initialised: median **63 ms** (69, 61, 64, 62, 63); two frames later median 71 ms.
- Filter toggle (tag chip click to second frame, 10 clicks): median **25.7 ms** (21 to 33). Again two-frames resolution; below one 60 Hz frame pair, not a measured cost.
- synthetic-gen, for comparison: 65 ms init, 32.8 ms toggle.
These numbers come from a 104 KB (synthetic-gen) / larger (synthetic-120) scene fetched from localhost; a network fetch is not included in any real sense.

## D. Bundle (`vite build`)

| group | raw bytes | gzip -9 bytes |
|---|---|---|
| JS + CSS + HTML | 424,346 | 130,310 |
| Inter woff2 (400 + 700, latin; 23,664 + 24,356) | 48,020 | 47,980 (woff2 does not compress further) |
| Inter woff fallback (emitted by fontsource CSS, only fetched by browsers without woff2) | 62,016 | 61,717 |

Browsers that support woff2 download the JS/CSS/HTML (130 kB gzip) plus 48 kB of font = about 178 kB. The woff files are in `dist/` because the fontsource CSS references both formats; they could be dropped with a custom `@font-face`.

## E. Screenshots (all in `<shots-dir>/`) and what looks wrong

Files: `viewer-aws-deployment-view.png`, `viewer-web_app_container_view_00.png`, `viewer-web_app_system_context_00.png`, `viewer-x_context_00.png`, `viewer-synthetic-120.png`, `viewer-aws-deployment-view-filtered.png`, `viewer-synthetic-120-filtered.png`, plus the earlier aws-mini / synthetic-gen files.

- **Scene bug, not viewer: white text on white fill.** In `aws-deployment-view`, 4 of 19 nodes (the "Web Application" and "Database Schema" container instances, in both regions) have `style.color: #ffffff` on `fill: #ffffff`, so they render as empty boxes. In `x_context_00` both nodes (Person and Software System) are `#ffffff` on `#ffffff`, so the whole diagram is blank boxes. The viewer draws what the scene says; the scene stage must resolve colours (probably a Structurizr default text colour applied without the matching default fill). This also means the search highlight is the only way to find those boxes.
- **aws-deployment-view otherwise looks right:** nested dashed boundaries with bottom-left labels and no collisions with child borders (the earlier collisions were the fixture), orthogonal dashed edges crossing the boundary borders, labels centred on the edges, lines fit in the boxes, filtered view dims the rest and outlines the two matching Database Schema cylinders.
- **web_app_container_view_00:** the boundary "Corporate Web App" has a strong blue fill with black label text (low contrast, from the scene); the edge label sits on a light-blue rectangle because my label background is `rgba(255,255,255,.85)` over the blue boundary; looks like a patch. Edge label also sits partly on the dashed line's lower side, as placed by the scene. The fit zoom is large (about 2x) because the scene is small; fine.
- **web_app_system_context_00:** fine. Edge label "sends notification using" is below the line, correct.
- **x_context_00:** blank boxes (see above). The Person head circle is clipped at the top by the toolbar overlay; the whole canvas is under the toolbar, so fit-to-view does not leave room for it (`fitView` padding does not know about the toolbar). Person label would be centred in the body.
- **synthetic-120 (dense):** at fit zoom the diagram is unreadable, as expected for 21,000 x 12,000 px of content in a 1600 x 1000 window (zoom about 0.07). Edge lines extend far to the left of every node: edge points start at x = 135 while the leftmost node is at x = 6,616, and the scene's `bounds` is 21,154 wide. `fitView` fits the nodes, not the edges, so edges run off the left edge of the viewport (visible as faint horizontal lines reaching x = 0). The long edges look like layout-side routing across empty space (worker A) rather than a viewer defect. A few large brown (filled) boundary boxes dominate; the fill colour for those comes from the scene.
- Filtered synthetic-120: nearly everything is dimmed because the combined query matches almost nothing; the highlight outlines are too small to see at this zoom.
- Toolbar still overlaps the canvas; the minimap shows plain grey blocks without the node colours.

## F. Accessibility, re-checked

After removing my extra `tabIndex`, each node is one Tab stop (the Tab-order log lists each node id once, 16 to 25 after the 15 toolbar stops). Enter and arrow keys still do nothing observable (no selection, no node move, no pan).

## G. Not verified in this pass

Same list as above, plus: whether the white-on-white colours are intended as fallbacks somewhere (I only read the scene JSON); Inter with characters outside latin (not bundled); the woff-less build; contrast of the dim state; any scene other than the seven.
