# Installation

## Requirements

- Python 3.10 or higher

## Install from PyPI

The easiest way to install `buildzr` is using `pip`:

```bash
pip install buildzr
```

### Optional Dependencies

#### `buildzr[export-plantuml]`

To export your architecture diagrams directly to PlantUML format, install with the `export-plantuml` extra:

```bash
pip install "buildzr[export-plantuml]"
```

Note: This requires Java 11+ to be installed on your system, as it uses Structurizr's Java libraries under the hood via JPype.

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
uv sync --all-extras --locked --python 3.10
```

This installs the development, documentation, and PlantUML extras. Run tools through the
project environment with `uv run`, for example:

```bash
uv run --python 3.10 pytest --mypy tests
```

The project supports Python 3.10, 3.11, 3.12, and 3.13. Use the Python minor
version you want to work with in both commands; the checked-in `uv.lock` keeps
the resulting environment reproducible. See the [Python support policy](../support-policy.md)
for how the supported matrix is maintained.

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
from buildzr.__about__ import __version__
print(f"buildzr version: {__version__}")
```

## Next Steps

Now that you have `buildzr` installed, head over to the [Quick Start Guide](quick-start.md) to create your first architecture diagram!
