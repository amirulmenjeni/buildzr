# Deployment View Example

This example shows how to create deployment views to illustrate how containers map to infrastructure.

## Scenario

We'll show how a web application is deployed to AWS infrastructure:

- Application running in ECS containers
- Database in RDS
- Load balancer distributing traffic

## Complete Code

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    ContainerInstance,
    InfrastructureNode,
    DeploymentView,
)

with Workspace('deployment-example') as w:
    # Define the software system and containers
    webapp = SoftwareSystem('Web Application')

    with webapp:
        api = Container('API', technology='Python/FastAPI')
        database = Container('Database', technology='PostgreSQL')

    # Define production deployment
    with DeploymentEnvironment('Production'):
        with DeploymentNode('AWS', technology='Cloud Provider'):
            # Load Balancer
            with DeploymentNode('Application Load Balancer', technology='AWS ALB'):
                lb = InfrastructureNode(
                    'ALB',
                    description='Distributes traffic',
                    technology='AWS ELB'
                )

            # Application tier
            with DeploymentNode('ECS Cluster', technology='AWS ECS'):
                with DeploymentNode('ECS Service', technology='Fargate'):
                    api_instance_1 = ContainerInstance(api)
                    api_instance_2 = ContainerInstance(api)

            # Database tier
            with DeploymentNode('RDS', technology='AWS RDS'):
                db_instance = ContainerInstance(database)

    # Deployment relationships
    lb >> "Forwards to" >> api_instance_1
    lb >> "Forwards to" >> api_instance_2
    api_instance_1 >> ("Connects to", "SQL/TLS") >> db_instance
    api_instance_2 >> ("Connects to", "SQL/TLS") >> db_instance

    # Create deployment view
    DeploymentView(
        software_system_selector=webapp,
        environment='Production',
        key='production_deployment',
        description='Production Deployment on AWS',
        auto_layout='tb'
    )

    w.to_json('deployment.json')
```

## Code Breakdown

### 1. Define Deployment Environment

```python
with DeploymentEnvironment('Production'):
    # Deployment nodes go here
```

Common environments: `Production`, `Staging`, `Development`, `Test`

### 2. Define Deployment Nodes

```python
with DeploymentNode('AWS', technology='Cloud Provider'):
    with DeploymentNode('ECS Cluster', technology='AWS ECS'):
        # Nested deployment nodes
```

Deployment nodes represent infrastructure - cloud platforms, servers, containers, etc.

### 3. Deploy Container Instances

```python
api_instance_1 = ContainerInstance(api)
api_instance_2 = ContainerInstance(api)
```

Container instances represent deployed copies of your containers.

### 4. Add Infrastructure Nodes

```python
lb = InfrastructureNode(
    'ALB',
    description='Distributes traffic',
    technology='AWS ELB'
)
```

Infrastructure nodes represent supporting components like load balancers, message queues, etc.

## Multi-Environment Example

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

with Workspace('multi-env') as w:
    system = SoftwareSystem('System')

    with system:
        api = Container('API', technology='Node.js')
        db = Container('Database', technology='PostgreSQL')

    # Development Environment
    with DeploymentEnvironment('Development'):
        with DeploymentNode('Developer Laptop', technology='macOS'):
            with DeploymentNode('Docker', technology='Docker Desktop'):
                dev_api = ContainerInstance(api)
                dev_db = ContainerInstance(db)

    # Staging Environment
    with DeploymentEnvironment('Staging'):
        with DeploymentNode('AWS'):
            with DeploymentNode('EC2', technology='t3.medium'):
                staging_api = ContainerInstance(api)
            with DeploymentNode('RDS', technology='db.t3.small'):
                staging_db = ContainerInstance(db)

    # Production Environment
    with DeploymentEnvironment('Production'):
        with DeploymentNode('AWS'):
            with DeploymentNode('ECS Cluster'):
                prod_api_1 = ContainerInstance(api)
                prod_api_2 = ContainerInstance(api)
            with DeploymentNode('RDS Multi-AZ', technology='db.m5.xlarge'):
                prod_db = ContainerInstance(db)

    # Create views for each environment
    DeploymentView(
        software_system_selector=system,
        environment='Development',
        key='dev_deployment',
        description='Development Environment'
    )

    DeploymentView(
        software_system_selector=system,
        environment='Staging',
        key='staging_deployment',
        description='Staging Environment'
    )

    DeploymentView(
        software_system_selector=system,
        environment='Production',
        key='prod_deployment',
        description='Production Environment'
    )

    w.to_json('multi_env.json')
```

## Kubernetes Deployment

```python
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    ContainerInstance,
    InfrastructureNode,
    DeploymentView,
)

with Workspace('k8s-deployment') as w:
    system = SoftwareSystem('Microservices App')

    with system:
        frontend = Container('Frontend', technology='React')
        backend = Container('Backend', technology='Go')
        cache = Container('Cache', technology='Redis')

    with DeploymentEnvironment('Production'):
        with DeploymentNode('Kubernetes Cluster', technology='GKE'):
            # Ingress
            with DeploymentNode('Ingress', technology='nginx-ingress'):
                ingress = InfrastructureNode('Ingress Controller')

            # Frontend deployment
            with DeploymentNode('Frontend Deployment'):
                with DeploymentNode('Frontend Pod 1', technology='Pod'):
                    frontend_1 = ContainerInstance(frontend)
                with DeploymentNode('Frontend Pod 2', technology='Pod'):
                    frontend_2 = ContainerInstance(frontend)

            # Backend deployment
            with DeploymentNode('Backend Deployment'):
                with DeploymentNode('Backend Pod 1', technology='Pod'):
                    backend_1 = ContainerInstance(backend)
                with DeploymentNode('Backend Pod 2', technology='Pod'):
                    backend_2 = ContainerInstance(backend)

            # Redis StatefulSet
            with DeploymentNode('Redis StatefulSet'):
                with DeploymentNode('Redis Pod', technology='Pod'):
                    cache_instance = ContainerInstance(cache)

    # Relationships
    ingress >> "Routes to" >> frontend_1
    ingress >> "Routes to" >> frontend_2
    frontend_1 >> "Calls" >> backend_1
    frontend_2 >> "Calls" >> backend_2
    backend_1 >> "Uses" >> cache_instance
    backend_2 >> "Uses" >> cache_instance

    DeploymentView(
        software_system_selector=system,
        environment='Production',
        key='k8s_deployment',
        description='Kubernetes Production Deployment',
        auto_layout='tb'
    )

    w.to_json('k8s_deployment.json')
```

## Best Practices

### 1. Use Realistic Instance Counts

```python
# Production: Multiple instances
prod_api_1 = ContainerInstance(api)
prod_api_2 = ContainerInstance(api)
prod_api_3 = ContainerInstance(api)

# Dev: Single instance
dev_api = ContainerInstance(api)
```

### 2. Add Infrastructure Details

Add properties to deployment nodes to document infrastructure specifications:

```python
with DeploymentNode(
    'RDS Instance',
    technology='PostgreSQL',
    properties={
        'Multi-AZ': 'Enabled',
        'Instance Type': 'db.r5.xlarge',
        'Storage': '500GB SSD',
        'Backup Retention': '30 days'
    }
):
    db_instance = ContainerInstance(database)
```

### 3. Show Load Balancing

```python
lb >> "Distributes to" >> instance_1
lb >> "Distributes to" >> instance_2
lb >> "Distributes to" >> instance_3
```

### 4. Separate Environments

Create separate `DeploymentEnvironment` blocks for each environment and separate views.

## Next Steps

- [System Context Example](system-context.md) - High-level views
- [Container View Example](container-view.md) - Logical architecture
- [Styling Guide](../user-guide/styling.md) - Customize appearance
