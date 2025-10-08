# Core Concepts

Understanding these core concepts will help you get the most out of `buildzr`.

## The C4 Model

`buildzr` is built around the [C4 model](https://c4model.com/), which provides a hierarchical approach to software architecture diagrams:

1. **Context** - How your system fits in the world
2. **Containers** - High-level technology choices
3. **Components** - Components within a container
4. **Code** - Code-level details (optional)

## Workspace

A **Workspace** is the top-level container for everything in your architecture model. It contains:

- **Model** - All your architecture elements and relationships
- **Views** - Visual representations of your model
- **Configuration** - Styling and other settings

```python
from buildzr.dsl import Workspace

with Workspace('my-workspace') as w:
    # Everything goes here
    pass
```

## Elements

Elements are the building blocks of your architecture model:

### Person

Represents a human user or actor in your system:

```python
user = Person('User', description='A user of the system')
admin = Person('Administrator', description='System administrator')
```

### Software System

Represents a software system (the highest level of abstraction):

```python
system = SoftwareSystem(
    'Web Application',
    description='Our main web application'
)
```

### Container

Represents an application or data store within a software system:

```python
with system:
    api = Container('API', description='REST API', technology='Python/FastAPI')
    database = Container('Database', description='Main database', technology='PostgreSQL')
    frontend = Container('Frontend', description='Web UI', technology='React')
```

### Component

Represents a component within a container:

```python
with api:
    auth = Component('Auth Service', description='Handles authentication')
    user_service = Component('User Service', description='Manages users')
```

## Relationships

Relationships connect elements and show how they interact:

```python
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
with Group("Internal Systems"):
    system_a = SoftwareSystem('System A')
    system_b = SoftwareSystem('System B')

with Group("External Systems"):
    external = SoftwareSystem('External API')
```

## Views

Views are visual representations of your model:

- **System Landscape View** - All systems and users
- **System Context View** - A system and its immediate environment
- **Container View** - Containers within a system
- **Component View** - Components within a container
- **Deployment View** - How containers map to infrastructure

```python
SystemContextView(
    software_system_selector=system,
    key='context',
    description='System Context',
    auto_layout='tb'
)
```

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

## Auto Layout

Views can automatically arrange elements:

- `'tb'` - Top to bottom
- `'bt'` - Bottom to top
- `'lr'` - Left to right
- `'rl'` - Right to left

```python
SystemContextView(
    software_system_selector=system,
    key='context',
    auto_layout='lr'
)
```

## Export

Export your workspace to JSON for use with Structurizr tools:

```python
w.to_json('workspace.json')
```

## Next Steps

- [Workspace](workspace.md) - Deep dive into workspaces
- [Models](models.md) - Learn about all model types
- [Relationships](relationships.md) - Master relationships
- [Views](views.md) - Create powerful views
