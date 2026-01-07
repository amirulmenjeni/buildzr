# CLAUDE.md

This file provides guidance for AI assistants working with the buildzr codebase.

## Project Overview

buildzr is a Structurizr authoring tool for Python programmers. It enables declarative and procedural creation of C4 model architecture diagrams using Pythonic syntax with context managers.

**Key concepts:**
- Structurizr: Open standard (JSON schema) for software architecture diagrams
- C4 model: Modeling language with Person, SoftwareSystem, Container, Component hierarchy
- DSL: Domain-specific language using Python `with` statements for natural hierarchy

## Quick Commands

```bash
# Run tests with type checking
pytest --mypy tests

# Run tests without Java-dependent tests (CI mode)
pytest --mypy --ignore tests/test_workspaces.py

# Build package
python -m build

# Setup dev environment
conda env create -f environment.yml
conda activate buildzr-dev
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

    # Export
    w.to_json('workspace.json')
    w.to_plantuml('output_dir')
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
- `test_workspaces.py` requires Java/Structurizr CLI (skip in CI with `--ignore`)
- Use `jsondiff` for comparing JSON outputs in tests

## PlantUML Export

Requires optional dependency: `pip install buildzr[export-plantuml]`

Uses JPype to call Structurizr's Java libraries. Export with:
```python
w.to_plantuml('output_directory')
```
