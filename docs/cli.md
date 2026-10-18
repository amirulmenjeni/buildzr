# Command line

The `buildzr` command turns an architecture model that you write in Python into a **site**: a folder of web pages that draws your diagrams in a browser. You can open the site on your own machine, or deploy it so that other people can open it.

The command has three subcommands:

- `buildzr build` runs your model file and writes the site.
- `buildzr serve` serves a site so that you can open it in a browser.
- `buildzr deploy` builds the site and copies it to a place that other people can reach.

This page has three parts. A [tutorial](#tutorial-build-view-and-deploy-your-first-site) takes you from an empty folder to a deployed site. The [command reference](#command-reference) lists every option. The [exit codes](#exit-codes) section lists what each exit code means.

## Find the page for your task

| You want to... | Read |
|---|---|
| Describe your architecture in Python | [Quick Start](getting-started/quick-start.md) and the [User Guide](user-guide/core-concepts.md) |
| Open your model in a browser | The [tutorial](#tutorial-build-view-and-deploy-your-first-site) on this page |
| Deploy your model for other people | [Deploying to an instance](deploy.md), then the [recipes](publishing-recipes.md) |
| Let scripts, CI (continuous integration) jobs, dashboards and AI assistants read your model | [The Model API](model-api.md) |
| Run one shared server (an instance) that holds many sites | [The site store](store.md) and [Deploying to an instance](deploy.md) |
| Keep your settings in one file | [`buildzr.yaml`](config.md) |
| Link to one box of a diagram | [Viewer links](viewer-hash-routes.md) |

## Words used on this page

| Word | Meaning |
|---|---|
| **model file** | The Python file that creates your `Workspace`. You name it with the `--workspace` option or the `workspace:` key of `buildzr.yaml`. |
| **site** | The folder that `buildzr build` writes: the viewer, the model data and a file called `build.json`. |
| **deploy** | To copy a built site to a target with `buildzr deploy`, so that other people can open it. |
| **viewer** | The web page inside a site that draws the diagrams. A site built with `--no-viewer` has the model data only and is called a **data-only site**. |
| **landscape** | The first diagram the viewer shows: the top level of your model. |
| **modelHash** | A fingerprint of the model, shown as `sha256:` and the start of a hash. The same model always gives the same hash. |
| **Model API** | The part of `buildzr serve` that answers questions about the model as JSON (a text format for data), under `/api/v1/`. |
| **site check** | The check that `build` and `deploy` run on a built site before they use it. |
| **`buildzr.yaml`** | The optional config file of your project. It holds the model file name, build settings and targets. |
| **target** | A named destination in `buildzr.yaml` to which `deploy` copies the site. A `dir` target is a folder on this machine. A `url` target points to the deploy listener of an instance. |
| **instance** | A running `buildzr serve --store DIR`: one process that serves every site of a store. With `--accept-deploys`, it also accepts new sites from `buildzr deploy`. |
| **store** | The folder `DIR` in which an instance keeps its sites. See [The site store](store.md). |
| **site path** | Where a site sits below the address of its target. With the site path `pr/42`, the site is served at `/pr/42/`. Empty means the top. |
| **release** | One deployed copy of a site on an instance. The instance keeps the current and the previous release of every site path. |
| **deploy listener** | The second port of an instance. It accepts uploads from `buildzr deploy`, and only from the same machine. |

## Before you start

You need:

- Python 3.10 or newer.
- Node.js 18 or newer on the machine that runs `buildzr build` or `buildzr deploy`. The layout step of the build runs on Node. Check your version with `node --version`. `buildzr serve` does not need Node.
- The `buildzr` package. Installing it also installs the `buildzr` command.

Install the package with pip:

```bash
pip install buildzr
```

If your project uses [uv](https://docs.astral.sh/uv/), add the package to it instead:

```bash
uv add buildzr
```

### Run the command without installing it

uv includes a tool called `uvx`, so install uv first. `uvx` runs a command in a temporary environment, and you do not install anything into your project. Put `uvx` in front of each command on this page, for example `uvx buildzr build`.

The temporary environment contains buildzr, so your model file can import it. If your model file imports other packages, add each one with `--with`:

```bash
uvx --with <package> buildzr build
```

## Tutorial: build, view and deploy your first site

In this tutorial you write a small model, build its site, open the site in your browser and deploy it to a folder. Start in an empty folder, and check that you have what [Before you start](#before-you-start) lists.

### 1. Write a model file

Create the file `architecture/model.py` with the content below. It describes a shop: a customer, the shop system with two containers, a payment provider, and one view.

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

Do not call `w.save()` in the file. `buildzr build` runs the file and reads the workspace itself, so it does not need a JSON file.

### 2. Build the site

Run `buildzr build` and name the model file with `-w`:

```text
$ buildzr build -w architecture/model.py
built .buildzr/site (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
```

The output tells you three things. The site is in the folder `.buildzr/site`. The model has 5 elements, 3 relationships and 1 view. The modelHash identifies this model: if you build the same model again, you get the same hash.

If you leave out `-w`, the command stops and tells you what is missing:

```text
$ buildzr build
buildzr: error: no workspace given; pass --workspace FILE or set workspace: in buildzr.yaml
[exit code 2]
```

The command does not print the last line, `[exit code 2]`. On this page, such a line shows the exit code that the command returns. The [exit codes](#exit-codes) section lists them all.

To see more detail, add `-v`:

```text
$ buildzr build -w architecture/model.py -v
/home/you/shop/architecture/model.py: 5 elements, 3 relationships, 1 views, 3 levels -> /tmp/tmpab12cd/.build-x1y2z3/export
built .buildzr/site (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
```

The first line comes from the step that runs your model file. It counts what the step found, including the levels: the diagrams that the layout step draws. It also names a temporary folder, which changes on every run.

### 3. Save the model file name in `buildzr.yaml`

You can store the name of the model file so that you do not type it every time. Create a file called `buildzr.yaml` at the top of your project, next to the `.git` folder if you use Git:

```yaml
workspace: architecture/model.py
```

Now `buildzr build` finds the model file without `-w`:

```text
$ buildzr build
built .buildzr/site (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
```

### 4. Open the site in your browser

Start the server:

```text
$ buildzr serve
Serving /home/you/shop/.buildzr/site at http://127.0.0.1:8000/ (Ctrl+C to stop)
Model API at http://127.0.0.1:8000/api/v1/ (read only)
```

Open `http://127.0.0.1:8000/` in your browser. The viewer shows the landscape of your model. Click a box to see what is inside it.

The second output line names the [Model API](model-api.md). At that address, the server answers questions about your model as JSON, for scripts and other programs. You do not need it to view the diagrams.

To stop the server, press Ctrl+C in the terminal. If port 8000 is already in use, choose another port, for example `buildzr serve -p 8001`.

### 5. Deploy the site to a folder

To deploy, you add a target to `buildzr.yaml`. Here the target is called `www`. It is a `dir` target: a folder on this machine, for example a folder that a web server serves.

```yaml
workspace: architecture/model.py
default_target: www
targets:
  www: {dir: public/architecture}
```

`default_target` is the target that `deploy` uses when you do not name one with `-t`. The path `public/architecture` is relative to the folder that holds `buildzr.yaml`.

First, run a dry run. It builds the site and runs the site check, then shows what it would write. It writes nothing.

```text
$ buildzr deploy --dry-run
built (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
checked 12 files, 517 KB: no problems
dry run: would write 12 files, 517 KB to /home/you/shop/public/architecture (target www); nothing was written
```

Then deploy:

```text
$ buildzr deploy
built (5 elements, 3 relationships, 1 view; modelHash sha256:87716f3c5b04…)
writing 12 files, 517 KB to /home/you/shop/public/architecture (target www)
deployed www: modelHash sha256:87716f3c5b04…
```

The site is now in `public/architecture`. When you deploy again, `deploy` replaces the old copy in one step, and only after the new site passed the site check.

### Where to go next

- To deploy to an instance that other people reach over the network, read [Deploying to an instance](deploy.md).
- For ready-made setups, such as a preview of every pull request, read the [recipes](publishing-recipes.md).

## Command reference

### How the commands find their settings

Each setting comes from the first of these that has it:

1. An option on the command line.
2. `buildzr.yaml`.
3. The built-in default.

The tables below list every option. `buildzr COMMAND --help` prints the same list.

### `buildzr build`

```text
buildzr build [-h] [-w FILE] [--k N] [--text-color {wcag,c4}] [--no-viewer] [-c FILE] [-v] [-o DIR]
```

`build` runs your model file, lays out the diagrams and runs the site check. If a step fails, the previous site is left as it was.

| Option | What it does |
|---|---|
| `-w FILE`, `--workspace FILE` | The model file. Default: `workspace:` in `buildzr.yaml`. |
| `--k N` | A layout parameter, the frame budget: a frame that the layout reserves has at most `N` times the area of a box that contains no other boxes. A whole number of at least 1. Default: `build.k` in `buildzr.yaml`, else 4. |
| `--text-color {wcag,c4}` | How the text colour of a box is chosen when your styles do not set one. `wcag` picks black or white, whichever contrasts more with the box, following the Web Content Accessibility Guidelines (WCAG). `c4` uses the default C4 text colours. Default: `build.text_color`, else `wcag`. |
| `--no-viewer` | Write a data-only site: the model data without the viewer. |
| `-c FILE`, `--config FILE` | The config file. Default: `buildzr.yaml`, searched from the current folder upward. |
| `-v`, `--verbose` | Also show the line from the step that runs your model file. It counts the elements, relationships, views and levels, and names a temporary folder. Errors are always shown. |
| `-o DIR`, `--out DIR` | The folder to write the site to. Default: `build.out`, else `.buildzr/site`. |

### `buildzr serve`

```text
buildzr serve [-h] [--store DIR] [-p PORT] [--host HOST] [--public-url URL] [--cors-origin ORIGIN] [--accept-deploys] [--deploy-port N] [--max-upload-mb N] [DIR]
```

`serve` only reads: it answers `GET` and `HEAD` requests, and nothing can change a site through it. Besides the files of the site, it answers the [Model API](model-api.md) under `/api/v1/` and a generated `/llms.txt`: a short plain-text page that tells AI tools where the Model API is.

| Option | What it does |
|---|---|
| `DIR` | The site to serve. Default: `build.out` of the nearest `buildzr.yaml`, else `.buildzr/site`. |
| `--store DIR` | Serve every site of the [store](store.md) `DIR`, read only, instead of one site. |
| `-p PORT`, `--port PORT` | The port. Default 8000. |
| `--host HOST` | The address to listen on. Default `127.0.0.1`: only this machine can connect. To let other machines connect, pass `0.0.0.0`; do this only on purpose. |
| `--public-url URL` | The address at which readers open the site (`http://` or `https://`). The [Model API](model-api.md) builds its `viewerUrl` links from it. |
| `--cors-origin ORIGIN` | Let a web page from `ORIGIN` read the Model API from a browser (CORS, Cross-Origin Resource Sharing). Repeat the option for more origins. There is no wildcard. |
| `--accept-deploys` | Only with `--store`: also accept uploads from `buildzr deploy` on the deploy listener, which only this machine can reach. If the store folder is missing or empty, it is created. |
| `--deploy-port N` | The port of the deploy listener. Default 8001. The deploy listener always listens on `127.0.0.1`. |
| `--max-upload-mb N` | The largest upload accepted, in megabytes, compressed. Default 50. |

`--deploy-port` and `--max-upload-mb` work only together with `--accept-deploys`. `--accept-deploys` needs the `jsonschema` package; install it with `pip install 'buildzr[serve]'`.

### `buildzr deploy`

```text
buildzr deploy [-h] [-w FILE] [--k N] [--text-color {wcag,c4}] [--no-viewer] [-c FILE] [-v] [-t NAME] [--path P] [--from DIR] [--dry-run] [--rollback]
```

`deploy` builds the site and copies it to a target. A `dir` target receives the site in `<dir>/<path>/`. A `url` target points to an instance, which receives the site over the network; [Deploying to an instance](deploy.md) describes that flow. [`buildzr.yaml`](config.md) describes how to define targets.

| Option | What it does |
|---|---|
| `-t NAME`, `--target NAME` | The target in `buildzr.yaml`. Default: `default_target`. |
| `--path P` | The site path below the target. It overrides the `path` of the target. |
| `--from DIR` | Deploy a site that is already built, instead of building one. The build options are then refused. |
| `--dry-run` | Load the config, build the site and run the site check, then print what would happen. Nothing is written or sent. |
| `--rollback` | `url` targets only: make the previous release of the site current again. Nothing is built. |
| `-w`, `--workspace`, `--k`, `--text-color`, `--no-viewer`, `-c`, `--config`, `-v`, `--verbose` | The same as for `build`. |

### What `deploy` does with each kind of target

#### A `dir` target

A `dir` target receives the site in the folder `<dir>/<path>/`.

- `deploy` replaces the old copy in one step, and only after the new site passed the site check. If the check fails, the folder is left as it was.
- `deploy` refuses to replace a folder that exists, is not empty and is not a buildzr site (a buildzr site has a `build.json`). This stops a typo such as `dir: ~` from emptying your home folder.
- With an empty `path`, `deploy` replaces the whole `dir`. Give other sites a `dir` of their own, or give each site its own `path`.
- The parent folder of the destination must be writable. If it is not, `deploy` prints `buildzr: error: cannot write to <path>: <reason>` and exits with code 1.
- Without the `jsonschema` package, the site check skips its schema step. `deploy` prints `buildzr: warning: jsonschema is not installed; the site check skips the schema step` once and continues. Install the package with `pip install jsonschema` to get the full check.
- `--rollback` is not available, because a folder keeps no previous copy; `deploy` exits with code 2. To go back, deploy the older version again.

#### A `url` target

A `url` target sends the site to the deploy listener of an instance.

- The `url` must be on this machine: `127.0.0.1`, `localhost` or `[::1]`. To reach an instance on another machine, open an SSH tunnel, as [Deploying to an instance](deploy.md) shows.
- `--rollback` makes the previous release of the site current again.

#### Deploying an existing site with `--from`

`--from DIR` builds nothing. It runs the site check on the site in `DIR` and deploys it unchanged. Use it to send exactly the same files to several targets. A data-only site stays data-only, and a site with a viewer keeps its viewer, whatever the `viewer:` key of the target says.

### Options that older versions had

Older versions had the options `--target DIR` and `--base-path`. Both are gone:

- `--target` now takes the name of a target in `buildzr.yaml`, not a folder.
- The base path is now the site path: the `path` of the target, or `--path`.

To write a site to a one-off folder, use `buildzr build -o DIR`.

## Exit codes

| Code | Meaning |
|---|---|
| 0 | Success. A dry run and a deploy that changes nothing also exit with 0. |
| 1 | The build, the site check or the write failed; the instance rejected the site; the `url` is not a deploy listener; or the port is in use. |
| 2 | A usage or config error: an unknown option, no model file, a problem in `buildzr.yaml`, an unknown target, or a variable that is not set. |
| 3 | `deploy` to a `url` target could not finish: the instance cannot be reached, the upload was interrupted, the instance stayed busy, or the instance is out of disk space. Try again later. |

Error messages from the command start with `buildzr: error: `. Problems in `buildzr.yaml` are listed one per line, as `buildzr.yaml:<line>: <key>: <message>`.

In the examples on these pages, a last line such as `[exit code 2]` shows the exit code. The command does not print that line.
