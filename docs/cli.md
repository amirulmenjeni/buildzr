# Command line

`pip install buildzr` also installs the `buildzr` command. It turns the model you wrote in Python into a website you can browse, serve and publish. It has three commands: `build`, `serve` and `deploy`.

## Which page do I read?

| I want to... | Read |
|---|---|
| Draw a model in Python | [Quick Start](getting-started/quick-start.md) and the [User Guide](user-guide/core-concepts.md) |
| Look at my model in a browser | This page, "A first run" below |
| Publish my model for other people | [Deploying to an instance](deploy.md), then the [recipes](publishing-recipes.md) |
| Let programs and AI assistants read my model | [The agent API](agent-api.md) |
| Run a shared instance that holds many models | [The site store](store.md) and [Deploying to an instance](deploy.md) |
| Keep my settings in one file | [`buildzr.yaml`](config.md) |
| Link to one box of a diagram | [Viewer links](viewer-hash-routes.md) |

## The three commands

| Command | What it does |
|---|---|
| `buildzr build` | Runs your model file and writes a **site**: a folder with the viewer, the model data and a file called `build.json`. |
| `buildzr serve` | Serves a built site (or a whole [store](store.md) of sites) over HTTP so you can open it in a browser. It only reads; nothing can change through it. |
| `buildzr deploy` | Builds the site and puts it on a **target** named in [`buildzr.yaml`](config.md): a folder on this machine, or a running instance. |

Every setting comes from a flag first, then from `buildzr.yaml`, then from a built-in default. Run `buildzr COMMAND --help` to see the same list as below.

### `buildzr build`

```text
buildzr build [-h] [-w FILE] [--k N] [--text-color {wcag,c4}] [--no-viewer] [-c FILE] [-o DIR]
```

| Option | What it does |
|---|---|
| `-w FILE`, `--workspace FILE` | The Python file that creates a `Workspace`. Default: `workspace:` in `buildzr.yaml`. |
| `--k N` | Layout parameter, a whole number of at least 1. Default: `build.k` in `buildzr.yaml`, else 4. |
| `--text-color {wcag,c4}` | The rule for the colour of text on boxes. Default: `build.text_color`, else `wcag`. |
| `--no-viewer` | Write the data only, without the viewer. |
| `-c FILE`, `--config FILE` | The config file. Default: `buildzr.yaml`, searched from the current folder upward. |
| `-o DIR`, `--out DIR` | Where to write the site. Default: `build.out`, else `.buildzr/site`. |

`build` runs your file, lays out the diagrams and checks the result. If a step fails, the previous output is left as it was.

### `buildzr serve`

```text
buildzr serve [-h] [--store DIR] [-p PORT] [--host HOST] [--public-url URL] [--cors-origin ORIGIN] [--accept-deploys] [--deploy-port N] [--max-upload-mb N] [DIR]
```

| Option | What it does |
|---|---|
| `DIR` | The built site. Default: `build.out` of the nearest `buildzr.yaml`, else `.buildzr/site`. |
| `--store DIR` | Serve every site of the [store](store.md) folder `DIR`, read only, instead of one site. |
| `-p PORT`, `--port PORT` | The port. Default 8000. |
| `--host HOST` | The address to listen on. Default `127.0.0.1`, which only this machine can reach. Use `0.0.0.0` on purpose to share. |
| `--public-url URL` | The address readers use for the site (`http://` or `https://`). The [agent API](agent-api.md) builds its `viewerUrl` links from it. |
| `--cors-origin ORIGIN` | Let a web page from this origin read the API from a browser. Repeat it for more origins. There is no wildcard. |
| `--accept-deploys` | With `--store`: also accept uploads from `buildzr deploy`, on a second listener that only this machine can reach. Creates the store when the folder is missing or empty. |
| `--deploy-port N` | The port of that second listener. Default 8001. It always listens on `127.0.0.1`. |
| `--max-upload-mb N` | The largest upload accepted, compressed. Default 50. |

`serve` answers `GET` and `HEAD` only. Besides the files it answers the [agent API](agent-api.md) under `/api/v1/` and a generated `/llms.txt`. `--deploy-port` and `--max-upload-mb` need `--accept-deploys`, and `--accept-deploys` needs `pip install 'buildzr[serve]'`.

### `buildzr deploy`

```text
buildzr deploy [-h] [-w FILE] [--k N] [--text-color {wcag,c4}] [--no-viewer] [-c FILE] [-t NAME] [--path P] [--from DIR] [--dry-run] [--rollback]
```

| Option | What it does |
|---|---|
| `-t NAME`, `--target NAME` | The target in `buildzr.yaml`. Default: `default_target`. |
| `--path P` | The site path below the target. It overrides the target's `path`. |
| `--from DIR` | Deploy an already built site instead of building one. The build flags are then refused. |
| `--dry-run` | Load the config, build and check, and print what would happen. Nothing is written or sent. |
| `--rollback` | For `url` targets: make the previous release of the site current again. Nothing is built. |
| `-w`, `--workspace`, `--k`, `--text-color`, `--no-viewer`, `-c`, `--config` | As for `build`. |

For a `dir` target the site is written to `<dir>/<path>/` in one step. For a `url` target it is sent to a running instance. [Deploying to an instance](deploy.md) explains that flow, and [`buildzr.yaml`](config.md) explains targets.

### What `deploy` does with each kind of target

A **`dir` target** gets the site in `<dir>/<path>/`.

- The old copy is replaced as one step, and only after the checker passed on the new one. If the check fails, the target is left as it was.
- The command refuses to replace a folder that exists, is not empty and is not a buildzr site (it has no `build.json`). This stops a typo such as `dir: ~` from emptying a folder.
- With an empty `path`, the whole `dir` is replaced. Keep other sites in a `dir` of their own, or give each site its own `path`.
- The parent folder of the destination must be writable. If it is not, the command prints `buildzr: error: cannot write to <path>: <reason>` and exits with code 1.
- Without the `jsonschema` package, the check of the built site skips the schema step. `deploy` says so once, as `buildzr: warning: jsonschema is not installed; the site check skips the schema step`, and carries on. Install it with `pip install jsonschema` for the full check.
- `--rollback` is not available: a folder keeps no previous copy (the command exits with code 2). Deploy the older version again instead.

A **`url` target** sends the site to a running instance. The `url` must be on this machine (`127.0.0.1`, `localhost` or `[::1]`); to reach another machine, open an SSH tunnel as [Deploying to an instance](deploy.md) shows. `--rollback` makes the previous release of the site current again.

`--from DIR` builds nothing. It checks and deploys the site in `DIR` as it is, which is useful to send the same bytes to several targets. A site built without a viewer stays without one, and a site with a viewer keeps it, whatever the target's `viewer:` says.

The flags `--target DIR` and `--base-path`, which older versions had, are gone: `--target` is now a target name, and the base path is the target's `path` (or `--path`). To write a site to a one-off folder, use `buildzr build -o DIR`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Done. A dry run and an unchanged deploy also end with 0. |
| 1 | The build, the checker or the write failed; the instance rejected the site; the `url` is not a deploy address; the port is in use. |
| 2 | Usage or config error: an unknown flag, no workspace, a problem in `buildzr.yaml`, an unknown target, a variable that is not set. |
| 3 | `deploy` to a `url` target could not finish: the instance cannot be reached, the upload was interrupted, the instance stayed busy, or it is out of disk space. Worth trying again. |

Messages from the command itself start with `buildzr: error: `. Problems in `buildzr.yaml` are listed one per line as `buildzr.yaml:<line>: <key>: <message>`.

## A first run

This path starts from an empty folder and ends with your model open in a browser.

### 1. Write a model

Make a folder with a model file in it. A small shop with one system, two containers and one view:

<!-- doctest: file architecture/model.py -->
```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, Container, SystemContextView

with Workspace("shop", implied_relationships=True) as w:
    customer = Person("Customer")
    with SoftwareSystem("Shop") as shop:
        web = Container("Web App", technology="React")
        db = Container("Database", technology="PostgreSQL")
    payments = SoftwareSystem("Payment Provider")

    customer >> "Browses and orders" >> web
    web >> ("Reads and writes", "SQL") >> db
    web >> "Takes payment via" >> payments

    SystemContextView(software_system_selector=shop, key="shop-context", description="The shop in its environment")
```

Save it as `architecture/model.py`. Do not call `w.save()` in it; `buildzr build` does not need a JSON file.

### 2. Build the site

If you run `build` without saying which file to use, it stops and tells you:

```text
$ buildzr build
buildzr: error: no workspace given; pass --workspace FILE or set workspace: in buildzr.yaml
[exit code 2]
```

Pass the file with `-w`:

```text
$ buildzr build -w architecture/model.py
/home/you/shop/architecture/model.py: 5 elements, 3 relationships, 1 views, 3 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built .buildzr/site (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
```

The first line comes from the step that runs your model file. It counts what it found. The second line says where the site is and shows the **modelHash**, a fingerprint of the model: the same model always gives the same hash.

To save typing the file name, put it in a `buildzr.yaml` next to your `.git` folder or at the top of your project:

```yaml
workspace: architecture/model.py
```

Now the file name is not needed:

```text
$ buildzr build
/home/you/shop/architecture/model.py: 5 elements, 3 relationships, 1 views, 3 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built .buildzr/site (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
```

### 3. Serve it and open the link

```text
$ buildzr serve
Serving /home/you/shop/.buildzr/site at http://127.0.0.1:8000/ (Ctrl+C to stop)
Agent API at http://127.0.0.1:8000/api/v1/ (read only)
```

Open `http://127.0.0.1:8000/` in a browser. You see the landscape of your model; click a box to open it. Press Ctrl+C in the terminal to stop the server. If the port is busy, pick another with `-p 8001`.

The same address also answers questions about the model as JSON; see [the agent API](agent-api.md).

### 4. Publish it to a folder

Add a target to `buildzr.yaml`. A `dir` target is a folder on this machine, for example one that a web server serves:

```yaml
workspace: architecture/model.py
default_target: www
targets:
  www: {dir: public/architecture}
```

A dry run builds and checks the site and shows what would be written:

```text
$ buildzr deploy --dry-run
/home/you/shop/architecture/model.py: 5 elements, 3 relationships, 1 views, 3 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
checked 12 files, 517 KB: no problems
dry run: would write 12 files, 517 KB to /home/you/shop/public/architecture (target www); nothing was written
```

Without `--dry-run` it writes the site:

```text
$ buildzr deploy
/home/you/shop/architecture/model.py: 5 elements, 3 relationships, 1 views, 3 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
writing 12 files, 517 KB to /home/you/shop/public/architecture (target www)
deployed www: modelHash sha256:87716f3c5b04…
```

The old copy is replaced in one step, and only after the checker passed on the new one. `deploy` refuses to replace a folder that is not a buildzr site.

To send the site to a running instance instead, see [Deploying to an instance](deploy.md). For ready-made setups such as a preview per pull request, see the [recipes](publishing-recipes.md).
