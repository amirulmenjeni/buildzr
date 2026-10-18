# Recipes

Each recipe on this page reaches one goal that people often ask about. The recipes combine the commands described on the [Command reference](cli.md) and [`buildzr.yaml`](config.md) pages, and the documentation tests run every command and every file on this page.

## Words used on this page

| Word | Meaning |
|---|---|
| **workspace** | A `Workspace(...)` that you write in Python, and what readers open at `/<name>/`. |
| **workspaces folder** | The folder of Python files that create your workspaces, `workspaces/` by default. |
| **built workspace** | The folder that `buildzr build` writes for one workspace: the viewer, the model data and `build.json`. |
| **data-only workspace** | A built workspace without the viewer, only the model data. |

## The model used by the recipes

The recipes use this small model. Save it as `workspaces/shop.py`:

<!-- doctest: file workspaces/shop.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace("Shop") as w:
    customer = Person("Customer")
    shop = SoftwareSystem("Shop")
    customer >> "Buys from" >> shop
```

## A workspace for programs only

Goal: serve the model to scripts, CI jobs, dashboards and AI assistants, without the viewer.

Build data-only workspaces with `--no-viewer`, into a build output of their own, and serve that folder:

```text
$ buildzr build --no-viewer -o .buildzr/data
built .buildzr/data/shop (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)

$ buildzr serve .buildzr/data
Serving .buildzr/data at http://127.0.0.1:8000/ (Ctrl+C to stop)
  http://127.0.0.1:8000/shop/
Workspace list at http://127.0.0.1:8000/_buildzr/v1/workspaces
```

`serve` builds nothing here, because `.buildzr/data` already holds built workspaces. To make every build of the project data-only, set `viewer: false` in the `build` section of [`buildzr.yaml`](config.md) instead.

A data-only workspace has no `index.html`, so `/shop/` answers 404, and the [Model API](model-api.md) at `/shop/api/v1/` works as usual. One field changes: `viewerUrl`, the link in every answer that opens an element in the viewer. There is no viewer to link to, so `viewerUrl` is `null` in every answer, with or without `--public-url`. The orientation document of the API says so in its `notes` field, and the [list of workspaces](serve-workspaces.md#6-list-the-workspaces-from-a-program) shows `"viewerUrl": null`.

The request below shows such an answer. It was sent to a data-only build of the larger example model `examples/buildzr_models_example.py` from the buildzr repository, because the small shop model has no element that matches `mongo`:

<!-- doctest: api data-only -->
```http
GET /microservices-example/api/v1/elements?q=mongo
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "total": 1,
  "items": [
    {
      "id": "e-commerce-system/database",
      "name": "Database",
      "type": "Container",
      "parent": "e-commerce-system",
      "description": null,
      "technology": "MongoDB",
      "tags": [
        "Element",
        "Container"
      ],
      "childCount": 0,
      "viewerUrl": null,
      "matched": "technology"
    }
  ],
  "next": null,
  "truncated": false
}
```

## Several workspaces in one folder

Goal: keep the models of several systems in one repository, share code between them, and serve them together.

Put one model file per system in the workspaces folder, in subfolders if you like. Code that several model files share goes in a file whose name starts with `_`: `build` and `serve` never run such a file on its own, and a change to it rebuilds every workspace. Save this as `workspaces/_people.py`:

<!-- doctest: file workspaces/_people.py -->
```python
CUSTOMER = "Customer"
SUPPORT = "Support Agent"
```

A model file imports it by its name: when buildzr runs a model file, the folder of that file comes first on the import path. One file may also create more than one workspace. Save this as `workspaces/support.py`:

<!-- doctest: file workspaces/support.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

from _people import CUSTOMER, SUPPORT

with Workspace("CRM") as crm_ws:
    agent = Person(SUPPORT)
    crm = SoftwareSystem("CRM")
    agent >> "Looks up customers in" >> crm

with Workspace("Help Desk") as desk_ws:
    customer = Person(CUSTOMER)
    desk = SoftwareSystem("Help Desk")
    customer >> "Opens tickets in" >> desk
```

A model file in a subfolder, such as `workspaces/teams/crm.py`, has its own folder on the import path, not the workspaces folder. To import `_people.py` from there, add the workspaces folder to `sys.path` at the top of the file, or put the shared file in the same subfolder.

Build all of them:

```text
$ buildzr build
built .buildzr/build/shop (2 elements, 1 relationship, 0 views; modelHash sha256:87716f3c5b04…)
built .buildzr/build/crm (2 elements, 1 relationship, 0 views; modelHash sha256:5a1f07c2b9d0…)
built .buildzr/build/help-desk (2 elements, 1 relationship, 0 views; modelHash sha256:1b2c3d4e5f60…)
```

Each workspace has its own folder and its own address: `/shop/`, `/crm/` and `/help-desk/`. `buildzr serve` lists all three at `/`. If two workspaces end up with the same name, `build` stops before it writes anything and names both, so you can rename one.

## Sharing a link to one element

Goal: send a colleague a link, or put one in a ticket, that opens the viewer at one element.

The viewer keeps the state of the screen in the part of the address after `#`, the **hash**. A link with a hash therefore opens the same element at the same level. You can write the hash by hand:

| To open... | Write |
|---|---|
| The landscape (every person and software system of the model) | `#/m` |
| A box that contains other boxes, expanded | `#/m/billing?sel=billing` |
| One element inside a box, selected | `#/m/billing?sel=billing/api` |
| A view that the authors drew | `#/v/billing-containers` |
| A box with a search and a tag filter on | `#/m/billing?q=pay&tags=PCI` |

```text
#/m
#/m/billing?sel=billing
#/m/billing?sel=billing/api
#/v/billing-containers
#/m/billing?q=pay&tags=PCI
```

Put the hash after the address of the workspace: `http://127.0.0.1:8000/shop/#/m/billing?sel=billing/api`. [Viewer links](viewer-hash-routes.md) describes the full grammar.

You can also take the link from the [Model API](model-api.md) instead of writing it. Every element in an answer carries its link in the field `viewerUrl`. Ask for the element and use that field. This example asks the API of the workspace built from `examples/buildzr_models_example.py`, which `buildzr serve` serves at `/microservices-example/`:

<!-- doctest: api example -->
```http
GET /microservices-example/api/v1/elements?q=repository
```

```json
{
  "apiVersion": "1",
  "modelHash": "sha256:ea077dc2738151741a441db445e54dc1195406615dc8eae81fb65f740d059e35",
  "total": 1,
  "items": [
    {
      "id": "e-commerce-system/order-service/order-repository",
      "name": "Order Repository",
      "type": "Component",
      "parent": "e-commerce-system/order-service",
      "description": null,
      "technology": null,
      "tags": [
        "Element",
        "Component"
      ],
      "childCount": 0,
      "viewerUrl": "/microservices-example/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service/order-repository",
      "matched": "name"
    }
  ],
  "next": null,
  "truncated": false
}
```

The link starts with `/` because `buildzr serve` ran without `--public-url`. When you start it with `--public-url https://architecture.example.com`, the links are complete: `https://architecture.example.com/microservices-example/#/m/...`. One option covers every workspace that `serve` serves. `buildzr serve` never guesses the address from the request.

Links follow **names**. The id of an element is made from the names of its parents and its own name. Renaming an element changes its id: an old link then opens the nearest box that still exists, and the viewer says so. Two siblings with the same name get `-2`, `-3` in model order. Adding an earlier sibling with the same name can therefore make an old link open a different element. See [Viewer links](viewer-hash-routes.md#what-a-link-restores-and-what-it-cannot).
