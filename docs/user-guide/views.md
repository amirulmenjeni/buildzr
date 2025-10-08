# Views

Views are visual representations of your architecture model. Different views tell different stories about your system.

## View Types

`buildzr` supports all major C4 model view types:

- **System Landscape View** - All systems and people
- **System Context View** - A system and its environment
- **Container View** - Containers within a system
- **Component View** - Components within a container
- **Deployment View** - Infrastructure and deployment

## System Landscape View

Shows all software systems and people in your organization.

```python
from buildzr.dsl import SystemLandscapeView

SystemLandscapeView(
    key='landscape',
    description='Enterprise System Landscape',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, SystemLandscapeView, Group

with Workspace('w') as w:
    with Group("Users"):
        customer = Person('Customer')

    with Group("Internal"):
        web = SoftwareSystem('Web App')
        api = SoftwareSystem('API')

    with Group("External"):
        payment = SoftwareSystem('Payment Gateway')

    customer >> "Uses" >> web
    web >> "Calls" >> api
    api >> "Processes payments via" >> payment

    SystemLandscapeView(
        key='landscape',
        description='System Landscape',
        auto_layout='lr'
    )

    w.to_json('landscape.json')
```

## System Context View

Shows a software system and its immediate environment.

```python
from buildzr.dsl import SystemContextView

SystemContextView(
    software_system_selector=my_system,
    key='context',
    description='System Context for My System',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import Workspace, Person, SoftwareSystem, SystemContextView

with Workspace('w') as w:
    user = Person('User')
    system = SoftwareSystem('My System')
    email = SoftwareSystem('Email System', tags=['external'])
    database = SoftwareSystem('Legacy Database', tags=['external'])

    user >> "Uses" >> system
    system >> "Sends emails via" >> email
    system >> "Reads data from" >> database

    SystemContextView(
        software_system_selector=system,
        key='system-context',
        description='My System Context',
        auto_layout='tb'
    )

    w.to_json('context.json')
```

## Container View

Shows the containers within a software system.

```python
from buildzr.dsl import ContainerView

ContainerView(
    software_system_selector=my_system,
    key='containers',
    description='Container View',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    ContainerView,
)

with Workspace('w') as w:
    user = Person('User')
    system = SoftwareSystem('Web Application')

    with system:
        web = Container('Web App', technology='React')
        api = Container('API', technology='FastAPI')
        db = Container('Database', technology='PostgreSQL')

    user >> "Uses" >> web
    web >> ("Calls", "REST/HTTPS") >> api
    api >> ("Reads/Writes", "SQL") >> db

    ContainerView(
        software_system_selector=system,
        key='containers',
        description='Web Application Containers',
        auto_layout='tb'
    )

    w.to_json('containers.json')
```

## Component View

Shows components within a container.

```python
from buildzr.dsl import ComponentView

ComponentView(
    container_selector=my_container,
    key='components',
    description='Component View',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    Component,
    ComponentView,
)

with Workspace('w') as w:
    system = SoftwareSystem('System')

    with system:
        api = Container('API')

        with api:
            controller = Component('REST Controller')
            service = Component('Business Service')
            repository = Component('Data Repository')

        database = Container('Database')

    controller >> "Uses" >> service
    service >> "Uses" >> repository
    repository >> ("Queries", "SQL") >> database

    ComponentView(
        container_selector=api,
        key='api-components',
        description='API Components',
        auto_layout='tb'
    )

    w.to_json('components.json')
```

## Deployment View

Shows how containers map to infrastructure.

```python
from buildzr.dsl import DeploymentView

DeploymentView(
    software_system_selector=my_system,
    environment='Production',
    key='deployment',
    description='Production Deployment',
    auto_layout='tb'
)
```

### Example

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    ContainerInstance,
    DeploymentView,
)

with Workspace('w') as w:
    system = SoftwareSystem('Web App')

    with system:
        api = Container('API', technology='Python')
        db = Container('Database', technology='PostgreSQL')

    with DeploymentEnvironment('Production'):
        with DeploymentNode('AWS', technology='Cloud'):
            with DeploymentNode('ECS Cluster', technology='Docker'):
                api_instance = ContainerInstance(api)

            with DeploymentNode('RDS', technology='Managed Service'):
                db_instance = ContainerInstance(db)

    DeploymentView(
        software_system_selector=system,
        environment='Production',
        key='prod-deployment',
        description='Production Deployment',
        auto_layout='tb'
    )

    w.to_json('deployment.json')
```

## Auto Layout

Control how elements are arranged:

- `'tb'` - Top to bottom (default)
- `'bt'` - Bottom to top
- `'lr'` - Left to right
- `'rl'` - Right to left

```python
SystemContextView(
    software_system_selector=system,
    key='context-horizontal',
    auto_layout='lr'  # Left to right
)
```

## Including/Excluding Elements

### Exclude Specific Elements

```python
SystemContextView(
    software_system_selector=system,
    key='context',
    exclude_elements=[internal_admin, test_system]
)
```

### Include Specific Elements

```python
ContainerView(
    software_system_selector=system,
    key='containers',
    include_elements=[critical_container]
)
```

## View Best Practices

### Create Multiple Views

Different audiences need different perspectives:

```python
# High-level for executives
SystemLandscapeView(key='landscape')

# Mid-level for architects
SystemContextView(software_system_selector=system, key='context')

# Detailed for developers
ContainerView(software_system_selector=system, key='containers')
ComponentView(container_selector=api, key='components')
```

### Use Descriptive Keys and Descriptions

```python
# Good
SystemContextView(
    software_system_selector=payment_system,
    key='payment-system-context',
    description='Payment System and External Dependencies'
)

# Less helpful
SystemContextView(
    software_system_selector=payment_system,
    key='view1',
    description='System View'
)
```

### Choose Appropriate Layouts

```python
# Hierarchical flow - use top-to-bottom
ContainerView(
    software_system_selector=system,
    key='containers',
    auto_layout='tb'
)

# Process flow - use left-to-right
SystemContextView(
    software_system_selector=system,
    key='context',
    auto_layout='lr'
)
```

## Complete Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    Group,
    SystemLandscapeView,
    SystemContextView,
    ContainerView,
    ComponentView,
)

with Workspace('multi-view-example') as w:
    # Model
    with Group("Users"):
        customer = Person('Customer')

    with Group("E-Commerce"):
        ecommerce = SoftwareSystem('E-Commerce Platform')

        with ecommerce:
            web = Container('Web App', technology='React')
            api = Container('API', technology='Node.js')

            with api:
                order_ctrl = Component('Order Controller')
                order_svc = Component('Order Service')
                order_repo = Component('Order Repository')

            db = Container('Database', technology='MongoDB')

    with Group("External"):
        payment = SoftwareSystem('Payment Gateway')

    # Relationships
    customer >> "Browses and purchases" >> web
    web >> ("Calls", "REST") >> api
    api >> ("Stores", "MongoDB") >> db
    order_ctrl >> "Uses" >> order_svc
    order_svc >> "Uses" >> order_repo
    order_repo >> "Queries" >> db
    api >> ("Processes payments", "REST") >> payment

    # Multiple views for different audiences
    SystemLandscapeView(
        key='landscape',
        description='All Systems'
    )

    SystemContextView(
        software_system_selector=ecommerce,
        key='ecommerce-context',
        description='E-Commerce System Context',
        auto_layout='tb'
    )

    ContainerView(
        software_system_selector=ecommerce,
        key='ecommerce-containers',
        description='E-Commerce Containers',
        auto_layout='tb'
    )

    ComponentView(
        container_selector=api,
        key='api-components',
        description='API Components',
        auto_layout='lr'
    )

    w.to_json('multi-view.json')
```

## Next Steps

- [Styling](styling.md) - Customize view appearance
- [Examples](../examples/system-context.md) - See complete examples
- [API Reference](../api/dsl.md) - Detailed API documentation
