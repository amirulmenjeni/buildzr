# Using the example from https://structurizr.com/dsl?example=amazon-web-services

from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    DeploymentEnvironment,
    DeploymentGroup,
    DeploymentNode,
    InfrastructureNode,
    ContainerInstance,
    SystemContextView,
    DeploymentView,
    StyleElements,
)

with Workspace(
    "Amazon Web Services Example",
    description="An example AWS deployment architecture",
) as w:

    user = Person("User", description="An ordinary user.")

    with SoftwareSystem("Online Shop") as shop:

        # Notice that we don't need to specify the tags "Application" and "Database"
        # for styling -- just pass the `wa` and `db` variables directly to the `StyleElements` class.
        wa = Container("Web Application", technology="Java and Spring boot")
        db = Container("Database Schema")

        wa >> "Reads from and writes to" >> db

        with wa:
            api_layer = Component("API Layer")
            db_layer = Component("Database Layer")

            api_layer >> "Runs queries/transactions on" >> db_layer

    user >> ("Uses", "browser") >> shop

    with DeploymentEnvironment("Live") as live:

        dg_region_1 = DeploymentGroup("region-1")
        dg_region_2 = DeploymentGroup("region-2")

        # The "Amazon Web Services - ..." tags are those of the Structurizr AWS theme (amazon-web-services-2020.04.30),
        # so applying that theme gives these nodes its colours and icons.
        with DeploymentNode("Amazon Web Services") as aws:
            aws.add_tags("Amazon Web Services - Cloud")

            with DeploymentNode("ap-southeast-1") as region_ap_southeast_1:
                region_ap_southeast_1.add_tags("Amazon Web Services - Region")

                dns = InfrastructureNode(
                    "DNS Router",
                    description="Routes incoming requests based upon domain name.",
                    technology="Route 53",
                    tags={"Amazon Web Services - Route 53"}
                )

                lb = InfrastructureNode(
                    "Load Balancer",
                    description="Automatically distributes incoming application traffic.",
                    technology="Elastic Load Balancer",
                    tags={"Amazon Web Services - Elastic Load Balancing"}
                )

                dns >> ("Fowards requests to", "HTTP") >> lb

                with DeploymentNode("Autoscaling Group", tags={"Amazon Web Services - Auto Scaling"}) as asg:
                    with DeploymentNode("Amazon EC2 - Ubuntu Server", tags={"Amazon Web Services - EC2 Instance"}):
                        lb >> "Forwards requests to" >> ContainerInstance(wa, deployment_groups=[dg_region_1])

                with DeploymentNode("Amazon RDS", tags={"Amazon Web Services - RDS"}) as rds:
                    with DeploymentNode("MySQL", tags={"Amazon Web Services - RDS MySQL instance"}):
                        database_instance = ContainerInstance(db, deployment_groups=[dg_region_1])

            with DeploymentNode("us-east-1") as region_us_east_1:
                region_us_east_1.add_tags("Amazon Web Services - Region")

                dns = InfrastructureNode(
                    "DNS Router",
                    description="Routes incoming requests based upon domain name.",
                    technology="Route 53",
                    tags={"Amazon Web Services - Route 53"}
                )

                lb = InfrastructureNode(
                    "Load Balancer",
                    description="Automatically distributes incoming application traffic.",
                    technology="Elastic Load Balancer",
                    tags={"Amazon Web Services - Elastic Load Balancing"}
                )

                dns >> ("Fowards requests to", "HTTP") >> lb

                with DeploymentNode("Autoscaling Group", tags={"Amazon Web Services - Auto Scaling"}) as asg:
                    with DeploymentNode("Amazon EC2 - Ubuntu Server", tags={"Amazon Web Services - EC2 Instance"}):
                        lb >> "Forwards requests to" >> ContainerInstance(wa, deployment_groups=[dg_region_2])

                with DeploymentNode("Amazon RDS", tags={"Amazon Web Services - RDS"}) as rds:
                    with DeploymentNode("MySQL", tags={"Amazon Web Services - RDS MySQL instance"}):
                        database_instance = ContainerInstance(db, deployment_groups=[dg_region_2])

    SystemContextView(
        software_system_selector=shop,
        key='online_shop_context_00',
        description="System context of Online Shop",
    )

    DeploymentView(
        environment=live,
        key='aws-deployment-view',
        software_system_selector=shop,
        title="Amazon Web Services Deployment",
        description="Deployment view of the web application on AWS",
        auto_layout='lr',
    )

    StyleElements(on=['Element'], background='#ffffff')
    StyleElements(on=['Container'], background='#ffffff')
    StyleElements(on=[wa], background='#ffffff')
    StyleElements(on=[user], shape='Person')
    StyleElements(on=[db], shape='Cylinder')

    # Write the JSON with: buildzr export examples/amazon_web_services.py --pretty