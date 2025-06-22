# Using the example from https://structurizr.com/dsl?example=amazon-web-services

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentGroup,
    DeploymentNode,
    InfrastructureNode,
    ContainerInstance,
    DeploymentView,
    StyleElements,
)

with Workspace(
    "Amazon Web Services Example",
    description="An example AWS deployment architecture",
    scope='landscape'
) as w:

    with SoftwareSystem("X") as x:

        # Notice that we don't need to specify the tags "Application" and "Database"
        # for styling -- just pass the `wa` and `db` variables directly to the `StyleElements` class.
        wa = Container("Web Application", technology="Java and Spring boot")
        db = Container("Database Schema")

        wa >> "Reads from and writes to" >> db

    with DeploymentEnvironment("Live") as live:
        with DeploymentNode("Amazon Web Services") as aws:
            aws.add_tags("Amazon Web Services - Cloud")

            with DeploymentNode("US-East-1") as region:
                region.add_tags("Amazon Web Services - Region")

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
                        lb >> "Forwards requests to" >> ContainerInstance(wa)

                with DeploymentNode("Amazon RDS", tags={"Amazon Web Services - RDS Instance"}) as rds:
                    with DeploymentNode("MySQL", tags={"Amazon Web Services - RDS MySQL instance"}):
                        database_instance = ContainerInstance(db)

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
    StyleElements(on=[db], shape='Cylinder')

w.to_json('amazon_web_services.json')