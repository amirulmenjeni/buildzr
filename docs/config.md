# `buildzr.yaml`

`buildzr.yaml` is the config file of your project. It holds what the `buildzr` commands need besides their options: where your workspaces folder is and the build settings. The file is optional; without it, the commands use the folder `workspaces` and the defaults.

This page is a reference. It lists where the commands look for the file, every key, how values are read, example files and the error messages. The options of each command are in the [Command reference](cli.md).

## Words used on this page

| Word | Meaning |
|---|---|
| **workspaces folder** | The folder of Python files that create your workspaces. The `workspaces:` key names it. |
| **built workspace** | The folder that `buildzr build` writes for one workspace: the viewer, the model data and a file called `build.json`. |
| **build output** | The folder that holds every built workspace. The `build.out` key names it. |
| **data-only workspace** | A built workspace without the viewer, only the model data. |

## How the commands use this file

Each setting comes from the first of these that has it:

1. An option on the command line.
2. `buildzr.yaml`.
3. The built-in default.

No environment variable sets a setting directly. You can use environment variables only inside the file, as [`${VAR}`](#values-from-environment-variables).

`buildzr build` and `buildzr serve` read the whole file, so a problem anywhere in it stops either command. `build` uses `workspaces` and `build`; it never uses `serve`. When you give `serve` a folder that already holds built workspaces, it uses only the `serve` settings of the file.

When the file has a problem, the command prints every problem, one per line, and exits with code 2. [Examples of error messages](#examples-of-error-messages) shows the format.

## Where the commands find the file

Without the `-c` option, a command looks for the file as follows:

- It starts in the current folder and walks up to the parent folders. The first `buildzr.yaml` it finds is used.
- It stops after the folder that contains `.git`, so it never reads a file outside your Git repository.
- The name must be exactly `buildzr.yaml`. If a folder has `buildzr.yml` or `.buildzr.yaml` and no `buildzr.yaml`, the search stops with `found buildzr.yml; the config file must be named buildzr.yaml`.

Relative paths in the file are relative to the folder that holds the file, not to the current folder. Without a file, the default folders `workspaces` and `.buildzr/build` are relative to the current folder.

## Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `version` | integer | `1` | The version of the file format. Only `1` is accepted. |
| `workspaces` | text (path) | `workspaces` | The workspaces folder. A path to a single `.py` file also works. |
| `build.k` | whole number, at least 1 | `4` | Room for a box that contains other boxes, as a multiple of the area of an empty box; the same value as `--k`. See [Choosing a value for `--k`](cli.md#choosing-a-value-for-k). |
| `build.text_color` | `wcag` or `c4` | `wcag` | The text colour on boxes. See `--text-color` in [`buildzr build`](cli.md#buildzr-build). |
| `build.viewer` | `true` / `false` | `true` | `false` builds data-only workspaces. |
| `build.out` | text (path) | `.buildzr/build` | The build output: `build` writes one folder per workspace into it, and `serve` serves it. |
| `serve.public_url` | text (`http://` or `https://` URL) | none | The address at which readers reach the server, for example behind a proxy; the same value as `--public-url`. The links of the [Model API](model-api.md) (`viewerUrl`, `apiUrl`) start with it. A `/` at the end is dropped. Without it, the links start with `/`. |
| `serve.port` | whole number, 1 to 65535 | `8000` | The port `serve` listens on; the same value as `-p`/`--port`. |
| `serve.host` | text | `127.0.0.1` | The address `serve` listens on; the same value as `--host`. `127.0.0.1` lets only this machine connect. `0.0.0.0` shares the server with every machine on the network, and `serve` has no login, so set it only on purpose. |
| `serve.cors_origins` | list of text | `[]` | The web origins (`https://host[:port]`, no path, no `*`) whose pages may read the Model API from a browser; the same values as repeated `--cors-origin`. An empty list means none. `--cors-origin` on the command line **replaces** this list; it does not add to it. |

Unknown keys are errors. Secrets never go in this file: the keys `token`, `password` and `secret` are refused.

Keys of older versions are refused with a line that says what to do: `workspace` (use `workspaces`), and `targets` and `default_target` (`buildzr deploy` no longer exists).

To let your editor check the file, use the JSON Schema `buildzr/site/schema/config.schema.json`. Add `# yaml-language-server: $schema=<path or URL of the schema>` as the first line of the file.

## Values from environment variables

You can use environment variables in the text values `workspaces`, `build.out`, `serve.public_url`, `serve.host` and each entry of `serve.cors_origins`. Not in `serve.port`, which is a number.

- Write `${NAME}`, where `NAME` matches `[A-Z_][A-Z0-9_]*`. Write `${NAME:-fallback}` to use `fallback` when the variable is unset or empty. Write `$$` for a literal `$`. Any other `$` is an error.
- A variable that is unset or empty, and has no fallback, is an error.
- A value is expanded only when a command uses it.

## How the file is read

The file is YAML, read with stricter rules than most YAML tools use:

- Only `true`, `false`, `null`, plain decimal integers (`4`) and plain decimal numbers (`1.5`) are typed. Everything else is text, including `yes`, `no`, `on`, `off`, `y`, `n`, `0755`, `1:30` and dates. A key `on:` stays the text `on`.
- Types are checked, not converted: `k: "4"` is an error.
- Duplicate keys, anchors (`&a`), aliases (`*a`), `<<` merges and `!tags` are errors.
- All problems are listed at once, each as `buildzr.yaml:<line>: <key>: <message>`.

## Example files

A project whose models live in another folder:

```yaml
workspaces: architecture
```

A project that builds data-only workspaces, with more room for boxes that contain other boxes, into a folder named after the Git branch:

```yaml
version: 1
workspaces: architecture
build:
  k: 9
  viewer: false
  out: "public/${BRANCH:-main}"
```

Settings for `buildzr serve` on a shared machine behind a proxy. Each one is used only when its option is not given on the command line. Set `public_url` in the file when the same project is served at a different address in each environment, such as a preview per branch: the variable gives the address, so the command stays the same everywhere.

```yaml
serve:
  public_url: "https://${PREVIEW_HOST:-architecture.example.com}"
  port: 8080
  host: 0.0.0.0
  cors_origins:
    - https://dashboard.example.com
```

## Examples of error messages

Each message names the line of the file and the key it is about.

A value of the wrong type:

<!-- doctest: invalid -->
```yaml
workspaces: architecture
build:
  k: four
```

```text
buildzr.yaml:3: build.k: expected a whole number of at least 1, got the text "four"
```

A secret in the file. The message tells you where to keep it instead:

<!-- doctest: invalid -->
```yaml
workspaces: architecture
build:
  token: abc123
```

```text
buildzr.yaml:3: build: unknown key "token". Secrets never go in this file; keep them in an environment variable.
```

A file written for an older version:

<!-- doctest: invalid -->
```yaml
workspace: architecture/model.py
targets:
  www: {dir: /var/www/architecture}
```

```text
buildzr.yaml:1: workspace: removed: use workspaces: (a folder; a single .py file path also works)
buildzr.yaml:2: targets: removed: buildzr deploy no longer exists; delete this key
```

An environment variable that is not set. This uses the second example file above, with `out: "public/${BRANCH}"` and no fallback:

```yaml
workspaces: architecture
build:
  out: "public/${BRANCH}"
```

```text
$ buildzr build
buildzr.yaml:3: build.out: environment variable BRANCH is not set (used in "public/${BRANCH}")
[exit code 2]
```

The last line of each command example, such as `[exit code 2]`, shows the exit code. The command does not print it.

## Python functions

The module `buildzr.site.config` has these functions for scripts and tests: `find_config(start)`, `load_config(path)`, `resolve_workspaces(cfg, env)` and `resolve_build(cfg, env)`. Problems raise `ConfigError`. `load_config` does not read environment variables; the `resolve_*` functions do.
