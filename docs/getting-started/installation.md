# Installation

## Requirements

- Python 3.10 or higher
- Node.js 18 or newer, only on the machine that runs `buildzr build` (or `buildzr deploy`, which builds first). The layout step of the build runs [elkjs](https://github.com/kieler/elkjs) on Node. Check with `node --version`. `buildzr serve` and the Python API need no Node.

The project follows a rolling support policy: CI tests every advertised Python
minor version, new maintained versions are added when supported by dependencies,
and the oldest version is dropped only at end-of-life or when tooling makes it impractical.

## Install from PyPI

The easiest way to add `buildzr` to a project is with [uv](https://docs.astral.sh/uv/):

```bash
uv add buildzr
```

With `pip` instead: `pip install buildzr`.

Which command to use depends on what you want:

- **Writing models.** Your model file imports `buildzr`, so it must be in the project's environment: `uv add buildzr` (or `pip install buildzr`). `uvx` is not for this; the import fails there.
- **Trying the command line, or running it once (for example in CI).** `uvx buildzr build` runs buildzr in an isolated environment without installing it. `serve` and `deploy` work the same way.
- **Keeping the `buildzr` command on your machine.** `uv tool install buildzr`.

To try a release candidate (a pre-release such as `0.1.0rc1`), ask for it by
version. A plain `uv add buildzr` or `pip install buildzr` never installs one.

```bash
uvx --from buildzr==0.1.0rc1 buildzr build
uv add buildzr==0.1.0rc1
pip install buildzr==0.1.0rc1
pip install --pre buildzr
```

### Optional Dependencies

#### `buildzr[export-plantuml]`

To export your architecture diagrams directly to PlantUML format, install with the `export-plantuml` extra:

```bash
pip install "buildzr[export-plantuml]"
```

Note: This requires Java 11+ to be installed on your system, as it uses Structurizr's Java libraries under the hood via JPype.
Rendering `svg`/`png` additionally needs [Graphviz](https://graphviz.org/download/) (`dot`),
unless you pass `layout='smetana'`. See the [Export](../user-guide/export.md) page.

## Install from Source

If you want to install the latest development version from source:

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

This installs the development, documentation, and PlantUML extras. Run tools through the
project environment with `uv run`, for example:

```bash
uv run pytest --mypy tests
```

The lockfile keeps local development and CI dependencies reproducible.

## Verification

To verify your installation, try importing `buildzr`:

```python
# norun
from buildzr.dsl import Workspace, SoftwareSystem, Person
print("buildzr installed successfully!")
```

Or check the version:

```python
# norun
from importlib.metadata import version
print(version("buildzr"))
```

## Next Steps

Now that you have `buildzr` installed, head over to the [Quick Start Guide](quick-start.md) to create your first architecture diagram!
