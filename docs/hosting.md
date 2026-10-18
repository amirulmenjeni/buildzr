# Hosting the built workspaces elsewhere

`buildzr serve` is the simplest way to let people open your workspaces, but you may already have a web server, or a static host that publishes a folder. This page says which parts of a built workspace work there and which need `buildzr serve`, and how to copy the build output.

## Words used on this page

| Word | Meaning |
|---|---|
| **built workspace** | The folder that `buildzr build` writes for one workspace: the viewer, the model data and `build.json`. |
| **build output** | The folder that holds every built workspace, one subfolder per workspace. Default: `.buildzr/build`. |
| **static host** | Any web server that only sends files as they are, such as nginx, Apache, GitHub Pages or an object store with web hosting. |

## What works without `buildzr serve`

A built workspace uses relative addresses only, so it works at any path of any web server:

| Part | On a static host | Why |
|---|---|---|
| The viewer (`index.html`, `assets/`) | Works | The viewer loads its scripts with relative addresses (`./assets/...`). |
| The model data (`data/index.json`, `data/model.<hash>.json`, `data/scene/...`) | Works | The viewer reads only these files, with relative addresses. |
| Viewer links (`#/m/...`, `#/v/...`) | Work | The part after `#` never reaches the server. See [Viewer links](viewer-hash-routes.md). |
| The [Model API](model-api.md) (`api/v1/`) | Does not work | `buildzr serve` computes each answer; there are no files for it. |
| `llms.txt` | Does not work | `buildzr serve` generates it from the model. |
| The list of workspaces at `/` and `/_buildzr/v1/workspaces` | Does not work | `buildzr serve` makes them from the build output. Link to each workspace yourself. |

A static host that shows the files of a folder at its address also shows `build.json`, which holds the version of buildzr, the build options, whether the workspace is broken (with its errors), the path of the model file inside your workspaces folder and the path of the workspaces folder relative to the build output. Nothing else of your project is in a built workspace.

A broken workspace works on a static host too: its viewer reads `build.json` and shows that it is broken. See [When a workspace is broken](cli.md#when-a-workspace-is-broken).

## Copy the build output

Build first, then copy the content of the build output to the folder that your web server publishes. With `rsync`, `--delete` also removes workspaces that you no longer build:

```bash
buildzr build
rsync -a --delete .buildzr/build/ host:/var/www/architecture/
```

Each workspace is then at `https://<your host>/architecture/<name>/`. Link to it with the trailing `/`: the viewer loads its files relative to that address, so `/architecture/<name>` without the `/` works only where the web server adds it.

`buildzr build` writes each workspace to a temporary folder first and renames it into place, so the build output itself is never half written. A copy is not atomic: while `rsync` runs, a reader may get files of the old and the new build for a moment. Reloading the page fixes it.

## When you need the Model API

If scripts or AI assistants must ask questions about the model, run `buildzr serve` with the build output, on the server or behind your web server:

```bash
buildzr serve --no-build --host 127.0.0.1 --public-url https://architecture.example.com
```

`--no-build` serves the folder as it is, so the server needs neither the model files nor Node. Point your web server's proxy at `http://127.0.0.1:8000/`. [Serve your workspaces](serve-workspaces.md#7-let-other-people-open-the-workspaces) explains `--public-url` and `--cors-origin`.
