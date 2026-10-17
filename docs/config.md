# `buildzr.yaml`

One file per repository holds what the commands need besides flags: the workspace file, the build options and the named deploy targets. The file is optional.

## How the commands use this file

Every setting comes from a command-line flag first, then from `buildzr.yaml`, then from the built-in default. No environment variable sets a setting directly; `${VAR}` works only inside the file (see below).

The three commands, their flags and their exit codes are on the [Command line](cli.md) page. In short:

- `buildzr build` reads `workspace` and `build.*`. `buildzr serve` reads `build.out` only, and not at all when you give it a folder.
- `buildzr deploy -t NAME` reads the target `NAME` (or `default_target`) and everything `build` reads.
- A `dir` target is a folder on this machine. A `url` target is the deploy address of a running instance; see [Deploying to an instance](deploy.md).

Without `-c`, the file is searched from the current folder upward (see below). Problems in the file are printed exactly as listed in [the four messages](#the-four-messages), one per line, and the command exits with code 2.

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
| `targets.<name>.url` | text | none | The deploy address of a running instance, `http://127.0.0.1:<port>` (on this machine or through an SSH tunnel; see [deploy](deploy.md)). Exactly one of `dir` and `url`. |
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

One author, no instance:

```yaml
workspace: architecture/model.py
```

A static web server folder and a data-only copy:

```yaml
workspace: model.py
targets:
  www:  {dir: /var/www/architecture}
  data: {dir: /srv/buildzr-data, viewer: false}
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

## The four messages

Each message names the line of the file and the key it is about. First, a value of the wrong kind:

<!-- doctest: invalid -->
```yaml
workspace: architecture/model.py
build:
  k: four
```

```text
buildzr.yaml:3: build.k: expected a whole number of at least 1, got the text "four"
```

Secrets never go in the file. The message says where to keep them instead:

<!-- doctest: invalid -->
```yaml
workspace: architecture/model.py
targets:
  prod:
    url: "http://127.0.0.1:9101"
    token: abc123
```

```text
buildzr.yaml:5: targets.prod: unknown key "token". Secrets never go in this file; keep them in an environment variable.
```

A `${VAR}` that is used by the target you deploy to must be set. With the team example above and no `PR_NUMBER`:

```text
$ buildzr deploy -t preview
buildzr.yaml:7: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")
[exit code 2]
```

And a target that does not exist lists the ones that do:

```text
$ buildzr deploy -t staging
buildzr: error: no target named "staging"; targets in /home/you/shop/buildzr.yaml: dev (default), preview, prod
[exit code 2]
```

## Python API

`buildzr.site.config` has `find_config(start)`, `load_config(path)`, `resolve_target(cfg, name, env)`, `resolve_build(cfg, env)`, `resolve_workspace(cfg, env)` and `ConfigError`. `load_config` does not read the environment; the `resolve_*` functions do.
