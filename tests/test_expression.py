import pytest
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    expression,
)
from typing import Optional

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
                app >> "Uses" >> db,
            ])
        )\
        .where(lambda u, s:
            u >> "Uses" >> s
        )

    return w

def test_filter_elements_by_tags(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        lambda e, r: 'Person' in e.tags,
        lambda e, r: 'Container' in e.tags,
        lambda e, r: 'user' in e.tags
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 3

def test_filter_elements_by_technology(workspace: Workspace) -> Optional[None]:

    # Note that some elements do not have technology attribute, like `Person` or
    # `SoftwareSystem`.
    #
    # This should not cause any problem to the filter.
    filter = expression.Expression(
        lambda e, r: e.technology == 'mssql'
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 'db'

def test_filter_elements_by_sources_and_destinations(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        lambda e, r: 'u' in e.sources.names,
        lambda e, r: 'db' in e.destinations.names and 'Container' in e.destinations.tags
    )

    elements, _ = filter.run(workspace)

    assert len(elements) == 2
    assert elements[0].model.name == 's'
    assert elements[1].model.name == 'app'

def test_filter_elements_by_properties(workspace: Workspace) -> Optional[None]:
    # TODO: Add `properties` property to the `DslElement`s first!
    pass