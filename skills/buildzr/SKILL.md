---
name: buildzr
description: Use when the user wants to model software architecture, C4 diagrams or Structurizr workspaces in Python, create or edit a buildzr workspace, run `buildzr build` or `buildzr serve`, fix a broken workspace, or ask questions about a served architecture model. Produces model files in `workspaces/`, built workspaces with an interactive viewer, and answers from the read-only Model API.
---

# buildzr

buildzr describes software architecture in Python with the C4 model. A **model file** in the **workspaces folder** (`workspaces/` by default) creates one or more `Workspace`s. `buildzr build` runs every model file, lays out the diagrams and writes one **built workspace** per workspace into the **build output** (`.buildzr/build/<name>/`). `buildzr serve` serves them: an interactive viewer for people and a JSON Model API for programs.

## 1. Install buildzr and check it

Install with `pip install buildzr`, `uv add buildzr`, or run without installing as `uvx buildzr build`. Node.js 18 or newer must be on the PATH for the layout step. Read [references/install.md](references/install.md) to pick the form and for the version note.

Check: `buildzr --version` (with `uv run` or `uvx` in front, if you use those) prints `buildzr 1.0.0` or newer and exits with code 0, and `node --version` prints v18 or newer. `command not found` means a 0.0.x release, which has no `buildzr` command: install again.

## 2. Write the model file

Create `workspaces/<name>.py` with one `with Workspace('<Name>') as w:` block. Put every element, relationship, view and style inside that block. A model file does not call `w.save()`: the build reads the workspace itself.

```python
from buildzr.dsl import (
    Workspace, Person, SoftwareSystem, Container,
    SystemContextView, ContainerView, StyleElements,
)

with Workspace('Online Shop') as w:
    customer = Person('Customer', description='Buys products')
    with SoftwareSystem('Shop', description='Sells products online') as shop:
        web = Container('Web App', technology='React')
        api = Container('API', technology='Python, FastAPI')
        db = Container('Database', technology='PostgreSQL', tags={'Database'})
    payments = SoftwareSystem('Payment Provider')

    customer >> "Buys products with" >> web
    web >> ("Calls", "JSON/HTTPS") >> api
    api >> ("Reads from and writes to", "SQL") >> db
    api >> "Takes payments through" >> payments

    SystemContextView(software_system_selector=shop, key='shop-context', description='The shop and its users')
    ContainerView(software_system_selector=shop, key='shop-containers', description='Inside the shop')

    StyleElements(on=[customer], shape='Person')
    StyleElements(on=['Database'], shape='Cylinder')
```

The essentials:

- Nest with `with`: containers inside `with SoftwareSystem(...)`, components inside `with Container(...)`, deployment nodes inside `with DeploymentEnvironment(...)`.
- Relationships: `a >> "description" >> b`, `a >> ("description", "technology") >> b`, or `a.uses(b, "description", "technology")`. Tag one with `| With(tags={'async'})`.
- Views take a unique lower-case `key`; it becomes the link `#/v/<key>`.
- Style by tag (`on=['Database']`), by element (`on=[customer]`) or by type (`on=[Container]`).

For components, groups, dynamic views, deployment views, themes and every argument, read [references/dsl.md](references/dsl.md). It has three complete examples to start from.

Deployment nodes and deployment views are not part of a built workspace yet: `buildzr build` drops them without a warning, and neither the viewer nor the Model API shows them. When the user asks for a deployment view, write it anyway, tell the user it will not appear in the viewer, and give it as Structurizr JSON: add `w.save(path='workspace.json')` as the last line of the `with` block and run `python workspaces/<name>.py` (`uvx --from buildzr python workspaces/<name>.py` without an install). The file opens in Structurizr Lite. `buildzr build` ignores the `save`.

Check: the file compiles (`python -m py_compile workspaces/<name>.py`).

## 3. Build, read the errors, fix, repeat

Run `buildzr build` in the folder that holds `workspaces/`.

- Success: exit code 0 and one line per workspace: `built .buildzr/build/<name> (N elements, N relationships, N views; modelHash sha256:…)`.
- A **broken** workspace: exit code 1 and a red block on stderr. Python's traceback comes first, then:

  ```text
  buildzr: BROKEN: workspace <name> (workspaces/<file>.py) failed at the model step
      NameError: name 'databse' is not defined
      <file>.py, line 13: cluster >> "Stores data in" >> databse
    this workspace is broken; the viewer says so
  ```

  The step is `model` (the Python raised: fix the line it names), `layout` or `check` (a bug in buildzr: report it with the errors). The same errors are in `.buildzr/build/<name>/build.json`: `"status": "broken"`, `"stage"`, `"errors"`. Read that file when the terminal output is cut off.
- A line `buildzr: error: …` without a BROKEN block is a problem of the machine or the command (Node missing, a bad `buildzr.yaml`, exit code 2 for usage errors): fix what it names.

Fix the model file and run `buildzr build` again. Check: exit code 0, no `BROKEN` and no `skipped` line, and the `built` line counts every view you wrote except the deployment views.

## 4. Serve the workspaces and give the link

Run `buildzr serve` (it builds what changed, then serves; `Ctrl+C` stops it). Give the user the address it prints for the workspace, `http://127.0.0.1:8000/<name>/`.

- The viewer opens on the landscape (every person and software system). Clicking a box shows its details and relationships; the left panel lists the views.
- Link to a view: `/<name>/#/v/<view-key>`. Link to one selected element: `/<name>/#/m/<parent-path>?sel=<element-path>`, for example `/online-shop/#/m/shop?sel=shop/api`. The `viewerUrl` of a Model API answer is such a link, ready to give.
- `<name>` is the workspace name in lower case with `-` for spaces and other characters: `Online Shop` becomes `online-shop`.
- Viewer settings (the gear at the bottom of the left panel) live in each reader's browser; nothing in the model sets them.

Check: `curl -s http://127.0.0.1:8000/_buildzr/v1/workspaces` lists the workspace with `"status": "ok"`.

## 5. Answer questions from the Model API

While `buildzr serve` runs, read the model as JSON instead of reading the Python: it gives the resolved ids, relationships and rollups the viewer shows, and it works for model files you did not write. Read the Python only to change the model.

- `GET /_buildzr/v1/workspaces`: every workspace with `status`, `viewerUrl`, `apiUrl`, `llmsUrl`.
- `GET /<name>/llms.txt`: a short text page that lists the endpoints. Start here.
- `GET /<name>/api/v1/`: the orientation document: counts, top-level ids, endpoint templates, limits.
- Then `element?id=shop/api`, `elements?q=postgres`, `tree?depth=2`, `neighbours?id=shop/database&direction=in`, `path?from=customer&to=shop/database`, `relationships?from=shop/api`, `views`, `view?key=shop-containers`.

Element ids are made from the element **names**, not the Python variables: lower case, `-` for spaces, joined by `/` (`Container('Database')` in `Shop` is `shop/database`). A wrong id answers 404 with the nearest existing ancestor. Lists are paged: follow `next` while `truncated` is true. After a change, build again and the answers change with the `modelHash`. Every endpoint and field is described at https://buildzr.dev/model-api/.

Check: `curl -s http://127.0.0.1:8000/<name>/api/v1/` answers JSON with `"status": "ok"`.

## buildzr.yaml

Optional, in the project root. Only these keys matter for most projects:

```yaml
workspaces: architecture   # the workspaces folder (default: workspaces), or a list of files and folders
build:
  out: .buildzr/build      # the build output
  k: 4                     # raise when the insides of expanded boxes are too small to read
serve:
  port: 8000
```

Options on the command line win over the file. Unknown keys are errors. Every key: https://buildzr.dev/config/.

## Pitfalls

- **A file that creates no workspace** is skipped with `skipped workspaces/<file>.py: it creates no workspace`. Put the `with Workspace(...)` block at the top level of the file, not inside a function that nothing calls.
- **Two workspaces with the same built name** (`Shop` and `shop`) stop the whole build before anything is written: `buildzr: error: two workspaces would both be built as "shop": …`. Rename one.
- **Importing one model file from another** runs its `with Workspace(...)` block again and gives the same error. Share code through a helper file instead.
- **Helper files start with `_`** (`workspaces/_people.py`): the build does not run them as model files, a model file imports them (`from _people import add_people`), and a change to them rebuilds the workspaces.
- **Code imported from outside the workspaces folder is not tracked**: `buildzr serve` keeps the old built workspace after you change it. Run `buildzr build` (it always rebuilds everything) or `buildzr serve --rebuild`.
- **Model files run in a temporary folder**, so a relative path such as `open('data.csv')` does not find the project's files. Build paths from `__file__`.
