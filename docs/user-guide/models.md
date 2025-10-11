# Models

Models are the fundamental building blocks of your architecture documentation in `buildzr`. They represent the different elements that make up your software system, from high-level abstractions like people and systems down to specific implementation details like components and deployment infrastructure. `buildzr` provides full support for all core C4 model element types, enabling you to create comprehensive architecture diagrams at multiple levels of detail.

## Understanding Model Categories

Your architecture models can be divided into two distinct categories: _static models_ and _instance models_.

**Static models** define the logical architecture of your system—the abstract concepts, relationships, and structure of your software independent of any specific deployment. These include people who interact with the system, the software systems themselves, and their internal structure broken down into containers and components. Static models answer questions like "What systems exist?" and "How are they organized?"

**Instance models** describe the physical deployment and runtime manifestation of your static models. They represent where and how your software actually runs in the real world—deployment environments, infrastructure nodes, and specific instances of containers deployed to those nodes. Instance models answer questions like "Where does this run?" and "What infrastructure supports it?"

This separation allows you to define your architecture once as static models, then map those same containers and systems to different deployment scenarios (development, staging, production) without duplicating the core architectural definitions.

Static models:

- `Person`
- `SoftwareSystem`
- `Container`
- `Component`

Instance models:

- `DeploymentEnvironment`
- `DeploymentNode`
- `SoftwareSystemInstance`
- `ContainerInstance`
- `InfrastructureNode`

To walk you through the models, let's use Structurizr's [Amazon Web Services](https://structurizr.com/dsl?example=amazon-web-services
) example.

## Person

`Person` represents human users, actors, roles, or personas.

```python
user = Person("User", description="An ordinary user.")
```

## Software System

`SoftwareSystem` represents the highest level of abstraction. A software system may contain zero or more containers.

```python
with SoftwareSystem('X') as x:
    # Its containers goes here.
    ...
```

## Container

`Container` represents an application, data store, or service within a software system. A container may contain zero or more components.

Here, we define the containers inside the software system `x` we've defined above.

```python
with SoftwareSystem("X") as x:

    wa = Container("Web Application", technology="Java and Spring boot")

    db = Container("Database Schema")

    wa >> "Reads from and writes to" >> db
```

Notice that we've also described a relationship between the web application `wa` and the database `db` of the software system `x`.

## Component

Represents a component within a container.

The `wa` web application may further be comprised of several layers, each serving different purpose. For example, in an Onion Architecture, your web application might have an API layer that listens for HTTP requests, which may in turn run queries or transactions via the database layer.

```python hl_lines="9-13"
with SoftwareSystem("X") as x:

    wa = Container("Web Application", technology="Java and Spring boot")

    db = Container("Database Schema")

    wa >> "Reads from and writes to" >> db

    with wa:
        api_layer = Component("API Layer")
        db_layer = Component("Database Layer")

        api_layer >> "Runs queries/transactions on" >> db_layer
```

## Properties and Metadata

You can add properties to enrich your models with metadata.

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

Models can also be assigned tags.

```python
critical_system = SoftwareSystem(
    'Payment System',
    tags=['critical', 'pci-compliant', 'monitored']
)
```

In Structurizr, the purpose of tags are used primarily for styling and visual representation of elements. For example, if an element is tagged as `critical`, you can apply a specific style (e.g., red colored background) to all elements tagged as `critical`.

`buildzr` offer a more flexible styling syntax beyond tagging. See [Styling](./styling.md).

!!! note
    If you run the code above, you will see that the `critical_system` has an extra additional "hidden" tags: `Element` and `SoftwareSystem`. By default, each model element will have default tags assigned to them: the model type (`Relationship` or `Element`) and, if it's an `Element`, the type of the element (e.g., `SoftwareSystem`, `Person`, `Container`, or `Component`).

## Deployment Elements

Now that we've defined the static models, let's detail out our architecture further by modeling how they're meant to be run or hosted.

### Deployment Environment

`DeploymentEnvironment` defines a deployment context (e.g., Development, Staging, Production). Each environment can have its own set of deployment nodes and infrastructure.

```python
with DeploymentEnvironment('Production') as prod:
    # Define deployment nodes
    pass
```

### Deployment Node

`DeploymentNode` represents infrastructure or runtime environment where your containers are deployed. Deployment nodes can be nested to represent hierarchical infrastructure (e.g., cloud provider → region → cluster → instance).

```python
with SoftwareSystem('Web Application') as system:
    api = Container(
        'API',
        description='Provides REST API',
        technology='Python/FastAPI'
    )

with DeploymentEnvironment('Production') as prod:
    with DeploymentNode('AWS'):
        with DeploymentNode('EC2', technology='Ubuntu 22.04'):
            # Deploy containers
            api_instance = ContainerInstance(api)
```

### Infrastructure Node

`InfrastructureNode` represents supporting infrastructure components that don't host containers but are essential to your system (load balancers, message queues, caches, etc.).

```python
with DeploymentNode('AWS'):
    load_balancer = InfrastructureNode(
        'Load Balancer',
        description='Distributes traffic',
        technology='AWS ELB'
    )
```

### Deployment Group

`DeploymentGroup` allows you to logically group container instances to control relationships between them in deployment scenarios.

**When to use:** Use deployment groups when you have multiple instances of the same containers and want to control which instances can communicate with each other.

```python
with SoftwareSystem('Web Application') as system:
    api = Container(
        'API',
        description='Provides REST API',
        technology='Python/FastAPI'
    )
    database = Container(
        'Database',
        description='Stores and runs transactions of app data',
        technology='MSSQL'
    )

with DeploymentEnvironment('Production') as prod:
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


## Complete Example

!!! note
    We've added a `SystemLandscapeView` in the code below, so that the generated JSON output can be used in a rendering tool (e.g., on [https://structurizr.com/json](https://structurizr.com/json)). See [Views](views.md) for more info.

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
    SystemContextView,
    DeploymentView,
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
    customer >>  "Uses" >> ecommerce
    admin >>  "Manages" >> ecommerce

    customer >> "Uses" >> web
    admin >> "Manages" >> web
    web >> "Calls" >> api_gateway
    api_gateway >> "Routes to" >> inv_svc
    order_svc >> "Stores in" >> db
    order_svc >> "Processes payment via" >> payment

    # Deployment (Production environment)
    with DeploymentEnvironment('Production') as prod:
        with DeploymentNode('AWS', technology='Cloud Provider'):
            # Load Balancer
            with DeploymentNode('Application Load Balancer', technology='AWS ALB'):
                lb = InfrastructureNode('Load Balancer')

            with DeploymentNode('EC2 Instance', technology='AWS EC2'):
                order_instance = ContainerInstance(order_svc)

            with DeploymentNode('API Gateway', technology='Amazon API Gateway'):
                api_gw_instance = ContainerInstance(api_gateway)

            # Application tier (containerized)
            with DeploymentNode('ECS Cluster', technology='AWS ECS'):
                web_instance = ContainerInstance(web)
                inventory_instance = ContainerInstance(inv_svc)

            # Database tier
            with DeploymentNode('DocumentDB', technology='MongoDB-compatible'):
                db_instance = ContainerInstance(db)

            api_gw_instance >> "Routes to" >> lb
            lb >> "Forwards requests to" >> order_instance

        SystemContextView(
            software_system_selector=ecommerce,
            key='system-context-view-ecommerce',
            description="System Context of E-Commerce App",
        )

w.apply_view(
    DeploymentView(
        environment=prod,
        key='deployment-view-production-ecommerce',
    )
)

w.to_json('workspace.json')
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
