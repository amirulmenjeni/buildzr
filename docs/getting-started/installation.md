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

For development work, you'll want to install the development dependencies:

```bash
pip install -e ".[dev]"
```

This will install additional tools including:

- `mypy` - Static type checker
- `pytest` - Testing framework
- `jsondiff` - JSON comparison for tests
- `datamodel-code-generator` - Code generation from schemas

## Using Conda

If you prefer using Conda, you can create an environment using the provided `environment.yml`:

```bash
conda env create -f environment.yml
conda activate buildzr-dev
```

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
