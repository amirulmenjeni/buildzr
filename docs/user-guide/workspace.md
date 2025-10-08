# Workspace

The `Workspace` is the top-level container for your entire architecture documentation. Think of it as your architecture's universe --- everything that exists in your system lives within a workspace. It holds your models (people, systems, containers, components), deployment environments, views, and styling rules. Without a workspace, you just have floating architectural concepts with nowhere to call home.

Every `buildzr` project starts by creating a workspace using a context manager:

```python
from buildzr.dsl import Workspace

with Workspace('My Architecture') as w:
    # Define your architecture here
    pass
```

## Configuration

When creating a workspace, you can configure several important behaviors:

### Name and Description

Every workspace needs a name. Descriptions are optional but recommended.

```python
with Workspace(
    'E-Commerce Platform',
    description='Architecture for our online shopping system'
) as w:
    pass
```

### Scope

The `scope` parameter determines what level of architecture your workspace focuses on:

- `'landscape'` - Multiple systems across your organization
- `'software_system'` (default) - A single software system in detail
- `None` - No specific scope

```python
# For documenting multiple systems
with Workspace('Enterprise Architecture', scope='landscape') as w:
    crm = SoftwareSystem('CRM')
    erp = SoftwareSystem('ERP')
    warehouse = SoftwareSystem('Warehouse Management')
```

```python
# For documenting a single system in depth
with Workspace('Payment Service', scope='software_system') as w:
    with SoftwareSystem('Payment Service') as payment:
        api = Container('API')
        database = Container('Database')
        worker = Container('Background Worker')
```

### Implied Relationships

When `implied_relationships=True`, `buildzr` automatically creates parent-level relationships based on child-level ones. If your frontend container talks to their API container, it implies your system talks to their system.

```python
with Workspace('w', implied_relationships=True) as w:
    with SoftwareSystem('System A') as a:
        frontend = Container('Frontend')

    with SoftwareSystem('System B') as b:
        api = Container('API')

    # This explicitly creates: frontend >> api
    # This implicitly creates: a >> b
    frontend >> "Calls" >> api
```

See [Implied Relationships](relationships.md#implied-relationships) for more details.

### Group Separator

When using nested groups, the `group_separator` determines how group names are joined. The default is `'/'`.

```python
with Workspace('w', group_separator='/') as w:
    with Group("Engineering"):
        with Group("Backend"):
            api = SoftwareSystem('API')
            # Full group name: "Engineering/Backend"
```

## Hierarchical Structure

`buildzr` uses Python's context managers (`with` statements) to create nested structures. This makes your code mirror your architecture's hierarchy.

```python
from buildzr.dsl import Workspace, SoftwareSystem, Container, Component

with Workspace('E-Commerce Platform') as w:

    # Software System level
    with SoftwareSystem('E-Commerce') as ecommerce:

        # Container level
        with Container('API') as api:

            # Component level
            auth = Component('Auth Service')
            payment = Component('Payment Service')
            catalog = Component('Catalog Service')

            auth >> "Validates requests for" >> payment
            auth >> "Validates requests for" >> catalog
```

The nesting naturally represents containment: components live in containers, containers live in systems, systems live in workspaces. No manual parent-child linking required.

## Groups

Groups organize related elements visually in your diagrams. They don't affect the logical architecture --- they're purely for presentation and communication.

```python
from buildzr.dsl import Workspace, SoftwareSystem, Person, Group

with Workspace('w') as w:

    with Group("Internal Systems"):
        crm = SoftwareSystem('CRM')
        erp = SoftwareSystem('ERP')
        inventory = SoftwareSystem('Inventory Management')

    with Group("External Systems"):
        payment_gateway = SoftwareSystem('Stripe')
        email_service = SoftwareSystem('SendGrid')

    with Group("Users"):
        employee = Person('Employee')
        customer = Person('Customer')
```

### Nested Groups

Groups can be nested to create hierarchical organization:

```python
with Workspace('w') as w:

    with Group("Company 1"):
        with Group("Department 1"):
            system_a = SoftwareSystem("System A")
            system_b = SoftwareSystem("System B")

        with Group("Department 2"):
            system_c = SoftwareSystem("System C")

    with Group("Company 2"):
        with Group("Department 1"):
            system_d = SoftwareSystem("System D")

        with Group("Department 2"):
            system_e = SoftwareSystem("System E")
```

The full group name for `system_a` would be `"Company 1/Department 1"` (using the default `/` separator).

## Accessing Elements

After defining elements in your workspace, you can access them as attributes using transformed names:

```python
with Workspace('w') as w:
    user = Person('Web Application User')
    payment_system = SoftwareSystem('Payment System')

    # Access via original variable
    user >> payment_system

    # Or access via workspace attributes (names are lowercased and spaces become underscores)
    w.web_application_user >> w.payment_system
```

You can also use dictionary-style access:

```python
# norun
w['web_application_user'] >> w['payment_system']
```

This is particularly useful when you need to reference elements defined in one part of your code from another part.

## Exporting

Once you've defined your architecture, export it to JSON for visualization in tools like [Structurizr](https://structurizr.com):

```python
# norun
with Workspace('My Architecture') as w:
    # ... define your architecture ...

    # Export to JSON
    w.to_json('workspace.json')

    # Export with pretty formatting
    w.to_json('workspace_pretty.json', pretty=True)
```

The JSON file can be uploaded to Structurizr's web interface or used with other C4 model visualization tools.

## Complete Example

Here's a complete example bringing together all workspace concepts:

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    SystemContextView,
    ContainerView,
    Group,
    desc,
)

with Workspace(
    'Online Banking System',
    description='Core banking platform architecture',
    scope='software_system',
    implied_relationships=True
) as w:

    # Define people
    with Group("Users"):
        customer = Person('Customer', description='Bank customer')
        support = Person('Support Staff', description='Customer support team')

    # Define our main system
    with SoftwareSystem('Online Banking') as banking:

        web_app = Container('Web Application', technology='React')
        mobile_app = Container('Mobile App', technology='React Native')

        with Container('API Gateway', technology='Node.js/Express') as api:
            auth = Component('Authentication')
            accounts = Component('Account Management')
            transactions = Component('Transaction Processing')

            auth >> "Protects" >> accounts
            auth >> "Protects" >> transactions

        database = Container('Database', technology='PostgreSQL')

        web_app >> "Makes API calls to" >> api
        mobile_app >> "Makes API calls to" >> api
        api >> "Reads from and writes to" >> database

    # External systems
    with Group("External"):
        email = SoftwareSystem('Email System', description='SendGrid')
        payment = SoftwareSystem('Payment Gateway', description='Stripe')

    # Relationships
    customer >> [
        desc("Uses") >> web_app,
        desc("Uses") >> mobile_app,
    ]
    support >> "Manages customers via" >> web_app
    api >> "Sends notifications via" >> email
    api >> "Processes payments via" >> payment

    # Create views
    SystemContextView(
        software_system_selector=banking,
        key='banking_context',
        description='System context for online banking',
        auto_layout='tb'
    )

    ContainerView(
        software_system_selector=banking,
        key='banking_containers',
        description='Container view of online banking',
        auto_layout='tb'
    )

    # Export (with pretty json formatting) 💅
    w.to_json('workspace.json', pretty=True)
```

## Next Steps

- [Models](models.md)
- [Relationships](relationships.md)
- [Views](views.md)
- [Styles](styles.md)