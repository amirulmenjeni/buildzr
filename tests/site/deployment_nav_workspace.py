"""The 'deployment-nav' fixture (``tests/site/fixtures/deployment-nav``): software that runs in zero, one or several places."""

from __future__ import annotations

from buildzr.dsl import (
    Container,
    ContainerInstance,
    ContainerView,
    DeploymentEnvironment,
    DeploymentNode,
    DeploymentView,
    Person,
    SoftwareSystem,
    SoftwareSystemInstance,
    SystemLandscapeView,
    Workspace,
)


def deployment_nav_workspace() -> Workspace:
    """A factory: the Shop system with four containers and a Payments system.

    - API runs in three places: two nodes in Production (one with ``instances='3'``) and one in Staging.
    - Database runs in one place (Production).
    - Worker is in the model but deployed nowhere (zero).
    - Cache runs in Dev, an environment without a deployment view: an instance no view draws.
    - Payments (the system) has one SoftwareSystemInstance in Production; Legacy (a system) is deployed nowhere.
    """
    with Workspace("Deployment navigation", scope=None, implied_relationships=True) as w:
        customer = Person("Customer")
        with SoftwareSystem("Shop") as shop:
            api = Container("API", technology="Python")
            db = Container("Database", technology="PostgreSQL")
            Container("Worker", technology="Python")
            cache = Container("Cache", technology="Redis")
        payments = SoftwareSystem("Payments")
        SoftwareSystem("Legacy")
        customer >> "Buys from" >> api
        api >> "Reads from and writes to" >> db
        api >> "Pays with" >> payments

        with DeploymentEnvironment("Production") as production:
            with DeploymentNode("AWS", technology="Amazon Web Services"):
                with DeploymentNode("eu-west-1", technology="AWS region"):
                    with DeploymentNode("ECS Cluster", technology="Amazon ECS", instances="3"):
                        ContainerInstance(api)
                    with DeploymentNode("RDS", technology="Amazon RDS"):
                        ContainerInstance(db)
                with DeploymentNode("us-east-1", technology="AWS region"):
                    with DeploymentNode("ECS Cluster", technology="Amazon ECS"):
                        ContainerInstance(api)
            with DeploymentNode("Payment provider"):
                SoftwareSystemInstance(payments)
        with DeploymentEnvironment("Staging") as staging:
            with DeploymentNode("Staging server", technology="Ubuntu"):
                ContainerInstance(api)
        with DeploymentEnvironment("Dev"):
            with DeploymentNode("Laptop"):
                ContainerInstance(cache)

        SystemLandscapeView(key="landscape", description="Everything")
        ContainerView(software_system_selector=shop, key="shop-containers", description="The containers of the shop")
        DeploymentView(environment=production, key="production", software_system_selector=shop, description="Shop in production")
        DeploymentView(environment=staging, key="staging", software_system_selector=shop, description="Shop in staging")
    return w
