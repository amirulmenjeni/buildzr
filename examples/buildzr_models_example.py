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
    SoftwareSystemInstance,
    InfrastructureNode,
    SystemContextView,
    DeploymentView,
)

with Workspace('microservices-example', implied_relationships=True) as w:
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

    DeploymentView(
        environment=prod,
        key='deployment-view-production-ecommerce',
    )

    w.to_json('buildzr_models_example.json', pretty=True)