# `buildzr.yaml`

One file per repository holds what the commands need besides flags: the workspace file, the build options and the named deploy targets. The file is optional.

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
| `build.out` | text (path) | `.buildzr/site` | Where `build` writes. |
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
