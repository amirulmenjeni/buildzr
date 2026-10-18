# Viewer links

A viewer link opens the viewer of a site at a chosen place: an element, a view, a selection or a search. The link is the address of the site plus a **hash**, the part after `#`. This page is the reference of the hash.

You can write a hash by hand, or take a complete link from the `viewerUrl` field of a [Model API](model-api.md) answer. For a short guide to sharing links, see [the recipes](publishing-recipes.md#sharing-a-link-to-one-element).

Links in the forms on this page keep working in later versions of buildzr.

## Words used on this page

| Word | Meaning |
|---|---|
| **viewer** | The web page inside a site that draws the diagrams. |
| **hash** | The part of an address after `#`. The viewer keeps its navigation state there. |
| **landscape** | The first diagram the viewer shows, like a [System Landscape diagram](https://c4model.com/#SystemLandscapeDiagram) of the C4 model: every person and software system of the model. Groups draw a boundary around some of them; they do not hide any. |
| **element path** | The id of an element: lower-case names joined by `/`, for example `billing/api`. It is the same id as in the Model API. |
| **authored view** | A view that the authors of the model defined, such as a system context view. |
| **arrow id** | The id of an arrow that the viewer draws, such as `billing/web->billing/api`. |

## How the viewer uses the hash

The viewer keeps all its navigation state in the hash. Every screen therefore has its own link, and the viewer works on a static file server at any address. The viewer's state (`path`, `view`, `selection`, `filter`) is the source of truth. The viewer writes the hash from the state, and reads the state back from the hash on load and on every `hashchange` event.

## Grammar

```
hash      = "#/" route [ "?" query ]
route     = "m" [ "/" elpath ]          ; model canvas
          | "v/" viewkey                ; authored view
elpath    = segment *( "/" segment )    ; slug path from the model, e.g. billing/api
viewkey   = segment                     ; the key of an authored view
segment   = 1*( %x61-7A / DIGIT / "-" ) ; [a-z0-9-], never empty
query     = param *( "&" param )
param     = "sel=" ( elpath / edgeid )
          | "q=" text                   ; percent-encoded search text
          | "tags=" tag *( "," tag )    ; percent-encoded tag names
          | "mode=" ( "and" / "or" )    ; tag combination, default "or"
```

- An empty hash, `#`, `#/` and `#/m` all mean the landscape.
- `#/m/billing/api` is the model canvas with the expanded path `landscape → billing → billing/api`. Only one path is expanded at a time.
- `#/v/billing-containers` opens the authored view whose scene is `v/billing-containers`.
- `sel` names one element path or one arrow id (`edgeid` in the grammar). Arrow ids contain `->`, `:` and `/`, which are percent-encoded in the hash (`-%3E`, `%3A`).
- The viewer writes the keys in the fixed order `sel`, `q`, `tags`, `mode`. It leaves out empty and default values, so `mode=or` is never written. Tags keep the order that the reader chose.
- The viewer ignores unknown query keys and drops them the next time it writes the hash.

Examples:

```
#/m
#/m/billing?sel=billing/api
#/m/billing/api?sel=billing/api/payments&q=pay&tags=PCI,Database&mode=and
#/v/billing-containers?sel=crm
#/m/billing?sel=billing/web-%3Ebilling/api
```

## What a link restores and what it cannot

| Restores | Cannot restore |
|---|---|
| Which element is expanded (the level): one path from the landscape down | Several unrelated elements expanded at once (only one path is expanded at a time) |
| The selected element or arrow | Pan and zoom |
| An authored view | The inspector tab and the scroll position of the tree |
| Search text, tags and tag mode | [Viewer settings](ui-settings.md), which each browser keeps for itself |

## When the model changes

A hash holds the names of elements, not fixed numbers. This has two effects:

- **Renaming or moving an element changes its path.** An old link then opens the nearest box that still exists, with a notice; see [Links to elements or views that do not exist](#links-to-elements-or-views-that-do-not-exist). Nothing breaks, but the link is less exact.
- **Siblings with the same name get `-2`, `-3` in model order.** Adding an earlier sibling with the same name shifts these numbers, so an old link can open a different element without any notice. Give siblings different names if links to them must last.

## Browser history

| Action | Browser history |
|---|---|
| Expand or collapse (click on the canvas, the tree or the breadcrumbs, or press Escape) | adds an entry |
| Open an authored view, or "Show in model" | adds an entry |
| Change the selection | replaces the entry |
| Change the search text, tags or mode | replaces the entry |

As a result, Back steps out one level at a time. For example, after you expand `billing` and then `billing/api` from the landscape, pressing Back twice returns to `#/m`.

## Links to elements or views that do not exist

- `#/m/<path>` with a path that is not in the model: the viewer walks up the path until it finds an existing element, or reaches the landscape. It expands that element, replaces the hash with its path and shows a notice, for example "`billing/old-api` not found; showing `billing`".
- A path to an element without children (a leaf, such as a component): the viewer expands the parent and selects the element. `#/m/billing/api/payments` is rewritten to `#/m/billing/api?sel=billing/api/payments`.
- `#/v/<key>` with an unknown view key: the viewer opens `#/m` and shows a notice.
- `sel=` that names nothing in the current canvas or model: the viewer drops it without a notice.
- Element types the viewer does not draw, for example `DeploymentNode`: the viewer ignores them everywhere, also in `sel=`.
