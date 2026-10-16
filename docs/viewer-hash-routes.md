# Viewer hash routes (v4)

The viewer keeps all navigation state in the URL hash, so every screen is a
deep link and works on a static file server at any base path. The store
(`path`, `view`, `selection`, `filter`) is the source of truth; the hash is
derived from it and parsed back on load and on `hashchange`.

## Grammar

```
hash      = "#/" route [ "?" query ]
route     = "m" [ "/" elpath ]          ; model canvas
          | "v/" viewkey                ; authored view
elpath    = segment *( "/" segment )    ; slug path from model.json, e.g. billing/api
viewkey   = segment                     ; model.json views[].key
segment   = 1*( %x61-7A / DIGIT / "-" ) ; [a-z0-9-], never empty
query     = param *( "&" param )
param     = "sel=" ( elpath / edgeid )
          | "q=" text                   ; percent-encoded search text
          | "tags=" tag *( "," tag )    ; percent-encoded tag names
          | "mode=" ( "and" / "or" )    ; tag combination, default "or"
```

- An empty hash, `#`, `#/` and `#/m` all mean the landscape.
- `#/m/billing/api` is the model canvas with the expanded path
  `landscape → billing → billing/api` (one expanded path at a time).
- `#/v/billing-containers` opens the authored view whose scene is
  `v/billing-containers`.
- `sel` names one element path or one scene edge id. Edge ids contain `->`,
  `:` and `/`; they are percent-encoded in the hash (`-%3E`, `%3A`).
- Keys are written in the fixed order `sel`, `q`, `tags`, `mode`. Empty or
  default values are omitted (`mode=or` is never written). Tags keep the
  order the user chose.
- Unknown query keys are ignored and dropped on the next write.

Examples:

```
#/m
#/m/billing?sel=billing/api
#/m/billing/api?sel=billing/api/payments&q=pay&tags=PCI,Database&mode=and
#/v/billing-containers?sel=crm
#/m/billing?sel=billing/web-%3Ebilling/api
```

## History

| Action | History |
|---|---|
| Expand or collapse (canvas click, tree, breadcrumbs, Escape) | push |
| Open an authored view, "Show in model" | push |
| Change selection | replace |
| Change search text, tags or mode | replace |

So Back steps out one level at a time: after expanding `billing` and then
`billing/api` from the landscape, Back twice returns to `#/m`.

## Resolution of unknown targets

- `#/m/<path>` with a path that is not in `model.json`: the viewer walks up
  the path until it finds an existing element (or reaches the landscape),
  expands to that ancestor, replaces the hash with it and shows a notice
  ("`billing/old-api` not found; showing `billing`").
- A path to an element without children (a leaf, e.g. a component) expands
  to its parent and selects the element: `#/m/billing/api/payments` is
  rewritten to `#/m/billing/api?sel=billing/api/payments`.
- `#/v/<key>` with an unknown view key falls back to `#/m` with a notice.
- `sel=` naming nothing in the current canvas or model is dropped silently.
- Element types the viewer does not know (for example `DeploymentNode`, to
  come later) are ignored everywhere, including in `sel=`.
