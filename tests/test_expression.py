import pytest
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
    expression,
    DeploymentEnvironment,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance,
    With,
)
from buildzr.dsl import Explorer
from typing import Optional, List, cast

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

        with DeploymentEnvironment('Development') as development:
            with DeploymentNode('Developer Machine') as developer_machine:
                s_instance = SoftwareSystemInstance(s)
                ContainerInstance(app)
                with DeploymentNode('Database Server'):
                    ContainerInstance(db)

                firewall = InfrastructureNode('Firewall')
                firewall >> s_instance

        with DeploymentEnvironment('Production') as production:
            server_1 = DeploymentNode('Server 1')
            server_2 = DeploymentNode('Server 2')

            with server_1:
                s_instance = SoftwareSystemInstance(s)
                ContainerInstance(app)
                with DeploymentNode('Database Server 1'):
                    ContainerInstance(db)
                firewall = InfrastructureNode('Firewall')
                firewall >> s_instance

            with server_2:
                s_instance = SoftwareSystemInstance(s)
                ContainerInstance(app)
                with DeploymentNode('Database Server 2'):
                    ContainerInstance(db)
                firewall = InfrastructureNode('Firewall')
                firewall >> s_instance

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
    assert isinstance(elements[0], Container) and elements[0].model.name == 'db'

def test_filter_elements_by_sources_and_destinations(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'u' in e.sources.names,
            lambda w, e: 'db' in e.destinations.names and 'Container' in e.destinations.tags,
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 2
    assert isinstance(elements[0], SoftwareSystem) and elements[0].model.name == 's'
    assert isinstance(elements[1], Container) and elements[1].model.name == 'app'

def test_filter_elements_by_properties(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: 'repo' in e.properties.keys() and 'github.com' in e.properties['repo']
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert isinstance(elements[0], SoftwareSystem) and elements[0].model.name == 's'

def test_filter_elements_by_equal_operator(workspace: Workspace) -> Optional[None]:

    filter = expression.Expression(
        include_elements=[
            lambda w, e: e == cast(SoftwareSystem, workspace.s).app,
        ]
    )

    elements = filter.elements(workspace)

    assert len(elements) == 1
    assert isinstance(elements[0], Container) and elements[0].model.name == 'app'

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
    assert isinstance(relationships[0].source, Person) and relationships[0].source.model.name == 'u'
    assert isinstance(relationships[0].destination, SoftwareSystem) and relationships[0].destination.model.name == 's'

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
    assert isinstance(relationships[0].source, Container) and relationships[0].source.model.name == 'app'
    assert isinstance(relationships[0].destination, Container) and relationships[0].destination.model.name == 'db'

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
    assert isinstance(relationships[0].source, Container) and relationships[0].source.model.name == 'app'
    assert isinstance(relationships[0].destination, Container) and relationships[0].destination.model.name == 'db'

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
    assert isinstance(relationships[0].source, Container) and relationships[0].source.model.name == 'app'
    assert isinstance(relationships[0].destination, Container) and relationships[0].destination.model.name == 'db'

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

def test_filter_by_environment(workspace: Workspace) -> Optional[None]:

    # Create an expression to get all the elements of a specific environment.

    filter_development = expression.Expression(
        include_elements=[
            lambda w, e: (
                e.environment == "Development" and
                e.type in (ContainerInstance, SoftwareSystemInstance)
            )
        ],
    )

    filter_production = expression.Expression(
        include_elements=[
            lambda w, e: (
                e.environment == "Production" and
                e.type in (ContainerInstance, InfrastructureNode)
            )
        ],
    )

    elements = filter_development.elements(workspace)

    assert len(elements) == 3
    assert isinstance(elements[0], SoftwareSystemInstance)
    assert isinstance(elements[1], ContainerInstance)
    assert isinstance(elements[2], ContainerInstance)

    elements = filter_production.elements(workspace)
    assert len(elements) == 6
    assert isinstance(elements[0], ContainerInstance)
    assert isinstance(elements[1], ContainerInstance)
    assert isinstance(elements[2], InfrastructureNode)
    assert isinstance(elements[3], ContainerInstance)
    assert isinstance(elements[4], ContainerInstance)
    assert isinstance(elements[5], InfrastructureNode)

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
    assert len(relationships) == 13

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

def test_filter_deployment_nodes(workspace: Workspace) -> Optional[None]:
    # Create an expression with include_elements and exclude_elements

    filter_development = expression.Expression(
        include_elements=[
            lambda w, e: e.type == DeploymentNode and e.environment == "Development",
        ],
    )

    filter_production = expression.Expression(
        include_elements=[
            lambda w, e: e.type == DeploymentNode and e.environment == "Production",
        ],
    )

    development_nodes = cast(List[DeploymentNode], filter_development.elements(workspace))
    production_nodes = cast(List[DeploymentNode], filter_production.elements(workspace))

    assert len(development_nodes) == 2
    assert development_nodes[0].model.name == "Developer Machine"
    assert development_nodes[1].model.name == "Database Server"

    assert len(production_nodes) == 4
    assert production_nodes[0].model.name == "Server 1"
    assert production_nodes[1].model.name == "Database Server 1"
    assert production_nodes[2].model.name == "Server 2"
    assert production_nodes[3].model.name == "Database Server 2"

def test_filter_infrastructure_nodes(workspace: Workspace) -> Optional[None]:

    filter_development = expression.Expression(
        include_elements=[
            lambda w, e: e.type == InfrastructureNode and e.environment == "Development",
        ],
    )

    filter_production = expression.Expression(
        include_elements=[
            lambda w, e: e.type == InfrastructureNode and e.environment == "Production",
        ],
    )

    development_elements = cast(List[InfrastructureNode], filter_development.elements(workspace))
    production_elements = cast(List[InfrastructureNode], filter_production.elements(workspace))

    assert len(development_elements) == 1
    assert development_elements[0].model.name == "Firewall"

    assert len(production_elements) == 2
    assert production_elements[0].model.name == "Firewall"
    assert production_elements[1].model.name == "Firewall"

def test_filter_software_system_instance_ids(workspace: Workspace) -> Optional[None]:

    # Create an expression to get all the software system instances of a specific software system.

    filter = expression.Expression(
        include_elements=[
            lambda w, e: e.is_instance_of(w.software_system().s),
        ],
    )

    elements = cast(List[SoftwareSystemInstance], filter.elements(workspace))

    assert len(elements) == 3
    assert elements[0].model.environment == "Development"
    assert elements[1].model.environment == "Production"
    assert elements[2].model.environment == "Production"

def test_filter_container_instance_ids(workspace: Workspace) -> Optional[None]:

    # Create an expression to get all the container instances of a specific container.

    filter_app = expression.Expression(
        include_elements=[
            lambda w, e: e.is_instance_of(w.software_system().s.app),
        ],
    )

    filter_db = expression.Expression(
        include_elements=[
            lambda w, e: e.is_instance_of(w.software_system().s.db),
        ],
    )

    app_instances = cast(List[ContainerInstance], filter_app.elements(workspace))
    db_instances = cast(List[ContainerInstance], filter_db.elements(workspace))

    assert len(app_instances) == 3
    assert app_instances[0].model.environment == "Development"
    assert app_instances[1].model.environment == "Production"
    assert app_instances[2].model.environment == "Production"

    assert len(db_instances) == 3
    assert db_instances[0].model.environment == "Development"
    assert db_instances[1].model.environment == "Production"
    assert db_instances[2].model.environment == "Production"