# AGENTS.md

## Development environment

Use the repository devcontainer for all development and testing. Do not run the
project's test suite, type checks, documentation builds, or package builds on
the host machine. This keeps Python, Java, uv, and the Structurizr tooling
consistent with CI.

Start or rebuild the devcontainer with the Dev Container CLI or VS Code, then
run commands from `/workspace/buildzr` inside the container. For example:

```bash
devcontainer up --workspace-folder .
devcontainer exec --workspace-folder . uv sync --all-extras --locked
devcontainer exec --workspace-folder . uv run pytest --mypy tests
```

Use the devcontainer's installed Structurizr CLI when running workspace
validation tests. When testing a specific supported Python interpreter, pass
that interpreter to uv inside the container, for example:

```bash
devcontainer exec --workspace-folder . uv run --python 3.13 pytest --mypy tests
```

Host-side inspection, editing, and Git operations are fine, but validation must
be performed inside the devcontainer.

## Project Overview

buildzr is a Structurizr authoring tool for Python programmers. It enables declarative and procedural creation of C4 model architecture diagrams using Pythonic syntax with context managers.

**Key concepts:**
- Structurizr: Open standard (JSON schema) for software architecture diagrams
- C4 model: Modeling language for software architecture diagrams
- DSL: Domain-specific language using Python `with` statements for natural hierarchy

## Quick Commands

Run these commands inside the devcontainer:

```bash
# Run tests with type checking
uv run pytest --mypy tests

# Run tests without Java-dependent tests (CI mode)
uv run pytest --mypy --ignore tests/test_workspaces.py

# Build package
uv build

# Setup dev environment
uv sync --all-extras
```

## Project Structure

```
buildzr/              # Main source module
├── dsl/              # Core DSL (Workspace, SoftwareSystem, Container, etc.)
│   ├── dsl.py        # Main DSL classes
│   ├── relations.py  # Relationship operators (>>)
│   └── factory/      # ID generation
├── models/           # Auto-generated dataclasses from Structurizr schema
├── sinks/            # Output writers (JSON, PlantUML)
├── exporters/        # Format converters
├── encoders/         # JSON serialization (camelCase via pyhumps)
├── loaders/          # Workspace deserialization
└── jars/             # Bundled JARs for PlantUML export

tests/                # Test suite
├── samples/          # Sample workspaces for manual verification
└── test_*.py         # Unit and integration tests

examples/             # User-facing examples
docs/                 # MkDocs documentation site
```

## Code Conventions

- **Python version:** 3.10+
- **Type hints:** Strict mypy enforcement (`disallow_untyped_defs = True`)
- **Docstrings:** Google style
- **Commits:** Conventional commits (feat:, fix:, docs:, etc.)
- **Models:** Auto-generated from `buildzr/models/structurizr.yaml` using datamodel-code-generator

## DSL Patterns

The buildzr DSL uses context managers for natural hierarchy:

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, Person, Group

with Workspace('name') as w:
    with Group("Group Name"):
        person = Person('User')
        system = SoftwareSystem('System')
        with system:
            container = Container('Container')

    # Relationships use >> operator
    person >> "uses" >> system
    person >> ("uses", "HTTP") >> system  # with technology

    # Export to files
    w.save()                              # JSON to {workspace_name}.json
    w.save(path='workspace.json')         # JSON to specific path
    w.save(format='plantuml', path='out') # PlantUML to directory

    # Get as strings/dicts (for display, Jupyter, etc.)
    json_str = w.to_json()                # JSON string
    puml_dict = w.to_plantuml()           # Dict[view_key, puml_string]
```

## Key Entry Points

Main imports from `buildzr.dsl`:
- **Elements:** `Workspace`, `Person`, `SoftwareSystem`, `Container`, `Component`, `Group`
- **Deployment:** `DeploymentEnvironment`, `DeploymentNode`, `InfrastructureNode`
- **Views:** `SystemContextView`, `ContainerView`, `ComponentView`, `DeploymentView`, `DynamicView`
- **Styling:** `StyleElements`, `StyleRelationships`
- **Helpers:** `desc`, `With`, `Explorer`, `Expression`

## Testing

- Place test samples in `tests/samples/` as Python files
- Tests validate JSON output against Structurizr schema
- `test_workspaces.py` requires Java/Structurizr CLI; use the devcontainer for it
- Use `jsondiff` for comparing JSON outputs in tests

## PlantUML Export

Requires optional dependency: `pip install buildzr[export-plantuml]`

Uses JPype to call Structurizr's Java libraries. Export with:
```python
# Save to files
w.save(format='plantuml', path='output_directory')  # .puml files
w.save(format='svg', path='output_directory')       # .svg files
w.save(format='png', path='output_directory')       # .png files

# Get as strings (for Jupyter notebooks, etc.)
puml_dict = w.to_plantuml()  # Dict[view_key, puml_string]
svg_dict = w.to_svg()        # Dict[view_key, svg_string]
```
