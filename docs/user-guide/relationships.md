# Relationships

Relationships connect elements in your architecture model and describe how they interact.

## Basic Syntax

Use the `>>` operator to create relationships:

```python
from buildzr.dsl import Person, SoftwareSystem

user = Person('User')
system = SoftwareSystem('System')

# Simple relationship
user >> system
```

## Adding Descriptions

Add a description to explain the relationship:

```python
user >> "Uses" >> system
```

## Technology/Protocol

Specify the technology or protocol used:

```python
from buildzr.dsl import Container

api = Container('API')
database = Container('Database')

# Relationship with description and technology
api >> ("Reads from and writes to", "JDBC/SSL") >> database
```

## Multiple Relationships

Define multiple relationships from one element:

```python
user >> [
    desc("Reads from") >> system_a,
    desc("Writes to") >> system_b,
    desc("Authenticates with") >> auth_system,
]
```

!!! note
    Use `desc` when describing relationships in a one-to-many relationships definition.


## Bidirectional Relationships

Create relationships in both directions:

```python
# System A calls System B
system_a >> "Calls" >> system_b

# System B sends events to System A
system_b >> "Sends events to" >> system_a
```

## Relationship Properties

Add custom properties to relationships:

```python
# Note: Direct property setting requires accessing the relationship object
# This is typically done through the underlying API
```

## Implied Relationships

`buildzr` automatically creates implied relationships. For example:

```python
# If Container A calls Container B
container_a >> "Calls" >> container_b

# An implied relationship exists between their parent systems
# (assuming they're in different systems)
```

## Relationship Examples

### Person to System

```python
customer >> "Places orders using" >> ecommerce_system
admin >> "Manages" >> admin_panel
```

### System to System

```python
web_app >> "Gets data from" >> api_system
api_system >> ("Queries", "REST/HTTPS") >> database_system
payment_system >> "Sends notifications via" >> email_system
```

### Container to Container

```python
with system:
    web >> "Makes API calls to" >> api
    api >> ("Reads from", "SQL") >> database
    api >> ("Caches in", "Redis protocol") >> cache
```

### Component to Component

```python
with api_container:
    controller >> "Uses" >> service
    service >> "Calls" >> repository
    repository >> "Queries" >> database_component
```

### Deployment Relationships

```python
from buildzr.dsl import DeploymentNode, ContainerInstance

with DeploymentEnvironment('Production'):
    with DeploymentNode('Load Balancer') as lb:
        lb_instance = InfrastructureNode('LB')

    with DeploymentNode('App Server') as app:
        api_instance = ContainerInstance(api)

    lb_instance >> "Forwards requests to" >> api_instance
```

## Complex Example

```python
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Group,
    desc,
)

with Workspace('relationships-example') as w:
    # Define elements
    with Group("Users"):
        customer = Person('Customer')
        admin = Person('Admin')

    with Group("Internal Systems"):
        webapp = SoftwareSystem('Web Application')
        with webapp:
            frontend = Container('Frontend', technology='React')
            backend = Container('Backend API', technology='FastAPI')
            db = Container('Database', technology='PostgreSQL')
            cache = Container('Cache', technology='Redis')

    with Group("External Systems"):
        payment = SoftwareSystem('Payment Gateway')
        email = SoftwareSystem('Email Service')
        analytics = SoftwareSystem('Analytics Platform')

    # User relationships
    customer >> [
        desc("Browses products using") >> frontend,
        desc("Makes purchases via") >> frontend,
    ]

    admin >> [
        desc("Manages system via") >> frontend,
        desc("Views reports in") >> frontend,
    ]

    # Frontend relationships
    frontend >> [
        desc("Calls", "REST/HTTPS") >> backend,
        desc("Sends events to") >> analytics,
    ]

    # Backend relationships
    backend >> [
        desc("Reads/Writes", "SQL") >> db,
        desc("Caches data in", "Redis protocol") >> cache,
        desc("Processes payments via", "REST API") >> payment,
        desc("Sends emails via", "SMTP") >> email,
        desc("Tracks events in") >> analytics,
    ]

    # External system relationships
    payment >> ("Sends webhooks to", "HTTPS") >> backend
    email >> ("Logs delivery status to", "API") >> backend

    w.to_json('relationships.json')
```

## Best Practices

### Be Descriptive

```python
# Good
api >> "Authenticates users via OAuth2" >> auth_service

# Less clear
api >> "Uses" >> auth_service
```

### Specify Technology

```python
# Good
api >> ("Queries", "SQL/TLS") >> database

# Missing context
api >> "Queries" >> database
```

### Group Related Relationships

```python
# Group relationships by source
frontend >> [
    desc("Calls") >> api,
    desc("Sends analytics to") >> analytics,
    desc("Stores session in") >> cache,
]
```

### Use Consistent Terminology

```python
# Consistent
service_a >> "Calls" >> service_b
service_b >> "Calls" >> service_c

# Inconsistent (confusing)
service_a >> "Invokes" >> service_b
service_b >> "Calls" >> service_c
```

## Next Steps

- [Views](views.md) - Visualize your relationships
- [Styling](styling.md) - Style your relationship lines
- [Examples](../examples/system-context.md) - See complete examples
