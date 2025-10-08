# Container View Example

This example demonstrates creating a Container view to show the internal structure of a system.

## Scenario

Building on the System Context example, we now show the internal containers of the Corporate Web App:

- Database container
- API container
- Their relationships

## Complete Code

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    ContainerView,
    Group,
    desc,
)

with Workspace('webapp-containers') as w:
    # Define elements
    with Group("My Company"):
        user = Person('Web Application User')
        webapp = SoftwareSystem('Corporate Web App')

        # Define containers within the system
        with webapp:
            database = Container(
                'Database',
                description='Stores application data',
                technology='PostgreSQL'
            )
            api = Container(
                'API',
                description='Provides REST API',
                technology='Python/FastAPI'
            )
            web = Container(
                'Web Application',
                description='User interface',
                technology='React'
            )

    with Group("Microsoft"):
        email_system = SoftwareSystem('Microsoft 365')

    # Relationships
    user >> "Uses" >> web
    web >> ("Calls", "REST/HTTPS") >> api
    api >> ("Reads and writes data from/to", "SQL") >> database
    api >> ("Sends emails via", "SMTP") >> email_system

    # Create container view
    ContainerView(
        software_system_selector=webapp,
        key='web_app_containers',
        description="Corporate Web App - Container View",
        auto_layout='tb'
    )

    w.to_json('webapp_containers.json')
```

## Code Breakdown

### 1. Define Containers

```python
with webapp:
    database = Container(
        'Database',
        description='Stores application data',
        technology='PostgreSQL'
    )
    api = Container(
        'API',
        description='Provides REST API',
        technology='Python/FastAPI'
    )
```

Containers are defined within the context of their parent software system using the `with` statement.

### 2. Container Relationships

```python
web >> ("Calls", "REST/HTTPS") >> api
api >> ("Reads and writes data from/to", "SQL") >> database
```

Show how containers communicate with each other and external systems.

### 3. Create Container View

```python
ContainerView(
    software_system_selector=webapp,
    key='web_app_containers',
    description="Corporate Web App - Container View",
    auto_layout='tb'
)
```

The container view shows all containers within the selected software system.

## Extended Example: Microservices

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    ContainerView,
    Group,
)

with Workspace('microservices') as w:
    customer = Person('Customer')

    ecommerce = SoftwareSystem('E-Commerce Platform')

    with ecommerce:
        # Frontend
        web = Container('Web App', technology='React')
        mobile = Container('Mobile App', technology='React Native')

        # API Gateway
        api_gateway = Container('API Gateway', technology='Kong')

        # Microservices
        order_service = Container('Order Service', technology='Node.js')
        inventory_service = Container('Inventory Service', technology='Python')
        payment_service = Container('Payment Service', technology='Java')

        # Data stores
        order_db = Container('Order Database', technology='PostgreSQL')
        inventory_db = Container('Inventory Database', technology='MongoDB')
        cache = Container('Cache', technology='Redis')

        # Message queue
        message_queue = Container('Message Queue', technology='RabbitMQ')

    # External systems
    payment_gateway = SoftwareSystem('Payment Gateway', tags=['external'])

    # Relationships
    customer >> [desc("Uses") >> web, desc("Uses") >> mobile]

    web >> ("Calls", "REST/HTTPS") >> api_gateway
    mobile >> ("Calls", "REST/HTTPS") >> api_gateway

    api_gateway >> "Routes to" >> order_service
    api_gateway >> "Routes to" >> inventory_service
    api_gateway >> "Routes to" >> payment_service

    order_service >> ("Stores", "SQL") >> order_db
    inventory_service >> ("Stores", "NoSQL") >> inventory_db

    order_service >> ("Caches", "Redis") >> cache
    inventory_service >> ("Caches", "Redis") >> cache

    order_service >> ("Publishes events", "AMQP") >> message_queue
    inventory_service >> ("Subscribes", "AMQP") >> message_queue
    payment_service >> ("Subscribes", "AMQP") >> message_queue

    payment_service >> ("Processes", "REST") >> payment_gateway

    # Container view
    ContainerView(
        software_system_selector=ecommerce,
        key='microservices',
        description='E-Commerce Microservices Architecture',
        auto_layout='tb'
    )

    w.to_json('microservices.json')
```

## Variations

### Show Only Specific Containers

```python
ContainerView(
    software_system_selector=webapp,
    key='backend_only',
    description='Backend Containers Only',
    include_elements=[api, database, cache]
)
```

### Multiple Container Views

```python
# Full view
ContainerView(
    software_system_selector=ecommerce,
    key='full_view',
    description='All Containers',
    auto_layout='tb'
)

# Frontend focus
ContainerView(
    software_system_selector=ecommerce,
    key='frontend_view',
    description='Frontend Architecture',
    include_elements=[web, mobile, api_gateway],
    auto_layout='lr'
)

# Backend services focus
ContainerView(
    software_system_selector=ecommerce,
    key='backend_view',
    description='Backend Services',
    exclude_elements=[web, mobile],
    auto_layout='tb'
)
```

### With Styling

```python
from buildzr.dsl import Configuration, Styles, ElementStyle

with Configuration():
    with Styles():
        ElementStyle(tag='database', shape='Cylinder', background='#438dd5')
        ElementStyle(tag='web', shape='WebBrowser')
        ElementStyle(tag='mobile', shape='MobileDevicePortrait')

# Tag containers appropriately
database = Container('Database', tags=['database'])
web = Container('Web', tags=['web'])
mobile = Container('Mobile App', tags=['mobile'])
```

## Best Practices

1. **Use descriptive container names** that reflect their purpose
2. **Specify technology** to clarify implementation choices
3. **Show data flow** with relationship descriptions
4. **Group related containers** logically
5. **Create focused views** for different audiences

## Next Steps

- [Component View](../user-guide/views.md#component-view) - Drill into a container
- [Deployment Example](deployment.md) - Map to infrastructure
- [Styling Guide](../user-guide/styling.md) - Customize appearance
