# Models API Reference

Low-level API reference for `buildzr.models` module.

This module contains the auto-generated Pydantic models that represent the Structurizr JSON schema. These are the underlying data structures used by the DSL classes.

::: buildzr.models

## Overview

The `buildzr.models` module contains Pydantic models generated from the [Structurizr JSON schema](https://github.com/structurizr/json) using [datamodel-code-generator](https://github.com/koxudaxi/datamodel-code-generator).

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
from buildzr.models import Workspace, Model, ViewSet

workspace = Workspace(
    name="My Workspace",
    model=Model(),
    views=ViewSet()
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

```python
workspace_dict = workspace.dict(exclude_none=True, by_alias=True)

with open('output.json', 'w') as f:
    json.dump(workspace_dict, f, indent=2)
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
from buildzr.models import (
    Workspace,
    Model,
    ViewSet,
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
                description="System user"
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
                        technology="Python/FastAPI"
                    ),
                    Container(
                        id="4",
                        name="Database",
                        technology="PostgreSQL"
                    )
                ]
            )
        ],
        relationships=[
            Relationship(
                sourceId="1",
                destinationId="2",
                description="Uses"
            ),
            Relationship(
                sourceId="3",
                destinationId="4",
                description="Reads from and writes to",
                technology="SQL"
            )
        ]
    ),
    views=ViewSet(
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

# Add deployment model
deployment_node_aws = DeploymentNode(
    id="5",
    name="AWS",
    technology="Cloud Provider",
    children=[
        DeploymentNode(
            id="6",
            name="ECS Cluster",
            technology="Container Service",
            containerInstances=[
                ContainerInstance(
                    id="7",
                    containerId="3",
                    instanceId=1
                )
            ]
        ),
        DeploymentNode(
            id="8",
            name="RDS",
            technology="Managed Database",
            containerInstances=[
                ContainerInstance(
                    id="9",
                    containerId="4",
                    instanceId=1
                )
            ]
        )
    ],
    infrastructureNodes=[
        InfrastructureNode(
            id="10",
            name="Load Balancer",
            technology="AWS ALB"
        )
    ]
)

# Add deployment environment to model
if not workspace.model.deploymentNodes:
    workspace.model.deploymentNodes = []
workspace.model.deploymentNodes.append(deployment_node_aws)

# Export to JSON
workspace_dict = workspace.dict(exclude_none=True, by_alias=True)
with open('complete_workspace.json', 'w') as f:
    json.dump(workspace_dict, f, indent=2)

print("Workspace created with deployment models!")
```

!!! tip "DSL vs Models"
    While you can use the low-level models directly as shown above, most users should prefer the higher-level DSL API from `buildzr.dsl`, which provides a more intuitive and Pythonic interface.

!!! note "Model IDs"
    When working directly with models, you need to manually manage element IDs and references. The DSL API handles this automatically.

## See Also

- [DSL API Reference](dsl.md) - High-level DSL API (recommended)
- [Structurizr JSON Schema](https://github.com/structurizr/json) - Official schema
- [User Guide](../user-guide/core-concepts.md) - Usage guide
