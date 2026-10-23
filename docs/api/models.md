# Models API Reference

Low-level API reference for `buildzr.models` module.

This module contains the auto-generated dataclasses that represent the Structurizr JSON schema. These are the underlying data structures used by the DSL classes.

::: buildzr.models

## Overview

The `buildzr.models` module contains Python dataclasses generated from the Structurizr JSON schema (see [Structurizr](https://structurizr.com)) using [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator). The field names are the ones of the schema, in camelCase (`sourceId`, `containerInstances`).

## When to Use

Most users should use the higher-level DSL API ([buildzr.dsl](dsl.md)) rather than working directly with these models. However, these models are useful when:

1. **Direct JSON manipulation** - Converting between Python objects and JSON
2. **Custom extensions** - Building custom functionality on top of buildzr
3. **Integration** - Integrating with other Structurizr tools
4. **Validation** - Validating Structurizr JSON structures

## Key Model Classes

### Workspace Model

The root model representing a complete Structurizr workspace.

```python
from buildzr.models import Workspace, Model, Views

workspace = Workspace(
    name="My Workspace",
    model=Model(),
    views=Views()
)
```

### Model Elements

Core model element types:

- `Person` - Human users/actors
- `SoftwareSystem` - Software systems
- `Container` - Applications/data stores
- `Component` - Components within containers

### Deployment Model Elements

Deployment-related model types:

- `DeploymentNode` - Infrastructure nodes (servers, cloud instances, etc.)
- `InfrastructureNode` - Supporting infrastructure (load balancers, message queues, etc.)
- `ContainerInstance` - Deployed instance of a container
- `SoftwareSystemInstance` - Deployed instance of a software system

### Relationships

A relationship is stored in the `relationships` list of its source element (a `Person`, `SoftwareSystem`, `Container`, `Component` or deployment element), not in the `Model`. Its `sourceId` and `destinationId` are the ids of the two elements.

```python
from buildzr.models import Relationship

relationship = Relationship(
    sourceId="1",
    destinationId="2",
    description="Uses",
    technology="HTTPS"
)
```

### Views

View models for different diagram types:

- `SystemLandscapeView`
- `SystemContextView`
- `ContainerView`
- `ComponentView`
- `DeploymentView`

## Working with Models

### Exporting to JSON

The models are dataclasses, so they have no JSON method of their own. Use `buildzr.encoders.JsonEncoder`, the encoder that the DSL's `to_json()` and `buildzr export` use: it leaves out the fields that are `None`.

```python
import json
from buildzr.encoders import JsonEncoder
from buildzr.models import Workspace, Model

workspace = Workspace(name="My Workspace", model=Model())

with open('output.json', 'w') as f:
    json.dump(workspace, f, cls=JsonEncoder, indent=2)
```

## Type Hints

All models include full type hints for IDE support:

```python
from buildzr.models import Workspace, Model

def process_workspace(ws: Workspace) -> Model:
    return ws.model
```

## Schema Compliance

These models are auto-generated to stay in sync with the official Structurizr JSON schema, ensuring compatibility with all Structurizr tools.

## Complete Example with Deployment

Here's a more comprehensive example that includes deployment models:

```python
import json
from buildzr.encoders import JsonEncoder
from buildzr.models import (
    Workspace,
    Model,
    Views,
    Person,
    SoftwareSystem,
    Container,
    DeploymentNode,
    ContainerInstance,
    InfrastructureNode,
    Relationship,
    SystemContextView,
    DeploymentView,
)

# Create a workspace
workspace = Workspace(
    name="Complete Example",
    description="Example with deployment models",
    model=Model(
        people=[
            Person(
                id="1",
                name="User",
                description="System user",
                # A relationship belongs to its source element
                relationships=[
                    Relationship(
                        id="11",
                        sourceId="1",
                        destinationId="2",
                        description="Uses"
                    )
                ]
            )
        ],
        softwareSystems=[
            SoftwareSystem(
                id="2",
                name="Web Application",
                containers=[
                    Container(
                        id="3",
                        name="API",
                        technology="Python/FastAPI",
                        relationships=[
                            Relationship(
                                id="12",
                                sourceId="3",
                                destinationId="4",
                                description="Reads from and writes to",
                                technology="SQL"
                            )
                        ]
                    ),
                    Container(
                        id="4",
                        name="Database",
                        technology="PostgreSQL"
                    )
                ]
            )
        ]
    ),
    views=Views(
        systemContextViews=[
            SystemContextView(
                key="context",
                softwareSystemId="2",
                description="System Context"
            )
        ],
        deploymentViews=[
            DeploymentView(
                key="deployment",
                softwareSystemId="2",
                environment="Production",
                description="Production Deployment"
            )
        ]
    )
)

# Add the deployment model: every node and instance names its environment
deployment_node_aws = DeploymentNode(
    id="5",
    name="AWS",
    technology="Cloud Provider",
    environment="Production",
    children=[
        DeploymentNode(
            id="6",
            name="ECS Cluster",
            technology="Container Service",
            environment="Production",
            containerInstances=[
                ContainerInstance(
                    id="7",
                    containerId="3",
                    instanceId=1,
                    environment="Production"
                )
            ]
        ),
        DeploymentNode(
            id="8",
            name="RDS",
            technology="Managed Database",
            environment="Production",
            containerInstances=[
                ContainerInstance(
                    id="9",
                    containerId="4",
                    instanceId=1,
                    environment="Production"
                )
            ]
        )
    ],
    infrastructureNodes=[
        InfrastructureNode(
            id="10",
            name="Load Balancer",
            technology="AWS ALB",
            environment="Production"
        )
    ]
)

# Add the deployment nodes to the model
if not workspace.model.deploymentNodes:
    workspace.model.deploymentNodes = []
workspace.model.deploymentNodes.append(deployment_node_aws)

# Export to JSON
with open('complete_workspace.json', 'w') as f:
    json.dump(workspace, f, cls=JsonEncoder, indent=2)

print("Workspace created with deployment models!")
```

!!! tip "DSL vs Models"
    While you can use the low-level models directly as shown above, most users should prefer the higher-level DSL API from `buildzr.dsl`, which provides a more intuitive and Pythonic interface.

!!! note "Model IDs"
    When working directly with models, you need to manually manage element IDs and references. The DSL API handles this automatically.

## See Also

- [DSL API Reference](dsl.md) - High-level DSL API (recommended)
- [Structurizr](https://structurizr.com) - the project that defines the Structurizr JSON schema
- [User Guide](../user-guide/core-concepts.md) - Usage guide
