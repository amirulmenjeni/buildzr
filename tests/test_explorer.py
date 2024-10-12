import pytest
from typing import Optional
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    DslRelationship,
    With,
)
from buildzr.dsl import Explorer

def test_walk() -> Optional[None]:

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
                            .where(lambda db, api, ui: [
                                ui >> ("Calls HTTP API from", "http/api") >> api,
                                api >> ("Runs queries from", "sql/sqlite") >> db,
                            ]),\
                        Container("database"),
                    )\
                    .where(lambda webapp, database: [
                        webapp >> "Uses" >> database
                    ])
            )\
            .where(lambda u, s: [
                u >> "Runs SQL queries" >> s.database
            ], implied=True)

    explorer = Explorer(w).walk_elements()
    assert next(explorer).model.name == 'u'
    assert next(explorer).model.name == 's'
    assert next(explorer).model.name == 'webapp'
    assert next(explorer).model.name == 'database layer'
    assert next(explorer).model.name == 'API layer'
    assert next(explorer).model.name == 'UI layer'
    assert next(explorer).model.name == 'database'
