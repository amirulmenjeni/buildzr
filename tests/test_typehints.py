# All tests in this file are to ensure that the typehints are correct.
# IMPORTANT: Run pytest with --mypy flag to check for typehint errors.

import pytest
from typing import Optional
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    DeploymentEnvironment,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance,
    desc,
)

def test_relationship_typehint_person_to_person() -> Optional[None]:

    with Workspace("w") as w:
        p1 = Person("p1")
        p2 = Person("p2")
        p3 = Person("p3")
        p4 = Person("p4")

        # Define relationships
        p1 >> "greet" >> p2
        p1 >> [
            p3,
            desc("greet") >> p4
        ]

def test_relationship_typehint_person_to_software_system() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        s3 = SoftwareSystem("s3")
        s4 = SoftwareSystem("s4")

        # Define relationships
        p >> "use" >> s1
        p >> [
            s2,
            desc("use") >> s3,
            desc("use") >> s4
        ]

def test_relationship_typehint_person_to_container() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        p >> "use" >> c1
        p >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_person_to_component() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s = SoftwareSystem("s")
        with s:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        p >> "use" >> c1
        p >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_software_system_to_software_system() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        s3 = SoftwareSystem("s3")
        s4 = SoftwareSystem("s4")

        # Define relationships
        s1 >> "integrate" >> s2
        s1 >> [
            s3,
            desc("integrate") >> s4
        ]

def test_relationship_typehint_software_system_to_container() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        with s2:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        s1 >> "use" >> c1
        s1 >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_software_system_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        with s2:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        s1 >> "use" >> c1
        s1 >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_container_to_container() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        c1 >> "call" >> c2
        c1 >> [
            c3,
            desc("call") >> c4
        ]

def test_relationship_typehint_container_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            with c2:
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        c1 >> "call" >> c2.c3
        c1 >> [
            c2.c4,
            desc("call") >> c3,
            desc("call") >> c4
        ]

def test_relationship_typehint_component_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        c1 >> "call" >> c2
        c1 >> [
            c3,
            desc("call") >> c4
        ]

def test_relationship_matrix() -> Optional[None]:

    # NOTE: If you remove to `# type: ignore[operator]` from the relationships
    #       below, mypy _should_ complain about the relationships that are not
    #       allowed.
    #
    # Test all possible relationship combinations between source and destination types,
    # as per described in https://docs.structurizr.com/dsl/language#relationship:
    #
    # Person                    --> Person, Software System, Container, Component
    # Software System           --> Person, Software System, Container, Component
    # Container                 --> Person, Software System, Container, Component
    # Component                 --> Person, Software System, Container, Component
    # Deployment Node           --> Deployment Node
    # Infrastructure Node       --> Deployment Node, Infrastructure Node, Software System Instance, Container Instance
    # Software System Instance  --> Infrastructure Node
    # Container Instance        --> Infrastructure Node
    #
    # So that means we need to assert that the following relationships are not allowed:
    # Person                    -/-> Deployment Node, Infrastructure Node, Software System Instance, Container Instance
    # Software System           -/-> Deployment Node, Infrastructure Node, Software System Instance, Container Instance
    # Container                 -/-> Deployment Node, Infrastructure Node, Software System Instance, Container Instance
    # Component                 -/-> Deployment Node, Infrastructure Node, Software System Instance, Container Instance
    # Deployment Node           -/-> Person, Software System, Container, Component, Infrastructure Node, Software System Instance, Container Instance
    # Infrastructure Node       -/-> Person, Software System, Container, Component
    # Software System Instance  -/-> Person, Software System, Container, Component, Deployment Node, Software System Instance, Container Instance
    # Container Instance        -/-> Person, Software System, Container, Component, Deployment Node, Software System Instance, Container Instance

    with Workspace("soa-example", scope=None) as w:

        person = Person("User")

        with SoftwareSystem("Software System") as software_system:
            with Container("API Service") as container_api:
                component_data_layer = Component("Data Layer")
                component_business_layer = Component("Business Layer")
            container_auth = Container("Authentication Service")
            container_data = Container("Data Processing Service")
            container_db = Container("Database")

        with DeploymentEnvironment("Development") as development:
            with DeploymentNode(
                "Developer Machine",
                description="Local development environment",
                technology="Docker Desktop",
            ) as dev_host:
                software_system_instance = SoftwareSystemInstance(software_system)
                software_system_instance_1 = SoftwareSystemInstance(software_system)
                container_instance_api = ContainerInstance(container_api)
                container_instance_auth = ContainerInstance(container_auth)
                ContainerInstance(container_data)
                ContainerInstance(container_db)

                lb = InfrastructureNode("Load Balancer")
                lb >> "Distributes traffic to" >> container_instance_api

        # Person
        person >> dev_host # type: ignore[operator]
        person >> lb # type: ignore[operator]
        person >> software_system_instance # type: ignore[operator]
        person >> container_instance_api # type: ignore[operator]

        # Software System
        software_system >> dev_host # type: ignore[operator]
        software_system >> lb # type: ignore[operator]
        software_system >> software_system_instance # type: ignore[operator]
        software_system >> container_instance_api # type: ignore[operator]

        # Container
        container_api >> dev_host # type: ignore[operator]
        container_api >> lb # type: ignore[operator]
        container_api >> software_system_instance # type: ignore[operator]
        container_api >> container_instance_api # type: ignore[operator]

        # Component
        component_data_layer >> dev_host # type: ignore[operator]
        component_data_layer >> lb # type: ignore[operator]
        component_data_layer >> software_system_instance # type: ignore[operator]
        component_data_layer >> container_instance_api # type: ignore[operator]

        # Deployment Node
        dev_host >> person # type: ignore[operator]
        dev_host >> software_system # type: ignore[operator]
        dev_host >> container_api # type: ignore[operator]
        dev_host >> component_data_layer # type: ignore[operator]
        dev_host >> lb # type: ignore[operator]
        dev_host >> software_system_instance # type: ignore[operator]
        dev_host >> container_instance_api # type: ignore[operator]

        # Infrastructure Node
        lb >> person # type: ignore[operator]
        lb >> software_system # type: ignore[operator]
        lb >> container_api # type: ignore[operator]
        lb >> component_data_layer # type: ignore[operator]

        # Software System Instance
        software_system_instance >> person # type: ignore[operator]
        software_system_instance >> software_system # type: ignore[operator]
        software_system_instance >> container_api # type: ignore[operator]
        software_system_instance >> component_data_layer # type: ignore[operator]
        software_system_instance >> dev_host # type: ignore[operator]
        software_system_instance >> container_instance_api # type: ignore[operator]
        software_system_instance >> software_system_instance_1 # type: ignore[operator]

        # Container Instance
        container_instance_api >> person # type: ignore[operator]
        container_instance_api >> software_system # type: ignore[operator]
        container_instance_api >> container_api # type: ignore[operator]
        container_instance_api >> component_data_layer # type: ignore[operator]
        container_instance_api >> dev_host # type: ignore[operator]
        container_instance_api >> software_system_instance # type: ignore[operator]
        container_instance_api >> container_instance_auth # type: ignore[operator]