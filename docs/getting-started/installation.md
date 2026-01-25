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

**System Requirements:**

| Requirement | Version | Purpose |
|-------------|---------|---------|
| Java (JDK or JRE) | 11+ | Required for all PlantUML exports (`.puml`, `.svg`, `.png`) |
| Graphviz (`dot`) | Any recent version | Required only for rendering to `.svg` or `.png` |

**Installing Java:**

- **Ubuntu/Debian:** `sudo apt install openjdk-17-jdk`
- **macOS:** `brew install openjdk@17`
- **Windows:** Download from [Adoptium](https://adoptium.net/)

**Installing Graphviz:**

- **Ubuntu/Debian:** `sudo apt install graphviz`
- **macOS:** `brew install graphviz`
- **Windows:** Download from [graphviz.org](https://graphviz.org/download/)

Verify your installation:

```bash
java -version    # Should show 11 or higher
dot -V           # Should show graphviz version
```

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
from buildzr.__about__ import VERSION
print(f"buildzr version: {VERSION}")
```

## Next Steps

Now that you have `buildzr` installed, head over to the [Quick Start Guide](quick-start.md) to create your first architecture diagram!
