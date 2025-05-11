import pytest
from typing import Optional, cast
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
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
    return w

def test_walk_elements(workspace: Workspace) -> Optional[None]:

    explorer = Explorer(workspace).walk_elements()
    assert next(explorer).model.name == 'u'
    assert next(explorer).model.name == 's'
    assert next(explorer).model.name == 'webapp'
    assert next(explorer).model.name == 'database layer'
    assert next(explorer).model.name == 'API layer'
    assert next(explorer).model.name == 'UI layer'
    assert next(explorer).model.name == 'database'

def test_walk_relationships(workspace: Workspace) -> Optional[None]:

    relationships = list(Explorer(workspace).walk_relationships())
    relationships_set = {
        (relationship.source.model.id, relationship.model.description, relationship.destination.model.id)
        for relationship in relationships
    }

    for relationship in relationships:
        print(f"{relationship.source.model.name} >> {relationship.model.description} >> {relationship.destination.model.name}")

    assert len(relationships) == 5 # Including one additional implied relationship

    for relationship in relationships:
        relationship_set = (
            relationship.source.model.id,
            relationship.model.description,
            relationship.destination.model.id
        )
        assert relationship_set in relationships_set