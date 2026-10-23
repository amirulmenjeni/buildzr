"""The workspace behind ``buildzr serve --example``: a small online shop, drawn at every level the viewer shows.

Not shipped: ``scripts/build_serve_example.py`` builds it and writes the built data into ``buildzr/site/example/``.
Only supported model and view features are used (no custom elements, no CustomView).
"""

from buildzr.dsl import (
    Component,
    ComponentView,
    Container,
    ContainerInstance,
    ContainerView,
    DeploymentEnvironment,
    DeploymentNode,
    DeploymentView,
    DynamicView,
    Group,
    InfrastructureNode,
    Person,
    SoftwareSystem,
    StyleElements,
    StyleRelationships,
    SystemContextView,
    SystemLandscapeView,
    Workspace,
)

with Workspace("example", description="An online shop, from the system landscape down to its deployment.",
               implied_relationships=True) as w:
    customer = Person("Customer", description="Browses the catalogue and buys things.")
    support = Person("Support Agent", description="Helps customers and refunds orders.")

    with Group("Shop"):
        with SoftwareSystem("Online Shop", description="Sells goods to customers over the web.") as shop:
            web = Container("Web App", description="The storefront in the browser.", technology="TypeScript, React",
                            tags={"Browser"})
            gateway = Container("API Gateway", description="One entry point for the apps.", technology="Kong")
            with Container("Order Service", description="Takes, pays and ships orders.",
                           technology="Python, FastAPI") as orders:
                order_api = Component("Order API", description="REST endpoints for orders.", technology="FastAPI")
                checkout = Component("Checkout", description="Prices the basket and starts the payment.",
                                     technology="Python")
                order_repo = Component("Order Repository", description="Reads and writes orders.",
                                       technology="SQLAlchemy")
                payment_client = Component("Payment Client", description="Calls the payment provider.",
                                           technology="httpx")
            catalogue = Container("Catalogue Service", description="Products, prices and stock.",
                                  technology="Go")
            queue = Container("Event Bus", description="Carries order events.", technology="RabbitMQ",
                              tags={"Queue"})
            orders_db = Container("Orders DB", description="Orders and payments.", technology="PostgreSQL",
                                  tags={"Database"})
            catalogue_db = Container("Catalogue DB", description="Products and stock levels.",
                                     technology="PostgreSQL", tags={"Database"})
        with SoftwareSystem("Back Office", description="Staff tools for support and refunds.") as back_office:
            admin_ui = Container("Admin UI", description="Orders and refunds for staff.", technology="React")

    with Group("External"):
        payments = SoftwareSystem("Payment Provider", description="Takes card payments.", tags={"External"})
        email = SoftwareSystem("Email Service", description="Sends receipts and notices.", tags={"External"})

    customer >> ("Browses and buys with", "HTTPS") >> web
    support >> ("Helps customers with", "HTTPS") >> admin_ui
    web >> ("Calls", "JSON/HTTPS") >> gateway
    admin_ui >> ("Calls", "JSON/HTTPS") >> gateway
    gateway >> ("Routes orders to", "JSON/HTTPS") >> order_api
    gateway >> ("Routes searches to", "gRPC") >> catalogue
    order_api >> "Starts" >> checkout
    checkout >> ("Reads prices from", "gRPC") >> catalogue
    checkout >> "Charges through" >> payment_client
    checkout >> "Saves orders with" >> order_repo
    payment_client >> ("Charges cards with", "HTTPS") >> payments
    order_repo >> ("Reads and writes", "SQL") >> orders_db
    orders >> ("Publishes order events to", "AMQP") >> queue
    queue >> ("Notifies", "AMQP") >> email
    catalogue >> ("Reads and writes", "SQL") >> catalogue_db

    with DeploymentEnvironment("Production") as production:
        with DeploymentNode("Customer device", technology="Web browser"):
            web_instance = ContainerInstance(web)
        with DeploymentNode("Cloud", technology="Amazon Web Services"):
            with DeploymentNode("Edge", technology="Amazon CloudFront"):
                balancer = InfrastructureNode("Load Balancer", technology="AWS ALB")
            with DeploymentNode("Kubernetes cluster", technology="Amazon EKS"):
                with DeploymentNode("Gateway pods", technology="Kubernetes"):
                    gateway_instance = ContainerInstance(gateway)
                with DeploymentNode("Service pods", technology="Kubernetes"):
                    orders_instance = ContainerInstance(orders)
                    catalogue_instance = ContainerInstance(catalogue)
                with DeploymentNode("Broker pods", technology="Kubernetes"):
                    queue_instance = ContainerInstance(queue)
            with DeploymentNode("Database service", technology="Amazon RDS"):
                orders_db_instance = ContainerInstance(orders_db)
                catalogue_db_instance = ContainerInstance(catalogue_db)
        web_instance >> ("Sends requests to", "HTTPS") >> balancer
        balancer >> ("Forwards to", "HTTP") >> gateway_instance

    StyleElements(on=[Person], shape="Person", background="#08427b", color="#ffffff")
    StyleElements(on=["External"], background="#8a8a8a", color="#ffffff")
    StyleElements(on=["Database"], shape="Cylinder", background="#2f7f6f", color="#ffffff")
    StyleElements(on=["Queue"], shape="Pipe", background="#b4651a", color="#ffffff")
    StyleElements(on=["Browser"], shape="WebBrowser")
    StyleRelationships(on=["Relationship"], color="#555555", thickness=2)

    SystemLandscapeView(key="landscape", description="Who and what is around the shop.", title="System landscape")
    SystemContextView(shop, key="shop-context", description="The shop, its users and neighbours.",
                      title="Online Shop - system context")
    ContainerView(shop, key="shop-containers", description="What runs inside the shop.",
                  title="Online Shop - containers")
    ComponentView(orders, key="orders-components", description="Inside the order service.",
                  title="Order Service - components")
    DynamicView(scope=shop, key="place-order", title="Place an order", description="What happens at checkout.",
                steps=[
                    customer >> "Submits the basket in" >> web,
                    web >> "Sends the order to" >> gateway,
                    gateway >> "Routes the order to" >> order_api,
                    checkout >> "Charges through" >> payment_client,
                    payment_client >> "Charges the card with" >> payments,
                    checkout >> "Saves the order with" >> order_repo,
                ])
    DeploymentView(production, key="production", description="Where the shop runs.",
                   title="Online Shop - production")
