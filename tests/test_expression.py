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

    with Workspace('w') as w:
        u = Person('u', tags={'user'})
        s = SoftwareSystem('s', properties={
            'repo': 'https://github.com/amirulmenjeni/buildzr',
        })
        with s:
            app = Container('app')
            db = Container('db', technology='mssql')

            app >> "Uses" >> db | With(
                tags={'backend-interface', 'mssql'}
            )

        u >> "Uses" >> s | With(
            tags={'frontend-interface'},
            properties={
                'url': 'http://example.com/docs/api/endpoint',
            }
        )

    return w

def test_filter_elements_by_tags(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'Person' in e.tags,
            lambda w, e: 'Container' in e.tags,
            lambda w, e: 'user' in e.tags
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 3

def test_filter_elements_by_technology(workspace: Workspace) -> Optional[None]:

    # Note that some elements do not have technology attribute, like `Person` or
    # `SoftwareSystem`.
    #
    # This should not cause any problem to the filter.
    filter = expression.Expression(
        include_elements=[
            lambda w, e: e.technology == 'mssql',
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 'db'

def test_filter_elements_by_sources_and_destinations(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'u' in e.sources.names,
            lambda w, e: 'db' in e.destinations.names and 'Container' in e.destinations.tags,
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 2
    assert elements[0].model.name == 's'
    assert elements[1].model.name == 'app'

def test_filter_elements_by_properties(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'repo' in e.properties.keys() and 'github.com' in e.properties['repo']
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 's'

def test_filter_elements_by_equal_operator(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: e == cast(SoftwareSystem, workspace.s).app,
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert elements[0].model.name == 'app'

def test_include_all_elements(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression()

    elements = filter.elements(workspace)

    all_elements = list(Explorer(workspace).walk_elements())

    assert len(elements) == len(all_elements)

def test_filter_relationships_by_tags(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: 'frontend-interface' in r.tags
        ]
    )

    elements = filter.elements(workspace)
    relationships = filter.relationships(workspace)
    all_elements = list(Explorer(workspace).walk_elements())

    assert len(relationships) == 1
    assert len(elements) == len(all_elements)
    assert relationships[0].source.model.name == 'u'
    assert relationships[0].destination.model.name == 's'

def test_filter_relationships_by_technology(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: 'mssql' in r.tags
        ]
    )

    elements = filter.elements(workspace)
    relationships = filter.relationships(workspace)
    all_elements = list(Explorer(workspace).walk_elements())

    assert len(relationships) == 1
    assert len(elements) == len(all_elements)
    assert relationships[0].source.model.name == 'app'
    assert relationships[0].destination.model.name == 'db'

def test_filter_relationships_by_source(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: r.source == cast(SoftwareSystem, workspace.s).app
        ]
    )

    elements = filter.elements(workspace)
    relationships = filter.relationships(workspace)
    all_elements = list(Explorer(workspace).walk_elements())

    assert len(relationships) == 1
    assert len(elements) == len(all_elements)
    assert relationships[0].source.model.name == 'app'
    assert relationships[0].destination.model.name == 'db'

def test_filter_relationships_by_destination(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: r.destination == cast(SoftwareSystem, workspace.s).db
        ]
    )

    elements = filter.elements(workspace)
    relationships = filter.relationships(workspace)
    all_elements = list(Explorer(workspace).walk_elements())

    assert len(relationships) == 1
    assert len(elements) == len(all_elements)
    assert relationships[0].source.model.name == 'app'
    assert relationships[0].destination.model.name == 'db'

def test_filter_relationships_by_properties(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: 'url' in r.properties.keys() and 'example.com' in r.properties['url']
        ]
    )

    elements = filter.elements(workspace)
    relationships = filter.relationships(workspace)
    all_elements = list(Explorer(workspace).walk_elements())

    assert len(relationships) == 1
    assert len(elements) == len(all_elements)
    assert 'url' in relationships[0].model.properties.keys()
    assert 'example.com' in relationships[0].model.properties['url']

def test_filter_element_with_workspace_path(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: e == w.software_system().s.db,
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert isinstance(elements[0], Container)
    assert elements[0].model.technology == 'mssql'

def test_filter_relationship_with_workspace_path(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: r.source == w.person().u
        ]
    )

    relationships = filter.relationships(workspace)

    assert len(relationships) == 1
    assert relationships[0].model.destinationId == workspace.software_system().s.model.id

def test_filter_elements_with_excludes(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'Person' in e.tags,
            lambda w, e: 'Container' in e.tags,
            lambda w, e: 'user' in e.tags
        ],
        exclude_elements=[
            lambda w, e: e == w.person().u
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 2
    assert workspace.person().u.model.id not in list(map(lambda x: x.model.id, elements))

def test_filter_relationships_with_excludes(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_relationships=[
            lambda w, r: any(['interface' in tag for tag in r.tags]) # True for all relationships
        ],
        exclude_relationships=[
            lambda w, r: r.source == w.person().u
        ]
    )

    relationships = filter.relationships(workspace)
    assert len(relationships) == 1

def test_filter_elements_without_includes_only_excludes(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        exclude_elements=[
            lambda w, e: w.person().u == e
        ]
    )

    elements = filter.elements(workspace)
    assert workspace.person().u.model.id not in list(map(lambda x: x.model.id, elements))

def test_filter_relationships_without_includes_only_excludes(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        exclude_relationships=[
            lambda w, r: r.source == w.person().u
        ]
    )

    relationships = filter.relationships(workspace)
    assert len(relationships) == 1

def test_filter_type(workspace: Workspace) -> Optional[None]:
    # Create an expression with include_elements and exclude_elements

    filter = expression.Expression(
        include_elements=[
            lambda w, e: e.type == Person,
            lambda w, e: e.type == Container,
        ],
    )

    elements = filter.elements(workspace)

    assert {
        workspace.person().u.model.id,
        workspace.software_system().s.app.model.id,
        workspace.software_system().s.db.model.id,
    }.issubset({ id for id in map(lambda x: x.model.id, elements) })
    assert len(elements) == 3