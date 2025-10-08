# Structurizr for the `buildzr`s 🧱⚒️

`buildzr` is a [Structurizr](https://structurizr.com/) authoring tool for Python programmers. It allows you to declaratively or procedurally author Structurizr models and diagrams.

If you're not familiar with Structurizr, it is both an open standard (see [Structurizr JSON schema](https://github.com/structurizr/json)) and a [set of tools](https://docs.structurizr.com/usage) for building software architecture diagrams as code. Structurizr derives its architecture modeling paradigm based on the [C4 model](https://c4model.com/), the modeling language for describing software architectures and their relationships.

In Structurizr, you define architecture models and their relationships first. And then, you can re-use the models to present multiple perspectives, views, and stories about your architecture.

## Why use `buildzr`?

✅ **Declarative DSL Syntax** - Use `buildzr`'s declarative DSL syntax to help you create C4 model architecture diagrams in Python concisely.

✅ **Programmatic Creation** - Use `buildzr`'s DSL APIs to programmatically create C4 model architecture diagrams. Great for automation!

✅ **Type Safety** - Write Structurizr diagrams more securely with extensive type hints and [mypy](https://mypy-lang.org) support.

✅ **Standards Compliant** - Stays true to the [Structurizr JSON schema](https://github.com/structurizr/json) standards. `buildzr` uses [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) to automatically generate the low-level representation of the Workspace model.

✅ **Python Integration** - Writing architecture models and diagrams in Python allows you to integrate programmability and automation into your software architecture diagramming and documentation workflow.

✅ **Rich Toolchain** - Uses the familiar Python programming language and its rich toolchains to write software architecture models and diagrams!

## Quick Example

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    SystemContextView,
    ContainerView,
    desc,
    Group,
)

with Workspace('w') as w:
    with Group("My Company"):
        u = Person('Web Application User')
        webapp = SoftwareSystem('Corporate Web App')
        with webapp:
            database = Container('database')
            api = Container('api')
            api >> ("Reads and writes data from/to", "http/api") >> database
    with Group("Microsoft"):
        email_system = SoftwareSystem('Microsoft 365')

    u >> [
        desc("Reads and writes email using") >> email_system,
        desc("Create work order using") >> webapp,
    ]
    webapp >> "sends notification using" >> email_system

    SystemContextView(
        software_system_selector=webapp,
        key='web_app_system_context_00',
        description="Web App System Context",
        auto_layout='lr',
        exclude_elements=[u]
    )

    ContainerView(
        software_system_selector=webapp,
        key='web_app_container_view_00',
        auto_layout='lr',
        description="Web App Container View",
    )

    w.to_json('workspace.json')
```

## Getting Started

Ready to dive in? Check out our [Installation Guide](getting-started/installation.md) and [Quick Start Tutorial](getting-started/quick-start.md).

## Project Links

- [GitHub Repository](https://github.com/amirulmenjeni/buildzr)
- [Issue Tracker](https://github.com/amirulmenjeni/buildzr/issues)
- [Roadmap](roadmap.md)
- [Contributing Guide](contributing.md)
