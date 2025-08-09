import pytest
from typing import Optional, cast
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    DeploymentEnvironment,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance,
    With,
)
from buildzr.dsl.interfaces import DslRelationship
from buildzr.dsl import Explorer

@pytest.fixture
def workspace() -> Workspace:
    with Workspace("w", implied_relationships=True) as w:
        u = Person("u")
        with SoftwareSystem("s") as s:
            with Container("webapp") as webapp:
                Component("database layer")
                Component("API layer")
                Component("UI layer")
                webapp.ui_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer
                webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.database_layer
            Container("database")
            s.webapp >> "Uses" >> s.database
        u >> "Runs SQL queries" >> s.database

        with DeploymentEnvironment('Production') as production:
            with DeploymentNode("Server 1") as server_1:
                SoftwareSystemInstance(s, tags={'si_1'})
                ContainerInstance(webapp, tags={'ci_1'})
                with DeploymentNode("Database Server"):
                    ContainerInstance(s.database, tags={'ci_2'})
            with DeploymentNode("Server 2") as server_2:
                ContainerInstance(webapp, tags={'ci_3'})
                with DeploymentNode("Database Server"):
                    ContainerInstance(s.database, tags={'ci_4'})

                load_balancer = InfrastructureNode("Load Balancer")
                load_balancer >> "Routes to" >> server_1

    return w

def test_walk_elements(workspace: Workspace) -> Optional[None]:

    expected_element_and_value = [
        (Person, 'u'),
        (SoftwareSystem, 's'),
        (Container, 'webapp'),
        (Component, 'database layer'),
        (Component, 'API layer'),
        (Component, 'UI layer'),
        (Container, 'database'),
        (DeploymentNode, 'Server 1'),
        (SoftwareSystemInstance, 'si_1'),
        (ContainerInstance, 'ci_1'),
        (DeploymentNode, 'Database Server'),
        (ContainerInstance, 'ci_2'),
        (DeploymentNode, 'Server 2'),
        (ContainerInstance, 'ci_3'),
        (DeploymentNode, 'Database Server'),
        (ContainerInstance, 'ci_4'),
        (InfrastructureNode, 'Load Balancer'),
    ]

    explorer = Explorer(workspace).walk_elements()
    for expected_element, expected_value in expected_element_and_value:
        model = next(explorer)
        if isinstance(
            model,
            (Person, SoftwareSystem, Container, Component, DeploymentNode, InfrastructureNode)
        ):
            assert model.model.name == expected_value
        else:
            assert expected_value in model.tags

def test_walk_relationships(workspace: Workspace) -> Optional[None]:

    relationships = list(Explorer(workspace).walk_relationships())
    relationships_set = {
        (relationship.source.model.id, relationship.model.description, relationship.destination.model.id)
        for relationship in relationships
    }

    # 5 explicit relationships.
    # Add one additional implied relationship.
    # And four additional from container instances for each two container instance (2x2=4 + 2x2=4 more).
    #
    # Explanation: if we have containers A and B with relationship A >> "Uses" >> B,
    # and container instances ci_A_1, ci_A_2, ci_B_1, ci_B_2, then we have the
    # following implied instance relationships:
    #   ci_A_1 >> "Uses" >> ci_B_1
    #   ci_A_1 >> "Uses" >> ci_B_2
    #   ci_A_2 >> "Uses" >> ci_B_1
    #   ci_A_2 >> "Uses" >> ci_B_2
    assert len(relationships) == 14

    for relationship in relationships:
        relationship_set = (
            relationship.source.model.id,
            relationship.model.description,
            relationship.destination.model.id
        )
        assert relationship_set in relationships_set