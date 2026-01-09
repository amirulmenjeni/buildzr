from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Container,
    DeploymentEnvironment,
    DeploymentGroup,
    ContainerInstance,
    DeploymentNode,
    DeploymentView,
)

with Workspace("w", scope=None) as w:
    with SoftwareSystem("Software System") as software_system:
        database = Container("Database")
        api = Container("Service API")
        api >> "Uses" >> database

    with DeploymentEnvironment("Productionzz") as production:
        service_instance_1 = DeploymentGroup("Service Instance 1")
        service_instance_2 = DeploymentGroup("Service Instance 2")

        with DeploymentNode("Server 1") as server_1:
            ContainerInstance(api, [service_instance_1])
            with DeploymentNode("Database Server"):
                ContainerInstance(database, [service_instance_1])
        with DeploymentNode("Server 2") as server_2:
            ContainerInstance(api, [service_instance_2])
            with DeploymentNode("Database Server"):
                ContainerInstance(database, [service_instance_2])

    DeploymentView(
        environment=production,
        key='deployment-view-no-software-system',
    )

    DeploymentView(
        environment=production,
        key='deployment-view-with-software-system',
        software_system_selector=software_system,
    )

    w.save(path='deployment_groups.json', pretty=True)