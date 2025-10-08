# Workspace

The Workspace is the top-level container for your entire architecture model.

## Creating a Workspace

Use a context manager to create a workspace:

```python
from buildzr.dsl import Workspace

with Workspace('my-workspace') as w:
    # Define your model here
    pass
```

## Workspace Components

A workspace contains three main sections:

1. **Model** - Architecture elements and relationships
2. **Views** - Visual representations
3. **Configuration** - Styling and settings

## Basic Usage

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem

with Workspace('my-workspace') as w:
    user = Person('User')
    system = SoftwareSystem('System')
    user >> "Uses" >> system
```

## Exporting

### Export to JSON

```python
with Workspace('my-workspace') as w:
    # ... define your model ...
    w.to_json('workspace.json')
```

### Export to a File Object

```python
with Workspace('my-workspace') as w:
    # ... define your model ...
    with open('workspace.json', 'w') as f:
        w.to_json(f)
```

## Workspace Scope

Everything defined within the workspace context belongs to that workspace:

```python
with Workspace('w1') as w1:
    system1 = SoftwareSystem('System 1')
    # system1 belongs to w1

with Workspace('w2') as w2:
    system2 = SoftwareSystem('System 2')
    # system2 belongs to w2
```

## Best Practices

### Use Descriptive Names

```python
with Workspace('ecommerce-platform') as w:
    # Clear what this workspace represents
    pass
```

### Organize with Groups

```python
with Workspace('enterprise-architecture') as w:
    with Group("Core Systems"):
        crm = SoftwareSystem('CRM')
        erp = SoftwareSystem('ERP')

    with Group("External Systems"):
        payment = SoftwareSystem('Payment Gateway')
```

### Create Multiple Views

```python
with Workspace('my-system') as w:
    system = SoftwareSystem('System')

    # Overview
    SystemLandscapeView(key='landscape')

    # Detailed view
    SystemContextView(
        software_system_selector=system,
        key='context'
    )
```

## Complete Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Group,
    SystemContextView,
    ContainerView,
)

with Workspace('online-banking') as w:
    # Define model
    with Group("Banking"):
        customer = Person('Customer', description='Bank customer')
        system = SoftwareSystem('Online Banking', description='Banking system')

        with system:
            web = Container('Web Application', technology='React')
            api = Container('API', technology='Spring Boot')
            db = Container('Database', technology='PostgreSQL')

    with Group("External"):
        email = SoftwareSystem('Email System')

    # Define relationships
    customer >> "Uses" >> web
    web >> "Calls" >> api
    api >> "Reads/Writes" >> db
    api >> "Sends email via" >> email

    # Create views
    SystemContextView(
        software_system_selector=system,
        key='context',
        description='System Context',
        auto_layout='tb'
    )

    ContainerView(
        software_system_selector=system,
        key='containers',
        description='Container View',
        auto_layout='tb'
    )

    # Export
    w.to_json('banking.json')
```

## Next Steps

- [Models](models.md) - Learn about different model types
- [Views](views.md) - Create different types of views
- [Styling](styling.md) - Customize appearance
