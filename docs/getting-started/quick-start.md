# Quick Start

This guide will walk you through creating your first architecture diagram with `buildzr`.

## Your First Workspace

Let's create a simple system context diagram showing a web application and its users.

### Step 1: Import Required Classes

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    SystemContextView,
)
```

### Step 2: Create a Workspace

A workspace is the top-level container for your architecture model:

```python
with Workspace('my-workspace') as w:
    # Your model will go here
    pass
```

### Step 3: Define Your Models

Inside the workspace context, define the elements of your architecture:

```python
with Workspace('my-workspace') as w:
    # Define a person (user)
    user = Person('User', description='A user of the system')

    # Define a software system
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    # Define the relationship
    user >> "Uses" >> system
```

### Step 4: Create a View

Views allow you to visualize your models:

```python
with Workspace('my-workspace') as w:
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )
    user >> "Uses" >> system

    # Create a system context view
    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'  # top-to-bottom layout
    )
```

### Step 5: Export to JSON

Finally, export your workspace to a JSON file:

```python
with Workspace('my-workspace') as w:
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )
    user >> "Uses" >> system

    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'
    )

    # Export to JSON
    w.to_json('workspace.json')
```

## Complete Example

Here's the complete code:

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    SystemContextView,
)

with Workspace('my-workspace') as w:
    # Define models
    user = Person('User', description='A user of the system')
    system = SoftwareSystem(
        'Web Application',
        description='Our main web application'
    )

    # Define relationships
    user >> "Uses" >> system

    # Create view
    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='System Context View',
        auto_layout='tb'
    )

    # Export
    w.to_json('workspace.json')
```

## Viewing Your Diagram

The generated JSON file follows the [Structurizr JSON schema](https://github.com/structurizr/json). You can visualize it using:

1. **Online**: Upload to [https://structurizr.com/json](https://structurizr.com/json)
2. **Structurizr Lite**: Run a local instance
   ```bash
   docker run -it --rm -p 8080:8080 -v $PWD:/usr/local/structurizr structurizr/lite
   ```
3. **Structurizr CLI**: Convert to other formats (PlantUML, Mermaid, etc.)

## Next Steps

Now that you've created your first diagram, explore more advanced features:

- [Core Concepts](../user-guide/core-concepts.md) - Understand the fundamentals
- [Models](../user-guide/models.md) - Learn about different model types
- [Relationships](../user-guide/relationships.md) - Master relationship definitions
- [Views](../user-guide/views.md) - Create different types of views
- [Examples](../examples/system-context.md) - See more complete examples
