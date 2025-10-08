# Deployment Groups Example

This example demonstrates how to use deployment groups to control relationships between container instances in multi-instance deployments.

## Scenario

We have a system with:
- An API service
- A database

We want to deploy two complete instances:
- Service Instance 1 on Server 1
- Service Instance 2 on Server 2

**Goal:** Ensure each API instance only connects to its corresponding database instance, preventing cross-server communication.

## Complete Code

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    DeploymentGroup,
    ContainerInstance,
    DeploymentView,
)

with Workspace('deployment-groups-example') as w:
    # Define software system and containers
    with SoftwareSystem('Web Application') as system:
        api = Container('API', technology='Python/FastAPI')
        database = Container('Database', technology='PostgreSQL')

        # Define relationship
        api >> "Reads/Writes" >> database

    # Production deployment with multiple instances
    with DeploymentEnvironment('Production') as production:
        # Create deployment groups
        instance_1 = DeploymentGroup('Service Instance 1')
        instance_2 = DeploymentGroup('Service Instance 2')

        # Server 1: First complete instance
        with DeploymentNode('Server 1'):
            api_1 = ContainerInstance(api, [instance_1])
            with DeploymentNode('Database Server'):
                db_1 = ContainerInstance(database, [instance_1])

        # Server 2: Second complete instance
        with DeploymentNode('Server 2'):
            api_2 = ContainerInstance(api, [instance_2])
            with DeploymentNode('Database Server'):
                db_2 = ContainerInstance(database, [instance_2])

    # Create deployment view
    DeploymentView(
        software_system_selector=system,
        environment=production,
        key='production-deployment',
        description='Production Deployment with Isolated Instances',
        auto_layout='tb'
    )

    w.to_json('deployment_groups.json')
```

## Code Breakdown

### 1. Define the System

```python
with SoftwareSystem('Web Application') as system:
    api = Container('API', technology='Python/FastAPI')
    database = Container('Database', technology='PostgreSQL')
    api >> "Reads/Writes" >> database
```

Define the logical architecture with containers and their relationships.

### 2. Create Deployment Groups

```python
instance_1 = DeploymentGroup('Service Instance 1')
instance_2 = DeploymentGroup('Service Instance 2')
```

Create deployment groups to logically separate instances.

### 3. Deploy Instances to Servers

```python
# Server 1
with DeploymentNode('Server 1'):
    api_1 = ContainerInstance(api, [instance_1])
    with DeploymentNode('Database Server'):
        db_1 = ContainerInstance(database, [instance_1])
```

Deploy containers and assign them to deployment groups. All instances with the same deployment group will maintain their relationships.

### 4. Relationship Isolation

**What happens:**

- ✅ `api_1` (in instance_1) connects to `db_1` (in instance_1)
- ✅ `api_2` (in instance_2) connects to `db_2` (in instance_2)
- ❌ `api_1` does NOT connect to `db_2`
- ❌ `api_2` does NOT connect to `db_1`

## Without Deployment Groups

If you don't use deployment groups, all instances share the "Default" group:

```python
with DeploymentNode('Server 1'):
    api_1 = ContainerInstance(api)  # Default group
    db_1 = ContainerInstance(database)  # Default group

with DeploymentNode('Server 2'):
    api_2 = ContainerInstance(api)  # Default group
    db_2 = ContainerInstance(database)  # Default group
```

**Result:** All APIs can connect to all databases (cross-server communication).

## Real-World Use Cases

### 1. Multi-Tenant Deployments

Deploy separate instances for each tenant with isolated data:

```python
tenant_a = DeploymentGroup('Tenant A')
tenant_b = DeploymentGroup('Tenant B')

with DeploymentNode('Tenant A Infrastructure'):
    app_a = ContainerInstance(app, [tenant_a])
    db_a = ContainerInstance(database, [tenant_a])

with DeploymentNode('Tenant B Infrastructure'):
    app_b = ContainerInstance(app, [tenant_b])
    db_b = ContainerInstance(database, [tenant_b])
```

### 2. Blue-Green Deployments

Maintain separate blue and green environments:

```python
blue = DeploymentGroup('Blue')
green = DeploymentGroup('Green')

with DeploymentNode('Blue Environment'):
    api_blue = ContainerInstance(api, [blue])
    cache_blue = ContainerInstance(cache, [blue])

with DeploymentNode('Green Environment'):
    api_green = ContainerInstance(api, [green])
    cache_green = ContainerInstance(cache, [green])
```

### 3. Geographic Regions

Deploy to multiple regions with local data:

```python
us_east = DeploymentGroup('US East')
eu_west = DeploymentGroup('EU West')

with DeploymentNode('AWS US-East-1'):
    api_us = ContainerInstance(api, [us_east])
    db_us = ContainerInstance(database, [us_east])

with DeploymentNode('AWS EU-West-1'):
    api_eu = ContainerInstance(api, [eu_west])
    db_eu = ContainerInstance(database, [eu_west])
```

### 4. Active-Active High Availability

Multiple active instances serving different traffic:

```python
shard_1 = DeploymentGroup('Shard 1')
shard_2 = DeploymentGroup('Shard 2')

with DeploymentNode('Data Center 1'):
    service_1 = ContainerInstance(service, [shard_1])
    db_1 = ContainerInstance(database, [shard_1])

with DeploymentNode('Data Center 2'):
    service_2 = ContainerInstance(service, [shard_2])
    db_2 = ContainerInstance(database, [shard_2])
```

## Best Practices

### 1. Use Descriptive Names

```python
# Good
primary = DeploymentGroup('Primary Instance')
secondary = DeploymentGroup('Secondary Instance')

# Less clear
group1 = DeploymentGroup('Group 1')
group2 = DeploymentGroup('Group 2')
```

### 2. Group All Related Instances

Ensure all containers that need to communicate are in the same group:

```python
production_instance = DeploymentGroup('Production Instance')

api_instance = ContainerInstance(api, [production_instance])
cache_instance = ContainerInstance(cache, [production_instance])
db_instance = ContainerInstance(database, [production_instance])
```

### 3. Document the Purpose

Use clear descriptions in your code:

```python
# Separate instances for different customer tiers
enterprise = DeploymentGroup('Enterprise Customers')
standard = DeploymentGroup('Standard Customers')
```

## Next Steps

- [Deployment Example](deployment.md) - Basic deployment views
- [Models Guide](../user-guide/models.md) - All model types
- [Structurizr Deployment Groups](https://docs.structurizr.com/dsl/cookbook/deployment-groups/) - Official documentation
