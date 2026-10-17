# `buildzr.yaml`

One file per repository holds what the commands need besides flags: the workspace file, the build options and the named deploy targets. The file is optional.

## Commands

Every setting comes from a command-line flag first, then from `buildzr.yaml`, then from the built-in default. No environment variable sets a setting directly; `${VAR}` works only inside the file.

```text
buildzr build [-w FILE] [-o DIR] [--k N] [--text-color wcag|c4] [--no-viewer] [-c FILE]
buildzr serve [DIR | --store DIR] [-p PORT] [--host HOST] [--public-url URL] [--cors-origin ORIGIN]...
buildzr deploy [-t NAME] [--path P] [--from DIR] [--dry-run] [-w FILE] [--k N] [--text-color wcag|c4] [--no-viewer] [-c FILE]
```

Without `-c`, the file is searched from the current folder upward (see below). The same five steps cover a normal week:

1. `buildzr build` writes the site to `build.out` (default `.buildzr/site`). `workspace:` in the file saves typing `--workspace`; with neither, the command stops with exit code 2. `build.viewer: false` and `--no-viewer` both write data only.
2. `buildzr serve` serves `build.out` of the nearest `buildzr.yaml` (else `.buildzr/site`) at `http://127.0.0.1:8000/`. It is read-only: GET and HEAD only. `buildzr serve DIR` does not read the config. Besides the files, it answers the [agent API](agent-api.md) under `/api/v1/` and a generated `/llms.txt`. Two flags belong to that API:
    - `--public-url URL` is the address readers use for the site (`http://` or `https://`, a trailing `/` is dropped, no query or fragment). The API builds its `viewerUrl` links from it. Without it the links start with `/`. A site built with `viewer: false` has no viewer to link to, so its links are `null` unless `--public-url` names the place where a viewer is.
    - `--cors-origin ORIGIN` lets a web page from that origin (for example `https://tool.example.com`, no path) read the API from a browser. Repeat it for more origins. There is no wildcard. Without the flag the API sends no CORS headers.

    `buildzr serve --store DIR` serves every site of a [store](store.md) folder (for example the main model at `/` and a preview at `/pr/42/`), each with its own API, and lists them at `/_buildzr/v1/sites`. `DIR` must already be a store; `--store` cannot be combined with a site `DIR`; `--public-url` and `--cors-origin` apply as above. In this version a store is **read-only**: uploads and `deploy` to an instance come later.
3. `buildzr deploy -t NAME` builds the site and writes it to the target. A `dir` target gets the site in `<dir>/<path>/`; the old copy is replaced as one step, and the checker must pass on the new one first. The command refuses to replace a folder that is not a buildzr site (no `build.json`). With `path` empty the whole `dir` is replaced, so keep other sites in a `dir` of their own or give each its own `path`. Without `-t`, `default_target` is used. `--path P` overrides the target's `path`. If the destination cannot be written (for example its parent folder is read-only), the command prints `buildzr: error: cannot write to <path>: <reason>` and exits with code 1. If the `jsonschema` package is not installed, the check of the built site skips the schema step and `deploy` says so with one warning line on stderr (`buildzr: warning: jsonschema is not installed; the site check skips the schema step`).
4. `buildzr deploy -t NAME --dry-run` loads the file, expands the variables, builds, runs the checker, prints the resolved target with the file count and size, and writes nothing to the target.
5. `buildzr deploy -t NAME --from DIR` deploys an already built site (for example one site to several targets) without building. The build flags cannot be combined with `--from`.

`url` targets (a running instance) are not available in this version: `deploy` exits with code 1 and says so. `--rollback` is not built yet (exit code 2). The old `--target DIR` and `--base-path` flags are gone: `--target` is a target name, and `--base-path` is the target's `path` (or `--path`). To write a site to a one-off folder, use `buildzr build -o DIR`.

| Exit code | Meaning |
|---|---|
| 0 | Done (also a dry run). |
| 1 | The build, the checker or the write failed (also a destination that cannot be written); a `url` target; the port is in use. |
| 2 | Usage or config error: unknown flag, no workspace, a problem in `buildzr.yaml`, an unknown target, a variable that is not set, a bad `--public-url` or `--cors-origin`. |

The CLI's own errors start with `buildzr: error: `. Problems in the config file are printed exactly as listed below, one per line.

## Where it is found

- Start in the current folder and walk up. The first `buildzr.yaml` wins. The search stops after the folder that contains `.git`.
- The name must be exactly `buildzr.yaml`. If a folder has `buildzr.yml` or `.buildzr.yaml` and no `buildzr.yaml`, the search stops with `found buildzr.yml; the config file must be named buildzr.yaml`.
- Relative paths in the file are relative to the folder that holds the file, not to the current folder.

## Keys

| Key | Type | Default | Notes |
|---|---|---|---|
| `version` | integer | `1` | Only `1` is accepted. |
| `workspace` | text (path) | none | The DSL `.py` file. |
| `build.k` | whole number, at least 1 | `4` | Layout frame budget. |
| `build.text_color` | `wcag` or `c4` | `wcag` | Node text colour rule. |
| `build.viewer` | `true` / `false` | `true` | `false` writes data only. |
| `build.out` | text (path) | `.buildzr/site` | Where `build` writes and `serve` reads by default. |
| `default_target` | text | the only target, if there is exactly one | Must name a key of `targets`. |
| `targets.<name>` | mapping | none | Names match `[a-z][a-z0-9_-]*`. |
| `targets.<name>.dir` | text (path) | none | A folder on this machine. Exactly one of `dir` and `url`. |
| `targets.<name>.url` | text | none | `http://` or `https://` address of a running instance. Exactly one of `dir` and `url`. |
| `targets.<name>.path` | text | `""` (the root) | Site path. Segments match `[a-z0-9][a-z0-9._-]*`, no `..`; a leading and a trailing `/` are removed. |
| `targets.<name>.viewer` | `true` / `false` | `build.viewer` | |
| `targets.<name>.timeout` | number of seconds above 0 | `120` | `url` targets only. |

Unknown keys are errors. `token_env` is reserved and rejected in this version. Secrets never go in this file: `token`, `password` and `secret` are refused.

An editor can check the file with the JSON Schema `buildzr/site/schema/config.schema.json`. Add `# yaml-language-server: $schema=<path or URL of the schema>` as the first line.

## Reading rules

- Only `true`, `false`, `null`, plain decimal integers (`4`) and plain decimal numbers (`1.5`) are typed. `yes`, `no`, `on`, `off`, `y`, `n`, `0755`, `1:30` and dates stay text. A key `on:` stays the text `on`.
- Types are checked, not converted: `k: "4"` is an error.
- Duplicate keys, anchors (`&a`), aliases (`*a`), `<<` merges and `!tags` are errors.
- All problems are listed at once, each as `buildzr.yaml:<line>: <key>: <message>`.

## `${VAR}`

In the text values `workspace`, `build.out`, `dir`, `url` and `path`:

- `${NAME}` (NAME matches `[A-Z_][A-Z0-9_]*`), `${NAME:-fallback}`, and `$$` for a literal `$`. Any other `$` is an error.
- A variable that is unset or empty, and has no fallback, is an error.
- A value is expanded only when a command uses it. `deploy -t dev` does not fail on a variable that only `prod` uses.
- The expanded value is checked like a written one, so `path` is checked after expansion.

## Examples

A single person, no instance:

```yaml
workspace: architecture/model.py
```

A team with a preview instance for pull requests and a production instance:

```yaml
version: 1
workspace: architecture/model.py
build: {k: 4, text_color: wcag}
default_target: dev
targets:
  dev:     {url: "http://127.0.0.1:8001"}
  preview: {url: "http://127.0.0.1:9001", path: "pr/${PR_NUMBER}"}
  prod:    {url: "http://127.0.0.1:9101"}
```

A static web server folder and a data-only copy:

```yaml
workspace: model.py
targets:
  www:  {dir: /var/www/architecture}
  data: {dir: /srv/buildzr-data, viewer: false}
```

## The four messages

```text
buildzr.yaml:4: build.k: expected a whole number of at least 1, got the text "four"
buildzr.yaml:9: targets.prod: unknown key "token". Secrets never go in this file; keep them in an environment variable.
buildzr.yaml:8: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")
buildzr: error: no target named "staging"; targets in /repo/buildzr.yaml: dev (default), preview, prod
```

## Python API

`buildzr.site.config` has `find_config(start)`, `load_config(path)`, `resolve_target(cfg, name, env)`, `resolve_build(cfg, env)`, `resolve_workspace(cfg, env)` and `ConfigError`. `load_config` does not read the environment; the `resolve_*` functions do.
