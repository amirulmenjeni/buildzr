# Structurizr for the `buildzr`s 🧱⚒️

`buildzr` is a [Structurizr](https://structurizr.com/) authoring tool for Python programmers. It allows you to declaratively or procedurally author Structurizr models and diagrams.

If you're not familiar with Structurizr, it is both an open standard (see [Structurizr JSON schema](https://github.com/structurizr/json)) and a [set of tools](https://docs.structurizr.com/usage) for building software architecture diagrams as code. Structurizr derive its architecture modeling paradigm based on the [C4 model](https://c4model.com/), the modeling language for describing software architectures and the relationships.

In Structurizr, you define architecture models and their relationships first. And then, you can re-use the models to present multiple perspectives, views, and stories about your architecture.

# Quick Start 🚀

## Installation

You can use `pip` to install the `buildzr` package:

```bash
pip install buildzr
```

## Creating a workspace

The module `buildzr.dsl` contains all the classes you need to create a workspace containing all the architecture models.

Below is an example, where we:
1. Create the models (`Person`, `SoftwareSystem`s, the `Container`s inside the `SoftwareSystem`, and the relationships -- `>>` -- between them)
2. Define multiple views using the models we've created before.

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
        exclude_elements=[
            u,
        ]
    )

    ContainerView(
        software_system_selector=webapp,
        key='web_app_container_view_00',
        auto_layout='lr',
        description="Web App Container View",
    )

    w.to_json('workspace.json')
```

Here's a short breakdown on what's happening:
- In the `with Workspace('w') as w:` block, we've created a `Workspace` named `w`.
- Inside this block, we're in the context of the `w` workspace, so any models, relationships, and views we declared in this block will belong to that workspace. We've declared a few models: `Person`, the `SoftwareSystems`, their `Container`s, and their relationships with each other. Oh, we've separated them into different `Group`s, too!
- Showing the who's and the what's in an architecture model is good, but an architecture model is incomplete without the arrows that describes the relationships between the systems. In `buildzr`, we can define relationships with the `>>` operator.
- Once we have all the models and their relationships defined, we use (and re-use!) the static models to create multiple views to tell different stories and show various narrative to help document your software architecture. In this case, we've created one `SystemContextView` and one `ContainerView` for the `webapp`.
- Finally, we write the workspace definitions into a JSON file, which can be consumed by rendering tools, or used for further processing.

The JSON output can be found [here](examples/system_context_and_container_view.json). You can also try out https://structurizr.com/json to see how this workspace will be rendered.

# Why use `buildzr`?

✅ Uses `buildzr`'s declarative DSL syntax to help you create C4 model architecture diagrams in Python concisely.

✅ Uses `buildzr`'s DSL APIs to programmatically create C4 model architecture diagrams. Good if you need to automate things!

✅ Write Structurizr diagrams more securely with extensive type hints and [mypy](https://mypy-lang.org) support.

✅ Stays true to the [Structurizr JSON schema](https://mypy-lang.org/) standards. `buildzr` uses the [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) to automatically generate the "low-level" [representation](buildzr/models/models.py) of the Workspace model. This reduces deprecancy between `buildzr` and the Structurizr JSON schema.

✅ Writing architecture models and diagrams in Python allows you to integrate programmability and automation into your software architecture diagramming and documentation workflow. For example, you might want to programmatically automate the creation of architecture models from metadata pulled from your IT asset management system, but still want to declaratively define how to present them.

✅ Uses the familiar Python programming language and its rich toolchains to write software architecture models and diagrams!

# Contributing

Interested in contributing to `buildzr`?

Please visit [CONTRIBUTING.md](CONTRIBUTING.md).