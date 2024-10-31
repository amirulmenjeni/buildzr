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

    w = Workspace("w")\
            .contains(
                Person("u"),
                SoftwareSystem("s")\
                    .contains(
                        Container("webapp")\
                            .contains(
                                Component("database layer"),
                                Component("API layer"),
                                Component("UI layer"),
                            )\
                            .where(lambda app: [
                                app.ui_layer >> ("Calls HTTP API from", "http/api") >> app.api_layer,
                                app.api_layer >> ("Runs queries from", "sql/sqlite") >> app.database_layer
                            ]),\
                        Container("database"),
                    )\
                    .where(lambda s: [
                        s.webapp >> "Uses" >> s.database
                    ])
            )\
            .where(lambda w: [
                w.person().u >> "Runs SQL queries" >> w.software_system().s.database
            ], implied=True)

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