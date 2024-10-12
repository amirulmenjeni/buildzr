import pytest
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    expression,
    With,
)
from buildzr.dsl import Explorer
from typing import Optional, cast

@pytest.fixture
def workspace() -> Workspace:

    w = Workspace('w')\
        .contains(
            Person('u', tags={'user'}),
            SoftwareSystem('s')\
            .contains(
                Container('app'),
                Container('db', technology='mssql'),
            )\
            .where(lambda app, db: [
                app >> "Uses" >> db | With(tags={'backend-interface'}),
            ])
        )\
        .where(lambda u, s:
            u >> "Uses" >> s | With(tags={'frontend-interface'})
        )

    return w

def test_filter_elements_by_tags(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        elements=[
            lambda e: 'Person' in e.tags,
            lambda e: 'Container' in e.tags,
            lambda e: 'user' in e.tags
        ]
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 3

def test_filter_elements_by_technology(workspace: Workspace) -> Optional[None]:

    # Note that some elements do not have technology attribute, like `Person` or
    # `SoftwareSystem`.
    #
    # This should not cause any problem to the filter.
    filter = expression.Expression(
        elements=[
            lambda e: e.technology == 'mssql',
        ]
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 'db'

def test_filter_elements_by_sources_and_destinations(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        elements=[
            lambda e: 'u' in e.sources.names,
            lambda e: 'db' in e.destinations.names and 'Container' in e.destinations.tags,
        ]
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 2
    assert elements[0].model.name == 's'
    assert elements[1].model.name == 'app'

def test_filter_elements_by_properties(workspace: Workspace) -> Optional[None]:
    # TODO: Add `properties` property to the `DslElement`s first!
    pass

def test_filter_elements_by_equal_operator(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        elements=[
            lambda e: e == cast(SoftwareSystem, workspace.s).app,
        ]
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 'app'

def test_include_all_elements(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression()

    elements, _ = filter.run(workspace)

    all_elements = list(Explorer(workspace).walk_elements())

    assert len(elements) == len(all_elements)

def test_filter_relationships_by_tags(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        relationships=[
            lambda r: 'frontend-interface' in r.tags
        ]
    )

    _, relationships = filter.run(workspace)

    assert len(relationships) == 1
    assert relationships[0].source.model.name == 'u'
    assert relationships[0].destination.model.name == 's'