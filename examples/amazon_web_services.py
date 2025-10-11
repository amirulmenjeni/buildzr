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

    with SoftwareSystem("X") as x:

        # Notice that we don't need to specify the tags "Application" and "Database"
        # for styling -- just pass the `wa` and `db` variables directly to the `StyleElements` class.
        wa = Container("Web Application", technology="Java and Spring boot")
        db = Container("Database Schema")

        wa >> "Reads from and writes to" >> db

        with wa:
            api_layer = Component("API Layer")
            db_layer = Component("Database Layer")

            api_layer >> "Runs queries/transactions on" >> db_layer

    user >> ("Uses", "browser") >> x

    with DeploymentEnvironment("Live") as live:

        dg_region_1 = DeploymentGroup("region-1")
        dg_region_2 = DeploymentGroup("region-2")

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
                    tags={"Amazon Web Services - Elastic Load Balancer"}
                )

                dns >> ("Fowards requests to", "HTTP") >> lb

                with DeploymentNode("Autoscaling Group", tags={"Amazon Web Services - Autoscaling Group"}) as asg:
                    with DeploymentNode("Amazon EC2 - Ubuntu Server", tags={"Amazon Web Services - EC2 Instance"}):
                        lb >> "Forwards requests to" >> ContainerInstance(wa, deployment_groups=[dg_region_1])

                with DeploymentNode("Amazon RDS", tags={"Amazon Web Services - RDS Instance"}) as rds:
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
                    tags={"Amazon Web Services - Elastic Load Balancer"}
                )

                dns >> ("Fowards requests to", "HTTP") >> lb

                with DeploymentNode("Autoscaling Group", tags={"Amazon Web Services - Autoscaling Group"}) as asg:
                    with DeploymentNode("Amazon EC2 - Ubuntu Server", tags={"Amazon Web Services - EC2 Instance"}):
                        lb >> "Forwards requests to" >> ContainerInstance(wa, deployment_groups=[dg_region_2])

                with DeploymentNode("Amazon RDS", tags={"Amazon Web Services - RDS Instance"}) as rds:
                    with DeploymentNode("MySQL", tags={"Amazon Web Services - RDS MySQL instance"}):
                        database_instance = ContainerInstance(db, deployment_groups=[dg_region_2])

    SystemContextView(
        software_system_selector=x,
        key='x_context_00',
        description="System context of X",
    )

    DeploymentView(
        environment=live,
        key='aws-deployment-view',
        software_system_selector=x,
        title="Amazon Web Services Deployment",
        description="Deployment view of the web application on AWS",
        auto_layout='lr',
    )

    StyleElements(on=['Element'], background='#ffffff')
    StyleElements(on=['Container'], background='#ffffff')
    StyleElements(on=[wa], background='#ffffff')
    StyleElements(on=[user], shape='Person')
    StyleElements(on=[db], shape='Cylinder')

    w.to_json('amazon_web_services.json', pretty=True)