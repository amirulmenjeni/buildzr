# Installation

This page shows how to install buildzr for each way of using it, and how to check the installation.

## Requirements

- Python 3.10 or newer.
- Node.js 18 or newer, only on the machine that builds: `buildzr build`, and `buildzr serve` when a workspace is new or changed. The layout step of the build runs [elkjs](https://github.com/kieler/elkjs) on Node. Check your version with `node --version`. Serving workspaces that are already built (`buildzr serve --no-build`) and the Python API do not need Node.

buildzr supports every Python version that its CI (continuous integration) tests. New maintained Python versions are added when the dependencies support them. The oldest version is dropped only at its end of life, or when the tools make it impractical to keep.

## Install from PyPI

To add `buildzr` to a project that uses [uv](https://docs.astral.sh/uv/):

```bash
uv add buildzr
```

With `pip` instead: `pip install buildzr`. Both also install the `buildzr` command.

The right command depends on what you want to do:

| You want to... | Run |
|---|---|
| Write models | `uv add buildzr` (or `pip install buildzr`). Your model file imports `buildzr`, so buildzr must be in the environment of your project. |
| Try the command line, or run it once, for example in CI | `uvx buildzr build`. `uvx` runs buildzr in a temporary environment without installing it. `uvx buildzr serve` works the same way. |
| Keep the `buildzr` command on your machine | `uv tool install buildzr` |

`uvx buildzr build` works without buildzr in your project. But when you run the model file yourself (`python workspaces/model.py`) or edit it in your editor, your project's Python is used, and the import fails until you add buildzr to the project.

### Install a release candidate

A release candidate is a pre-release, such as `0.1.0rc1`. A plain `uv add buildzr` or `pip install buildzr` never installs one; ask for it by version:

```bash
uvx --from buildzr==0.1.0rc1 buildzr build
uv add buildzr==0.1.0rc1
pip install buildzr==0.1.0rc1
pip install --pre buildzr
```

### Optional Dependencies

#### `buildzr[export-plantuml]`

To export your diagrams to PlantUML, install the `export-plantuml` extra:

```bash
pip install "buildzr[export-plantuml]"
```

This extra needs Java 11 or newer, because it calls Structurizr's Java libraries through JPype. To render `svg` or `png`, you also need [Graphviz](https://graphviz.org/download/) (`dot`), unless you pass `layout='smetana'`. See the [Export](../user-guide/export.md) page.

## Install from Source

To install the latest development version from the source code:

```bash
git clone https://github.com/amirulmenjeni/buildzr.git
cd buildzr
pip install -e .
```

## Development Installation

For development work, install [uv](https://docs.astral.sh/uv/) and sync the locked environment:

```bash
uv sync --all-extras --locked
```

This installs every extra, including the development, documentation and PlantUML extras. Run tools in the project environment with `uv run`, for example:

```bash
uv run pytest --mypy tests
```

The lock file `uv.lock` makes the dependencies of local development and of CI the same. To work on the documentation or to run the full test suite, use the devcontainer; see the [Contributing Guide](../contributing.md).

## Verification

To check your installation, import `buildzr`:

```python
# norun
from buildzr.dsl import Workspace, SoftwareSystem, Person
print("buildzr installed successfully!")
```

Or print the installed version:

```python
# norun
from importlib.metadata import version
print(version("buildzr"))
```

## Next Steps

To create your first architecture diagram, continue with the [Quick Start Guide](quick-start.md). To serve several models, and let other people open them, continue with [Serve your workspaces](../serve-workspaces.md).
