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

    explorer = Explorer(workspace).walk_relationships()

    next_relationship = next(explorer)
    assert next_relationship.model.description == "Runs SQL queries"
    assert next_relationship.model.sourceId == cast(Person, workspace.u).model.id
    assert next_relationship.model.destinationId == cast(SoftwareSystem, workspace.s).database.model.id

    # Note: implied relationships
    next_relationship = next(explorer)
    assert next_relationship.model.description == "Runs SQL queries"
    assert next_relationship.model.sourceId == cast(Person, workspace.u).model.id
    assert next_relationship.model.destinationId == cast(SoftwareSystem, workspace.s).model.id

    next_relationship = next(explorer)
    assert next_relationship.model.description == "Uses"
    assert next_relationship.model.sourceId == cast(SoftwareSystem, workspace.s).webapp.model.id
    assert next_relationship.model.destinationId == cast(SoftwareSystem, workspace.s).database.model.id

    next_relationship = next(explorer)
    assert next_relationship.model.description == "Runs queries from"
    assert next_relationship.model.sourceId == cast(SoftwareSystem, workspace.s).webapp.api_layer.model.id
    assert next_relationship.model.destinationId == cast(SoftwareSystem, workspace.s).webapp.database_layer.model.id

    next_relationship = next(explorer)
    assert next_relationship.model.description == "Calls HTTP API from"
    assert next_relationship.model.sourceId == cast(SoftwareSystem, workspace.s).webapp.ui_layer.model.id
    assert next_relationship.model.destinationId == cast(SoftwareSystem, workspace.s).webapp.api_layer.model.id