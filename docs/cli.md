# Command reference

The `buildzr` command turns an architecture model that you write in Python into a **site**: a folder of web pages that draws your diagrams in a browser. You can open the site on your own machine, or deploy it so that other people can open it.

This page is the reference of the command: every option, its default, and every exit code. To learn the commands step by step, follow the [Quick Start](getting-started/quick-start.md) (`build` and `serve`), then [Publish your first site](publish-first-site.md) (`deploy`).

The command has three subcommands:

- `buildzr build` runs your model file and writes the site.
- `buildzr serve` serves a site so that you can open it in a browser.
- `buildzr deploy` builds the site and copies it to a place that other people can reach.

## Find the page for your task

| You want to... | Read |
|---|---|
| Describe your architecture in Python | [Quick Start](getting-started/quick-start.md) and the [User Guide](user-guide/core-concepts.md) |
| Open your model in a browser | [Quick Start](getting-started/quick-start.md) |
| Deploy your model for other people | [Publish your first site](publish-first-site.md), then [Deploying to an instance](deploy.md) and the [recipes](publishing-recipes.md) |
| Let scripts, CI (continuous integration) jobs, dashboards and AI assistants read your model | [The Model API](model-api.md) |
| Run one shared instance: a `buildzr serve` that holds many sites | [The site store](store.md) and [Deploying to an instance](deploy.md) |
| Keep your settings in one file | [`buildzr.yaml`](config.md) |
| Link to one box of a diagram | [Viewer links](viewer-hash-routes.md) |

## Words used on this page

| Word | Meaning |
|---|---|
| **model file** | The Python file that creates your `Workspace`. You name it with the `--workspace` option or the `workspace:` key of `buildzr.yaml`. |
| **site** | The folder that `buildzr build` writes: the viewer, the model data and a file called `build.json`. |
| **deploy** | To copy a built site to a target with `buildzr deploy`, so that other people can open it. |
| **viewer** | The web page inside a site that draws the diagrams. A site built with `--no-viewer` has the model data only and is called a **data-only site**. |
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

## Requirements and installation

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

## Commands and their options

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
| `--k N` | Room for a box that contains other boxes, as a multiple of the area of an empty box. Raise it if the insides of such boxes are too small to read; lower it for compact diagrams. A whole number of at least 1. Default: `build.k` in `buildzr.yaml`, else 4. See [Choosing a value for `--k`](#choosing-a-value-for-k). |
| `--text-color {wcag,c4}` | How the text colour of a box is chosen when your styles do not set one. `wcag` picks black or white, whichever contrasts more with the box, following the Web Content Accessibility Guidelines (WCAG). `c4` uses the default C4 text colours. Default: `build.text_color`, else `wcag`. |
| `--no-viewer` | Write a data-only site: the model data without the viewer. |
| `-c FILE`, `--config FILE` | The config file. Default: `buildzr.yaml`, searched from the current folder upward. |
| `-v`, `--verbose` | Also show the line from the step that runs your model file. It counts the elements, relationships, views and levels, and names a temporary folder. Errors are always shown. |
| `-o DIR`, `--out DIR` | The folder to write the site to. Default: `build.out`, else `.buildzr/site`. |

### Choosing a value for `--k`

`--k` sets how much room the layout gives the inside of a box that contains other boxes, such as a software system with containers. The room for the inside is at most `N` times the area of an empty box; the box itself is a little larger, because it also holds its own name. `build.k` in `buildzr.yaml` sets the same value.

When you expand such a box in the viewer, its inside is drawn in that room. If the inside needs more room, it is shrunk to fit; it is never enlarged. For example, in the model `examples/buildzr_models_example.py` of the buildzr repository, the inside of the E-Commerce System is drawn at 23% of its full size with `--k 1`, 35% with 4 (the default), 50% with 9 and 68% with 16.

- **Raise the value** when the inside of an expanded box is too small to read. The cost: boxes with an inside take more room on the diagram of their parent, so the whole diagram is larger, and the viewer shows it smaller when it fits it to the screen.
- **Lower the value** for compact diagrams. You then zoom in to read the inside of an expanded box.
- Once a box has all the room its inside needs, the inside is drawn at full size, and a larger value changes nothing more for that box. In the example, the Order Service container reaches full size at 9.
- A model in which no box contains other boxes, such as the one in the [Quick Start](getting-started/quick-start.md), looks the same at every value.
- The value is a whole number of at least 1. The default is 4.

![The E-Commerce System expanded with --k 1: its five containers are small, and Order Service, which has two components, is about the same size as the empty boxes](images/cli/k-1-expanded-system.png)

*With `--k 1`, the containers fill a small area, and the viewer zooms in to show it. Order Service and Inventory Service, which contain components, are about the same size as the other containers.*

![The same system expanded with --k 9: Order Service and Inventory Service are much larger than the empty boxes, and the diagram is shown at a smaller zoom](images/cli/k-9-expanded-system.png)

*With `--k 9`, Order Service and Inventory Service get room for their components, so they are more than twice as wide and as tall as the other containers, and the viewer zooms out to fit the larger diagram.*

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
