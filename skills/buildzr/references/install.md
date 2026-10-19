# Install buildzr and check the version

You need Python 3.10 or newer, and Node.js 18 or newer for the layout step of `buildzr build` (check with `node --version`). Serving workspaces that are already built (`buildzr serve --no-build`) does not need Node.

## Pick one way to install

| The project... | Run | Then run commands as |
|---|---|---|
| uses uv | `uv add buildzr` | `uv run buildzr build` |
| uses pip and a virtual environment | `pip install buildzr` | `buildzr build` |
| must not get a new dependency | nothing | `uvx buildzr build` |

- With `uvx`, buildzr exists only while the command runs. A model file that imports other packages needs them too: `uvx --with <package> buildzr build`.
- With `uvx`, `python workspaces/<name>.py` does not work, because the project's own Python has no buildzr. Use `uvx buildzr build` to run the files.

<!-- PRE-RELEASE NOTE: delete this block when buildzr 1.0.0 final is on PyPI. -->
> **Until 1.0.0 final is out, add `--pre`:** `pip install --pre buildzr`, `uv add --prerelease allow buildzr`, `uvx --prerelease allow buildzr build`.
<!-- END PRE-RELEASE NOTE -->

## Check the installation

`buildzr build` and `buildzr serve` need buildzr 1.0 or newer: the 0.0.x releases install no `buildzr` command at all. Run, with the prefix you picked above (`uv run`, nothing, or `uvx`):

```bash
buildzr serve --help
```

It must print `usage: buildzr serve [-h] [--no-build] [--rebuild] ...` and exit with code 0. Any of these means that the installed buildzr is 0.0.x or missing; install it again as above:

- `buildzr: command not found` (pip),
- ``error: Failed to spawn: `buildzr` `` (`uv run`),
- ``Package `buildzr` does not provide any executables.`` (`uvx`).

To see the installed version:

```bash
python -c "from importlib.metadata import version; print(version('buildzr'))"
```
