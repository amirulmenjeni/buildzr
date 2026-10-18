# `buildzr.yaml`

`buildzr.yaml` is the config file of your project. It holds what the `buildzr` commands need besides their options: the name of your model file, the build settings and the targets that `buildzr deploy` copies the site to. The file is optional; without it, you pass everything as options.

This page is a reference. It lists where the commands look for the file, every key, how values are read, example files and the error messages. The options of each command are in the [Command reference](cli.md).

## Words used on this page

| Word | Meaning |
|---|---|
| **model file** | The Python file that creates your `Workspace`. The `workspace:` key names it. |
| **site** | The folder that `buildzr build` writes: the viewer, the model data and a file called `build.json`. |
| **data-only site** | A site without the viewer, only the model data. |
| **deploy** | To copy a built site to a target with `buildzr deploy`. |
| **target** | A named destination in this file. A `dir` target is a folder on this machine. A `url` target points to the deploy listener of an instance. |
| **instance** | A running `buildzr serve --store DIR`: one process that serves every site of a store. With `--accept-deploys`, it also accepts new sites from `buildzr deploy`. |
| **deploy listener** | The port of an instance that accepts uploads from `buildzr deploy`. It is always on `127.0.0.1`. |
| **site path** | Where a site sits below the address of its target. With the site path `pr/42`, the site is served at `/pr/42/`. Empty means the top. |

## How the commands use this file

Each setting comes from the first of these that has it:

1. An option on the command line.
2. `buildzr.yaml`.
3. The built-in default.

No environment variable sets a setting directly. You can use environment variables only inside the file, as [`${VAR}`](#values-from-environment-variables).

Each command reads a different part of the file:

- `buildzr build` reads `workspace` and the `build` keys.
- `buildzr serve` reads only `build.out`, to find the site. When you name a site folder on the command line, `serve` does not read the file at all.
- `buildzr deploy -t NAME` reads the target `NAME` (or `default_target` without `-t`), and everything that `build` reads.

When the file has a problem, the command prints every problem, one per line, and exits with code 2. [Examples of error messages](#examples-of-error-messages) shows the format.

## Where the commands find the file

Without the `-c` option, a command looks for the file as follows:

- It starts in the current folder and walks up to the parent folders. The first `buildzr.yaml` it finds is used.
- It stops after the folder that contains `.git`, so it never reads a file outside your Git repository.
- The name must be exactly `buildzr.yaml`. If a folder has `buildzr.yml` or `.buildzr.yaml` and no `buildzr.yaml`, the search stops with `found buildzr.yml; the config file must be named buildzr.yaml`.

Relative paths in the file are relative to the folder that holds the file, not to the current folder.

## Keys

| Key | Type | Default | Meaning |
|---|---|---|---|
| `version` | integer | `1` | The version of the file format. Only `1` is accepted. |
| `workspace` | text (path) | none | The model file. |
| `build.k` | whole number, at least 1 | `4` | The layout parameter that `--k` also sets (the frame budget). See [`buildzr build`](cli.md#buildzr-build). |
| `build.text_color` | `wcag` or `c4` | `wcag` | How the text colour of a box is chosen. See `--text-color` in [`buildzr build`](cli.md#buildzr-build). |
| `build.viewer` | `true` / `false` | `true` | `false` builds a data-only site. |
| `build.out` | text (path) | `.buildzr/site` | The folder that `build` writes to and that `serve` reads by default. |
| `default_target` | text | the only target, if there is exactly one | The target that `deploy` uses without `-t`. Must name a key of `targets`. |
| `targets.<name>` | mapping | none | One target. Names match `[a-z][a-z0-9_-]*`. |
| `targets.<name>.dir` | text (path) | none | A folder on this machine. A target has exactly one of `dir` and `url`. |
| `targets.<name>.url` | text | none | The deploy listener of an instance, `http://127.0.0.1:<port>`. The instance runs on this machine, or you reach it through an SSH tunnel; see [Deploying to an instance](deploy.md). A target has exactly one of `dir` and `url`. |
| `targets.<name>.path` | text | `""` (the top) | The site path. Segments match `[a-z0-9][a-z0-9._-]*`; `..` is not allowed. A leading and a trailing `/` are removed. |
| `targets.<name>.viewer` | `true` / `false` | `build.viewer` | `false` deploys a data-only site to this target. |
| `targets.<name>.timeout` | number of seconds above 0 | `120` | `url` targets only. |

Unknown keys are errors. The key `token_env` is reserved and rejected in this version.

Secrets never go in this file. The keys `token`, `password` and `secret` are refused.

To let your editor check the file, use the JSON Schema `buildzr/site/schema/config.schema.json`. Add `# yaml-language-server: $schema=<path or URL of the schema>` as the first line of the file.

## Values from environment variables

You can use environment variables in these text values: `workspace`, `build.out`, `dir`, `url` and `path`.

- Write `${NAME}`, where `NAME` matches `[A-Z_][A-Z0-9_]*`. Write `${NAME:-fallback}` to use `fallback` when the variable is unset or empty. Write `$$` for a literal `$`. Any other `$` is an error.
- A variable that is unset or empty, and has no fallback, is an error.
- A value is expanded only when a command uses it. For example, `deploy -t dev` does not fail on a variable that only the target `prod` uses.
- The expanded value is checked like a written one. For example, `path` is checked against the site path rules after expansion.

## How the file is read

The file is YAML, read with stricter rules than most YAML tools use:

- Only `true`, `false`, `null`, plain decimal integers (`4`) and plain decimal numbers (`1.5`) are typed. Everything else is text, including `yes`, `no`, `on`, `off`, `y`, `n`, `0755`, `1:30` and dates. A key `on:` stays the text `on`.
- Types are checked, not converted: `k: "4"` is an error.
- Duplicate keys, anchors (`&a`), aliases (`*a`), `<<` merges and `!tags` are errors.
- All problems are listed at once, each as `buildzr.yaml:<line>: <key>: <message>`.

## Example files

A single author who only builds and serves:

```yaml
workspace: architecture/model.py
```

Deploy to a folder that a web server serves, and a data-only site to a second folder:

```yaml
workspace: model.py
targets:
  www:  {dir: /var/www/architecture}
  data: {dir: /srv/buildzr-data, viewer: false}
```

A team with an instance for pull request previews, and a production instance:

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

## Examples of error messages

Each message names the line of the file and the key it is about.

A value of the wrong type:

<!-- doctest: invalid -->
```yaml
workspace: architecture/model.py
build:
  k: four
```

```text
buildzr.yaml:3: build.k: expected a whole number of at least 1, got the text "four"
```

A secret in the file. The message tells you where to keep it instead:

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

An environment variable that is not set. This uses the team example above, without `PR_NUMBER` set. The variable must be set because the target you deploy to uses it:

```text
$ buildzr deploy -t preview
buildzr.yaml:7: targets.preview.path: environment variable PR_NUMBER is not set (used in "pr/${PR_NUMBER}")
[exit code 2]
```

A target that does not exist. The message lists the targets that do:

```text
$ buildzr deploy -t staging
buildzr: error: no target named "staging"; targets in /home/you/shop/buildzr.yaml: dev (default), preview, prod
[exit code 2]
```

The last line of each command example, such as `[exit code 2]`, shows the exit code. The command does not print it.

## Python functions

The module `buildzr.site.config` has these functions for scripts and tests: `find_config(start)`, `load_config(path)`, `resolve_target(cfg, name, env)`, `resolve_build(cfg, env)` and `resolve_workspace(cfg, env)`. Problems raise `ConfigError`. `load_config` does not read environment variables; the `resolve_*` functions do.
