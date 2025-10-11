# Core Concepts

Understanding these core concepts will help you get the most out of `buildzr`.

## The C4 Model

`buildzr` is built around the [C4 model](https://c4model.com/), which provides a hierarchical approach to software architecture diagrams:

1. **Context**: The highest level of abstraction in the C4 model, showing how a software system fits into the world around it (users and neighboring systems).
2. **Containers**: Zooms into a system to show the major technical building blocks (apps, databases, etc.) and how they communicate.
3. **Components**: Zooms into a container to show the major structural building blocks (modules, packages, classes) and their interactions.
4. **Code**: Zooms into a component to show the actual implementation details (classes, interfaces, etc.) -- often just UML class diagrams.

## Workspace

A **Workspace** is the top-level container for everything in your architecture model. It contains:

- **Model**: All your architecture elements and relationships
- **Views**: Visual representations of your model
- **Configuration**: Styling and other settings

```python
# norun
from buildzr.dsl import Workspace

with Workspace('my-workspace') as w:
    # Everything goes here
    pass
```

## Elements

Elements are the building blocks of your architecture model.

There are four elements you can create in a `Workspace`:

- **Person**: A user or an actor -- including robots -- that interacts with one or more software systems (and anything it contains).
- **Software System**: The highest level of abstraction, or a complete system that delivers value to its users (people or other systems).
- **Container**: A separately runnable/deployable units within a software system (e.g., web app, database, mobile app, microservice).
- **Component**: A grouping of related functionality within a container, typically represented as a module, package, or class grouping in code.

### Person

Represents a user or actor in your system:

```python
# norun
user = Person('User', description='A user of the system')
admin = Person('Administrator', description='System administrator')
```

### Software System

Represents a software system (the highest level of abstraction):

```python
# norun
system = SoftwareSystem(
    'Web Application',
    description='Our main web application'
)
```

### Container

Represents an application or data store within a software system:

```python
# norun
with system:
    api = Container('API', description='REST API', technology='Python/FastAPI')
    database = Container('Database', description='Main database', technology='PostgreSQL')
    frontend = Container('Frontend', description='Web UI', technology='React')
```

### Component

Represents a component within a container:

```python
# norun
with api:
    auth = Component('Auth Service', description='Handles authentication')
    user_service = Component('User Service', description='Manages users')
```

## Relationships

Relationships connect elements and show how they interact:

```python
# norun
# Simple relationship
user >> "Uses" >> system

# Relationship with technology
api >> ("Reads from", "SQL") >> database

# Multiple relationships
from buildzr.dsl import desc
user >> [
    desc("Uses") >> frontend,
    desc("Authenticates with", "http") >> api,
]
```

## Groups

Groups help organize related elements:

```python
# norun
with Group("Internal Systems"):
    system_a = SoftwareSystem('System A')
    system_b = SoftwareSystem('System B')

with Group("External Systems"):
    external = SoftwareSystem('External API')
```

!!! note
    Groups can be nested too!

    See: [Groups](./workspace.md#groups)

## Views

Views are visual representations of your model:

- **System Landscape View**: All systems and users
- **System Context View**: A system and its immediate environment
- **Container View**: Containers within a system
- **Component View**: Components within a container
- **Deployment View**: How containers map to infrastructure

```python
SystemContextView(
    software_system_selector=system,
    key='context',
    description='System Context',
    auto_layout='tb'
)
```

Views usually require an element input so that it knows which model in the architecture to focus on. In the example above, we pass the `system` element to the `SystemContextView`.

## Context Managers

`buildzr` uses Python context managers (`with` statements) to create hierarchical structures:

```python
with Workspace('w') as w:
    with Group("My Company"):
        system = SoftwareSystem('System')
        with system:
            container = Container('API')
            with container:
                component = Component('Service')
```

## Tags

Tags allow you to categorize and style elements:

```python
system = SoftwareSystem('System', tags=['critical', 'web'])
```

## Next Steps

- [Workspace](workspace.md) - Deep dive into workspaces
- [Models](models.md)
- [Relationships](relationships.md):
- [Views](views.md)
