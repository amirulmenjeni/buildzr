# Structurizr for the `buildzr`s 🧱⚒️

`buildzr` is a [Structurizr](https://structurizr.com/) authoring tool for Python programmers.

If you're not familiar with Structurizr, it is both an open standard (see [Structurizr JSON schema](https://github.com/structurizr/json)) and a [set of tools](https://docs.structurizr.com/usage) for building software architecture diagrams as code. Structurizr derive its architecture modeling paradigm based on the [C4 model](https://c4model.com/), the modeling language for visualizing software architecture.

`buildzr` offers flexible and fluent APIs to write software architecture models,
leveraging the standard Structurizr JSON schema for interoperability with
various rendering and authoring tools.

# Quick Start 🚀

## Installation

You can use `pip` to install the `buildzr` package:

```bash
pip install buildzr
```

## Creating a workspace

The module `buildzr.dsl` contains all the classes you need to create a workspace containing all the architecture models.

Below is an example, where we:
1. Create the models (`Person`, `SoftwareSystem`s, the `Container`s inside the `SoftwareSystem`, and the relationships between them)
2. Define multiple views using the models we've created before.

```python
import os
import json

from buildzr.encoders import JsonEncoder

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

w = Workspace('w')\
    .contains(
        Group(
            "My Company",
            Person('Web Application User').labeled('u'),
            SoftwareSystem('Corporate Web App').labeled('webapp')
            .contains(
                Container('database'),
                Container('api'),
            )\
            .where(lambda s: [
                s.api >> "Reads and writes data from/to" >> s.database,
            ])
        ),
        Group(
            "Microsoft",
            SoftwareSystem('Microsoft 365').labeled('email_system'),
        )
    )\
    .where(lambda w: [
        w.person().u >> [
            desc("Reads and writes email using") >> w.software_system().email_system,
            desc("Create work order using") >> w.software_system().webapp,
        ],
        w.software_system().webapp >> "sends notification using" >> w.software_system().email_system,
    ])\
    .with_views(
        SystemContextView(
            lambda w: w.software_system().webapp,
            key='web_app_system_context_00',
            description="Web App System Context",
            auto_layout='lr',
            exclude_elements=[
                lambda w, e: w.person().user == e,
            ]
        ),
        ContainerView(
            lambda w: w.software_system().webapp,
            key='web_app_container_view_00',
            auto_layout='lr',
            description="Web App Container View",
        )
    )\
    .get_workspace()

# Save workspace to a JSON file following the Structurizr JSON schema.
w.to_json('workspace.json')
```

Here's a short breakdown on what's happening:
- In `Workspace(...).contains(...)` method, we define the _static_ C4 models (i.e., `Person`, `SoftwareSystem`, and the `Container`s in the software system).
- In the `Workspace(...).contains(...).where(...)`, we define the relationships between the C4 models in the workspace. We access the models via the `w` parameter in the `lambda` function, and create the relationships using the `>>` operators.
- Once we have all the models and their relationships defined, we use (and re-use!) the static models to create multiple views to tell different stories and show various narrative to help document your software architecture.
- Finally, we write the workspace definitions into a JSON file, which can be consumed by rendering tools, or used for further processing.

The JSON output can be found [here](examples/system_context_and_container_view.json). You can also try out https://structurizr.com/json to see how this workspace will be rendered.

# Why use `buildzr`?

✅ Uses fluent APIs to help you create C4 model architecture diagrams in Python concisely.

✅ Write Structurizr diagrams more securely with extensive type hints and [mypy](https://mypy-lang.org) support.

✅ Stays true to the [Structurizr JSON schema](https://mypy-lang.org/) standards. `buildzr` uses the [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator) to automatically generate the "low-level" [representation](buildzr/models/models.py) of the Workspace model. This reduces deprecancy between `buildzr` and the Structurizr JSON schema.

✅ Writing architecture diagrams in Python allows you to integrate programmability and automation into your software architecture diagramming and documentation workflow.

✅ Uses the familiar Python programming language to write software architecture diagrams!

# Contributing

Interested in contributing to `buildzr`?

Please visit [CONTRIBUTING.md](CONTRIBUTING.md).