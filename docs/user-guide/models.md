# Models

Models are the elements that make up your architecture. `buildzr` supports all the core C4 model element types.

## Person

Represents human users, actors, roles, or personas.

```python
from buildzr.dsl import Person

user = Person('User')
admin = Person('Administrator', description='System admin with elevated privileges')
```

### Person with Tags

```python
external_user = Person('External User', tags=['external', 'customer'])
```

## Software System

Represents a software system - the highest level of abstraction.

```python
from buildzr.dsl import SoftwareSystem

system = SoftwareSystem('Web Application')
detailed_system = SoftwareSystem(
    'E-Commerce Platform',
    description='Handles online sales and inventory'
)
```

### External Systems

```python
external_api = SoftwareSystem(
    'Payment Gateway',
    description='Third-party payment processing',
    tags=['external']
)
```

## Container

Represents an application, data store, or service within a software system.

```python
from buildzr.dsl import Container

with system:
    web_app = Container(
        'Web Application',
        description='Delivers content to users',
        technology='React'
    )

    api = Container(
        'API',
        description='Provides REST API',
        technology='Python/FastAPI'
    )

    database = Container(
        'Database',
        description='Stores data',
        technology='PostgreSQL'
    )
```

## Component

Represents a component within a container.

```python
from buildzr.dsl import Component

with api:
    auth_service = Component(
        'Authentication Service',
        description='Handles user authentication',
        technology='JWT'
    )

    user_service = Component(
        'User Service',
        description='Manages user data'
    )

    order_service = Component(
        'Order Service',
        description='Processes orders'
    )
```

## Deployment Elements

### Deployment Environment

Defines a deployment context (e.g., Development, Production).

```python
from buildzr.dsl import DeploymentEnvironment

with DeploymentEnvironment('Production'):
    # Define deployment nodes
    pass
```

### Deployment Node

Represents infrastructure or runtime environment.

```python
from buildzr.dsl import DeploymentNode, ContainerInstance

with DeploymentEnvironment('Production'):
    with DeploymentNode('AWS'):
        with DeploymentNode('EC2', technology='Ubuntu 22.04'):
            # Deploy containers
            api_instance = ContainerInstance(api)
```

### Infrastructure Node

Represents supporting infrastructure components.

```python
from buildzr.dsl import InfrastructureNode

with DeploymentNode('AWS'):
    load_balancer = InfrastructureNode(
        'Load Balancer',
        description='Distributes traffic',
        technology='AWS ELB'
    )
```

### Deployment Group

Logically groups container instances to control relationships between them in deployment scenarios.

**When to use:** Use deployment groups when you have multiple instances of the same containers and want to control which instances can communicate with each other.

```python
from buildzr.dsl import DeploymentGroup, ContainerInstance

with DeploymentEnvironment('Production'):
    # Define deployment groups
    instance_group_1 = DeploymentGroup('Service Instance 1')
    instance_group_2 = DeploymentGroup('Service Instance 2')

    # Server 1: API and Database in group 1
    with DeploymentNode('Server 1'):
        api_1 = ContainerInstance(api, [instance_group_1])
        with DeploymentNode('Database Server'):
            db_1 = ContainerInstance(database, [instance_group_1])

    # Server 2: API and Database in group 2
    with DeploymentNode('Server 2'):
        api_2 = ContainerInstance(api, [instance_group_2])
        with DeploymentNode('Database Server'):
            db_2 = ContainerInstance(database, [instance_group_2])
```

!!! tip "Deployment Groups Use Case"
    Deployment groups ensure that:

    - The API on Server 1 only connects to the database on Server 1
    - The API on Server 2 only connects to the database on Server 2

    This prevents cross-server communication and keeps instances isolated within their groups.

!!! note "Default Deployment Group"
    If you don't specify deployment groups, all container instances are automatically assigned to a "Default" deployment group.

## Groups

Organize related elements into named groups.

```python
from buildzr.dsl import Group

with Group("Internal Systems"):
    crm = SoftwareSystem('CRM')
    erp = SoftwareSystem('ERP')

with Group("External Systems"):
    payment = SoftwareSystem('Payment Gateway')
    email = SoftwareSystem('Email Service')
```

## Properties and Metadata

Add custom properties to elements:

```python
system = SoftwareSystem(
    'System',
    properties={
        'Owner': 'Platform Team',
        'Cost Center': 'IT-001',
        'SLA': '99.9%'
    }
)
```

## Tags

Use tags to categorize and style elements:

```python
critical_system = SoftwareSystem(
    'Payment System',
    tags=['critical', 'pci-compliant', 'monitored']
)
```

## Hierarchical Structure

Use context managers to create nested structures:

```python
with Workspace('w') as w:
    # Software System level
    ecommerce = SoftwareSystem('E-Commerce')

    with ecommerce:
        # Container level
        api = Container('API')

        with api:
            # Component level
            auth = Component('Auth Service')
            payment = Component('Payment Service')
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
    DeploymentEnvironment,
    DeploymentNode,
    ContainerInstance,
    InfrastructureNode,
)

with Workspace('microservices-example') as w:
    # People
    customer = Person('Customer')
    admin = Person('Administrator')

    # Systems
    with Group("E-Commerce Platform"):
        ecommerce = SoftwareSystem('E-Commerce System')

        with ecommerce:
            # Containers
            web = Container('Web App', technology='React')
            api_gateway = Container('API Gateway', technology='Kong')

            # Services
            with Container('Order Service', technology='Node.js') as order_svc:
                order_controller = Component('Order Controller')
                order_repository = Component('Order Repository')

            with Container('Inventory Service', technology='Python') as inv_svc:
                inventory_api = Component('Inventory API')
                stock_manager = Component('Stock Manager')

            # Database
            db = Container('Database', technology='MongoDB')

    with Group("External"):
        payment = SoftwareSystem('Payment Provider')

    # Relationships
    customer >> "Uses" >> web
    admin >> "Manages" >> web
    web >> "Calls" >> api_gateway
    api_gateway >> "Routes to" >> order_svc
    api_gateway >> "Routes to" >> inv_svc
    order_svc >> "Stores in" >> db
    order_svc >> "Processes payment via" >> payment

    # Deployment (Production environment)
    with DeploymentEnvironment('Production'):
        with DeploymentNode('AWS', technology='Cloud Provider'):
            # Load Balancer
            with DeploymentNode('Application Load Balancer', technology='AWS ALB'):
                lb = InfrastructureNode('Load Balancer')

            # Application tier
            with DeploymentNode('ECS Cluster', technology='AWS ECS'):
                web_instance = ContainerInstance(web)
                api_gw_instance = ContainerInstance(api_gateway)
                order_instance = ContainerInstance(order_svc)
                inventory_instance = ContainerInstance(inv_svc)

            # Database tier
            with DeploymentNode('DocumentDB', technology='MongoDB-compatible'):
                db_instance = ContainerInstance(db)

    w.to_json('microservices.json')
```

!!! tip "Complete Architecture"
    This example demonstrates all major model types in buildzr:

    - **People**: Customer and Admin users
    - **Systems**: E-Commerce platform and external payment provider
    - **Containers**: Web app, API gateway, microservices, and database
    - **Components**: Internal service components
    - **Deployment**: AWS infrastructure with ECS and DocumentDB
    - **Groups**: Logical organization of systems

## Next Steps

- [Relationships](relationships.md) - Learn how to connect models
- [Views](views.md) - Visualize your models
- [Styling](styling.md) - Customize appearance
