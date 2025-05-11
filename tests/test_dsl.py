from dataclasses import dataclass, fields
import inspect
import pytest
import importlib
from typing import Optional, cast
from buildzr.dsl.interfaces import DslRelationship
from buildzr.dsl import (
    Workspace,
    Group,
    SoftwareSystem,
    Person,
    Container,
    Component,
    With,
    SystemContextView,
    desc,
)
from buildzr.encoders import JsonEncoder

@dataclass
class DslHolder:
    """A `dataclass` for us to hold the objects created using the DSL.

This helps by allowing us to create the workspace and other DSL objects in the
fixture once to be reused across multiple tests.
"""

    workspace: Workspace
    software_system: SoftwareSystem
    person: Person
    container: Container
    component: Component

@pytest.fixture
def dsl() -> DslHolder:

    workspace = Workspace("My Workspace", "A happy place")
    software_system = SoftwareSystem("My Software System")
    person = Person("Super user")
    container = Container("My container")
    component = Component("My component")

    return DslHolder(
        workspace=workspace,
        software_system=software_system,
        person=person,
        container=container,
        component=component,
    )

def test_docstrings(dsl: DslHolder) -> Optional[None]:
    """The docstrings of the DSL object should match the one in the Structurizr schema."""

    models_module = importlib.import_module('buildzr.models')

    classes = [cls for _, cls in inspect.getmembers(models_module, inspect.isclass)]

    class_docstring = {}
    for cls in classes:
        class_name = cls.__name__
        class_doc = cls.__doc__

        if class_doc is None or len(class_doc) == 0:
            class_docstring[class_name] = str()
        else:
            class_docstring[class_name] = class_doc

    for field in fields(dsl):
        dsl_obj = getattr(dsl, field.name)
        dsl_name = dsl_obj.__class__.__name__
        dsl_doc = dsl_obj.__class__.__doc__
        assert dsl_doc is not None
        assert dsl_doc.strip() == class_docstring[dsl_name].strip()

def test_element_ids(dsl: DslHolder) -> Optional[None]:

    assert dsl.workspace._m.id is not None
    assert dsl.person._m.id is not None
    assert dsl.software_system._m.id is not None
    assert dsl.container._m.id is not None
    assert dsl.component._m.id is not None

def test_workspace_has_configuration(dsl: DslHolder) -> Optional[None]:

    assert dsl.workspace._m.configuration is not None

def test_relationship_dsl(dsl: DslHolder) -> Optional[None]:

    dsl.person >> ("uses", "cli") >> dsl.software_system

    assert dsl.person._m.relationships is not None
    assert len(dsl.person._m.relationships) == 1
    assert dsl.person._m.relationships[0].id is not None
    assert dsl.person._m.relationships[0].sourceId == dsl.person.model.id
    assert dsl.person._m.relationships[0].destinationId == dsl.software_system.model.id
    assert dsl.person._m.relationships[0].description == "uses"
    assert dsl.person._m.relationships[0].technology == "cli"

def test_relationship_with_extra_info_using_with(dsl: DslHolder) -> Optional[None]:

    dsl.person >> ("uses", "cli") >> dsl.software_system | With(
        tags={"bash", "terminal"},
        properties={
            "authentication": "ssh",
        },
        url="http://example.com/info/relationship-user-uses-cli",
    )

    assert "bash" in dsl.person.model.relationships[0].tags
    assert "terminal" in dsl.person.model.relationships[0].tags
    assert "authentication" in dsl.person.model.relationships[0].properties.keys()
    assert "ssh" in dsl.person.model.relationships[0].properties['authentication']
    assert "http://example.com/info/relationship-user-uses-cli" == dsl.person.model.relationships[0].url

def test_relationship_with_extra_info_using_has(dsl: DslHolder) -> Optional[None]:

    (dsl.person >> ("uses", "cli") >> dsl.software_system).has(
        tags={"bash", "terminal"},
        properties={
            "authentication": "ssh",
        },
        url="http://example.com/info/relationship-user-uses-cli",
    )

    assert "bash" in dsl.person.model.relationships[0].tags
    assert "terminal" in dsl.person.model.relationships[0].tags
    assert "authentication" in dsl.person.model.relationships[0].properties.keys()
    assert "http://example.com/info/relationship-user-uses-cli" == dsl.person.model.relationships[0].url

def test_relationship_using_uses_method(dsl: DslHolder) -> Optional[None]:

    dsl.person\
        .uses(
            dsl.software_system,
            description="browses",
            technology="browser")\
        .has(
            tags={"webapp"},
            properties={
                "url": "http://link.example.page"
            }
        )

    assert any(dsl.person.model.relationships)
    assert any(dsl.person.model.relationships[0].tags)
    assert any(dsl.person.model.relationships[0].properties.keys())
    assert dsl.person.model.relationships[0].sourceId == dsl.person.model.id
    assert dsl.person.model.relationships[0].destinationId == dsl.software_system.model.id
    assert dsl.person.model.relationships[0].description == "browses"
    assert dsl.person.model.relationships[0].technology == "browser"
    assert set(dsl.person.model.relationships[0].tags.split(',')) == {'Relationship', 'webapp'}
    assert dsl.person.model.relationships[0].properties['url'] == "http://link.example.page"

def test_relationship_dont_work_with_workspace(dsl: DslHolder) -> Optional[None]:

    with pytest.raises(TypeError):
        dsl.workspace >> "uses" >> dsl.person #type: ignore[operator]

    with pytest.raises(TypeError):
        dsl.person >> "uses" >> dsl.workspace #type: ignore[operator]

    with pytest.raises(TypeError):
        dsl.workspace >> "uses" >> dsl.software_system #type: ignore[operator]

def test_workspace_model_inclusion_dsl(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.add_model(dsl.person)
    dsl.workspace.add_model(dsl.software_system)

    with Workspace("w") as w:
        u = Person("u")
        s = SoftwareSystem("s")

    assert any(dsl.workspace._m.model.people)
    assert any(dsl.workspace._m.model.softwareSystems)

def test_parenting(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.add_model(dsl.person)
    dsl.workspace.add_model(dsl.software_system)
    dsl.software_system.add_container(dsl.container)
    dsl.container.add_component(dsl.component)

    assert dsl.person.parent.model.id == dsl.workspace.model.id
    assert dsl.software_system.parent.model.id == dsl.workspace.model.id
    assert dsl.container.parent.model.id == dsl.software_system.model.id
    assert dsl.component.parent.model.id == dsl.container.model.id

def test_making_children(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.add_model(dsl.person)
    dsl.workspace.add_model(dsl.software_system)
    dsl.software_system.add_container(dsl.container)
    dsl.container.add_component(dsl.component)

    assert dsl.workspace.children[0].model.id == dsl.person.model.id
    assert dsl.workspace.children[1].model.id == dsl.software_system.model.id
    assert dsl.software_system.children[0].model.id == dsl.container.model.id
    assert dsl.container.children[0].model.id == dsl.component.model.id

def test_accessing_child_elements(dsl: DslHolder) -> Optional[None]:

    with Workspace('w') as w:
        u = Person('u')
        s = SoftwareSystem('s')
        with s:
            webapp = Container('webapp')
            with webapp:
                Component('database layer')
                Component('API layer')
                Component('UI layer')

                webapp.database_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer
                webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.ui_layer
            Container('database')

    assert type(w.u) is Person
    assert type(w.s) is SoftwareSystem
    assert type(w.s.webapp) is Container
    assert type(w.s.database) is Container
    assert type(w.s.webapp.api_layer) is Component

    if isinstance(w['s'], SoftwareSystem):
        assert type(w['s']['webapp']['database layer']) is Component

def test_relationship_definition_commutativity() -> Optional[None]:

    from buildzr.encoders import JsonEncoder
    import jsondiff #type: ignore[import-untyped]
    import json

    # For now, we have to cheat a bit and manually edit each entity's ID so they
    # they're not identified as differences between the two workspaces. This is
    # because the current IDs are running numbers across the same class of
    # `DslElements`s.
    #
    # So, hashtag TODO.

    w1 = Workspace("w")
    w1.model.id = 1
    u1 = Person("u")
    u1.model.id = "2"
    s1 = SoftwareSystem("s")
    s1.model.id = "3"
    u1 >> "Uses" >> s1
    u1.model.relationships[0].id = "4"
    w1.add_model(u1)
    w1.add_model(s1)

    w2 = Workspace("w")
    w2.model.id = 1
    u2 = Person("u")
    u2.model.id = "2"
    s2 = SoftwareSystem("s")
    s2.model.id = "3"
    w2.add_model(u2)
    w2.add_model(s2)
    u2 >> "Uses" >> s2
    u2.model.relationships[0].id = "4"

    json_str_w1 = json.dumps(w1, cls=JsonEncoder)
    json_str_w2 = json.dumps(w2, cls=JsonEncoder)
    differences = jsondiff.diff(
        json_str_w1,
        json_str_w2,
    )

    assert not differences

def test_relationship_returns_correct_type(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.add_model(dsl.person)
    dsl.workspace.add_model(dsl.software_system)

    relationship = dsl.person >> "Uses" >> dsl.software_system

    assert isinstance(relationship, DslRelationship)
    assert relationship.model.description == "Uses"
    assert relationship.model.destinationId == dsl.software_system.model.id

def test_fluent_workspace_definition() -> Optional[None]:

    with Workspace("w") as w:
        u = Person('u')
        with SoftwareSystem('s') as s:
            with Container('webapp') as webapp:
                Component('database layer')
                Component('API layer')
                Component('UI layer')

                webapp.ui_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer
                webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.database_layer
            Container('database')

            s.webapp >> "Uses" >> s.database | With(
                tags={
                    'api'
                },
                properties={
                    'url': 'https://example.com/api'
                }
            )
        u >> "Uses" >> s | With(
            tags={"5g-network"},
        )

    assert any(w.model.model.people)
    assert any(w.model.model.people[0].relationships)
    assert any(w.model.model.softwareSystems)
    assert any(w.model.model.softwareSystems[0].containers)
    assert any(w.model.model.softwareSystems[0].containers[0].relationships)
    assert any(w.model.model.softwareSystems[0].containers[0].components)
    assert any(w.model.model.softwareSystems[0].containers[0].components[1].relationships)
    assert any(w.model.model.softwareSystems[0].containers[0].components[2].relationships)
    assert not w.model.model.softwareSystems[0].containers[0].components[0].relationships
    assert 'api' in w.model.model.softwareSystems[0].containers[0].relationships[0].tags.split(',')
    assert 'url' in w.model.model.softwareSystems[0].containers[0].relationships[0].properties.keys()
    assert 'example.com' in w.model.model.softwareSystems[0].containers[0].relationships[0].properties['url']

def test_implied_relationship() -> Optional[None]:
    """
    See: https://docs.structurizr.com/java/implied-relationships#createimpliedrelationshipsunlessanyrelationshipexistsstrategy
    """

    # _I think_ the behavior of the implied relationship can't really be tested
    # in the authoring tool, as it is handled by the rendering tool (e.g., the
    # Structurizr Lite or Structurizr On-Premise).
    #
    # But this test ensures that cross-layer relationship _doesn't_ create new
    # relationship. For example, u -> s.database doesn't explicitly create a u
    # -> s relationship in the workspace JSON.

    # TODO: Add a way to enable/disable implied relationships in the DSL.

    with Workspace("w", implied_relationships=True) as w:
        u = Person('u')
        s = SoftwareSystem('s')
        with s:
            db = Container('db')
            app = Container('app')
            with app:
                Component('api layer')
                Component('model layer')
                Component('ui layer')
            app.ui_layer >> ("Calls HTTP API from", "http/api") >> app.api_layer
            app.api_layer >> ("Runs queries from", "sql/sqlite") >> app.model_layer
            app >> "Uses" >> db

        u >> "Runs SQL queries" >> s.db # `u >> "Runs SQL queries" >> s`` should be implied

    assert isinstance(w.u, Person)
    assert isinstance(w.s, SoftwareSystem)
    assert len(w.u.model.relationships) == 2 # Should have u >> R >> s and u >> R >> s.database

    assert w.u.model.relationships[0].description == "Runs SQL queries"
    assert w.u.model.relationships[0].sourceId == w.u.model.id
    assert w.u.model.relationships[0].destinationId == w.s.db.model.id

    assert w.u.model.relationships[1].description == "Runs SQL queries"
    assert w.u.model.relationships[1].sourceId == w.u.model.relationships[0].sourceId
    assert w.u.model.relationships[1].destinationId == w.s.model.id
    assert w.u.model.relationships[1].linkedRelationshipId == w.u.model.relationships[0].id

def test_tags_on_elements() -> Optional[None]:

    u = Person('My User', tags={'admin'})
    ss = SoftwareSystem('My Software System', tags={'External', 'Cloud'})
    container = Container('The Container', tags={'Database'})
    component = Component('A Component', tags={'Views'})

    assert set(u.model.tags.split(',')) == {'Element', 'Person', 'admin'}
    assert u.tags == {'Element', 'Person', 'admin'}

    assert set(ss.model.tags.split(',')) == {'Element', 'Software System', 'External', 'Cloud'}
    assert ss.tags == {'Element', 'Software System', 'External', 'Cloud'}

    assert set(container.model.tags.split(',')) == {'Element', 'Container', 'Database'}
    assert container.tags == {'Element', 'Container', 'Database'}

    assert set(component.model.tags.split(',')) == {'Element', 'Component', 'Views'}
    assert component.tags == {'Element', 'Component', 'Views'}

def test_tags_on_relationship_using_uses() -> Optional[None]:

    u = Person('u')
    s = SoftwareSystem('s')
    r = u.uses(s, 'Uses', tags={'Human-Computer Interaction'})

    assert set(r.model.tags.split(',')) == {'Relationship', 'Human-Computer Interaction'}
    assert r.tags == {'Relationship', 'Human-Computer Interaction'}

def test_tags_on_relationship_using_with() -> Optional[None]:


    u = Person('u')
    s = SoftwareSystem('s')
    r = (u >> "Uses" >> s | With(tags={'Human-Computer Interaction'}))

    assert set(r.model.tags.split(',')) == {'Relationship', 'Human-Computer Interaction'}
    assert r.tags == {'Relationship', 'Human-Computer Interaction'}

def test_source_destinations_in_dsl_elements() -> Optional[None]:

    with Workspace('w', implied_relationships=True) as w:
        u = Person('u')
        s = SoftwareSystem('s')
        with s:
            webapp = Container('webapp')
            with webapp:
                Component('database layer')
                Component('API layer')
                Component('UI layer')

                webapp.ui_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer
                webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.database_layer
            Container('database')

            s.webapp >> "Uses" >> s.database | With(
                tags={
                    'api'
                },
                properties={
                    'url': 'https://example.com/api'
                }
            )
        u >> "Uses" >> s.database | With(
            tags={"5g-network"},
        )

    assert isinstance(w.u, Person)
    assert isinstance(w.s, SoftwareSystem)

    assert len(w.u.sources) == 0

    assert len(w.s.sources) == 1
    assert {w.u.model.id}.issubset({src.model.id for src in w.s.sources})

    assert len(w.u.destinations) == 2
    assert {w.s.model.id, w.s.database.model.id}.issubset({dst.model.id for dst in w.u.destinations})

    assert len(w.s.destinations) == 0

    assert len(w.s.webapp.sources) == 0

    assert len(w.s.database.sources) == 2
    assert {w.u.model.id, w.s.webapp.model.id}.issubset({dst.model.id for dst in w.s.database.sources})

def test_accessing_typed_dynamic_attributes() -> Optional[None]:

    with Workspace('w') as w:
        u = Person('u')
        s = SoftwareSystem('s')
        with s:
            webapp = Container('webapp')
            with webapp:
                Component('database layer')
                Component('API layer')
                Component('UI layer')

                webapp.ui_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer
                webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.database_layer
            Container('database')

            s.webapp >> "Uses" >> s.database
        u >> "Runs SQL queries" >> s.database

    assert 'Person' in w.person().u.tags
    assert 'Software System' in w.software_system().s.tags
    assert 'Container' in w.software_system().s.container().webapp.tags
    assert 'Component' in w.software_system().s.container().webapp.component().ui_layer.tags

def test_dsl_where_with_workspace() -> Optional[None]:

    print("test: test_dsl_where_with_workspace")

    with Workspace('w') as w:
        u = Person('User')
        s = SoftwareSystem('Software')
        with s:
            ui = Container('UI')
            db = Container('Database')
            ui >> "Reads from and writes to" >> db
        u >> "Uses" >> s

    assert len(w.children) == 2
    assert w.software_system().software.ui.model.relationships[0].description == "Reads from and writes to"
    assert w.person().user.model.relationships[0].description == "Uses"

def test_one_source_to_many_destinations_relationships_for_person() -> Optional[None]:

    w = Workspace("w")

    person = Person("User")
    s1 = SoftwareSystem("Software 1")
    s2 = SoftwareSystem("Software 1")

    relationships = person >> [
        desc("Uses") >> s1,
        desc("Gets data", "SQL") >> s2
    ]

    assert len(relationships) == 2
    assert relationships[0].model.description == "Uses"

    assert relationships[1].model.description == "Gets data"
    assert relationships[1].model.technology == "SQL"

def test_one_source_to_many_destinations_relationships_in_where_method() -> Optional[None]:

    with Workspace('w') as w:
        Person('Personal Banking Customer')
        Person('Customer Service Staff')
        Person('Back Office Staff')
        SoftwareSystem('ATM')
        SoftwareSystem('Internet Banking System')
        SoftwareSystem('Email System')
        SoftwareSystem('Mainframe Banking System')
        w.person().personal_banking_customer >> [
            desc("Withdraws cash using") >> w.software_system().atm,
            desc("Views account balance, and makes payments using") >> w.software_system().internet_banking_system,
            desc("Ask questions to") >> w.person().customer_service_staff,
        ]
        w.person().customer_service_staff >> "Uses" >> w.software_system().mainframe_banking_system
        w.person().back_office_staff >> "Uses" >> w.software_system().mainframe_banking_system
        w.software_system().atm >> "Uses" >> w.software_system().mainframe_banking_system
        w.software_system().email_system >> "Sends e-mail to" >> w.person().personal_banking_customer
        w.software_system().internet_banking_system >> [
            desc("Gets account information from, and makes payments using") >> w.software_system().mainframe_banking_system,
            desc("Sends e-mail using") >> w.software_system().email_system,
        ]

    relationships = w.person().personal_banking_customer.model.relationships
    assert len(relationships) == 3
    assert relationships[0].description == "Withdraws cash using"
    assert relationships[0].destinationId == w.software_system().atm.model.id
    assert relationships[1].description == "Views account balance, and makes payments using"
    assert relationships[1].destinationId == w.software_system().internet_banking_system.model.id
    assert relationships[2].description == "Ask questions to"
    assert relationships[2].destinationId == w.person().customer_service_staff.model.id

def test_one_to_one_relationship_creation_with_desc() -> Optional[None]:

    with Workspace('w') as w:
        u = Person('User')
        s1 = SoftwareSystem('Software 1')
        s2 = SoftwareSystem('Software 2')
        with s1:
            c1 = Container('Container 1')
            c2 = Container('Container 2')
            c1 >> desc("Uses", "HTTP") >> c2
        with s2:
            c3 = Container('Container 3')
            with c3:
                Component('Component 1')
                Component('Component 2')
                c3.component_1 >> desc("Uses", "TCP") >> c3.component_2

        u >> desc("Uses", "CLI") >> s1
        s1 >> desc("Uses", "SSH") >> s2

    assert w.person().user.model.relationships[0].description == "Uses"
    assert w.software_system().software_1.model.relationships[0].technology == "SSH"
    assert w.software_system().software_1.container().container_1.model.relationships[0].technology == "HTTP"
    assert w.software_system().software_2.container().container_3.component_1.model.relationships[0].technology == "TCP"

def test_one_to_many_relationship_with_tags() -> Optional[None]:

    with Workspace("w") as w:
        u = Person("User")
        s1 = SoftwareSystem("Software 1")
        s2 = SoftwareSystem("Software 2")
        u >> [
            desc("Uses") >> s1 | With(tags={"CLI"}),
            desc("Uses") >> s2 | With(tags={"UI"}),
        ]

    relationships = w.person().user.model.relationships
    assert len(relationships) == 2
    assert set(relationships[0].tags.split(',')) == {"CLI", "Relationship"}
    assert set(relationships[1].tags.split(',')) == {"UI", "Relationship"}

def test_access_relationships_from_dslelements() -> Optional[None]:
    with Workspace("w") as w:
        u = Person("User")
        with SoftwareSystem("Software 1") as s1:
            with Container("Container 1") as c1:
                Component("Component 1")
                Component("Component 2")
                c1.component_1 >> desc("Uses", "TCP") >> c1.component_2
            pass
        with SoftwareSystem("Software 2") as s2:
            with Container("Container 2") as c2:
                Component("Component 3")
                Component("Component 4")
                c2.component_3 >> desc("Uses", "HTTP") >> c2.component_4
        u >> [
            desc("Uses") >> s1,
            desc("Uses") >> s2,
        ]

        s1 >> desc("Uses") >> s2

    assert len(u.relationships) == 2
    assert len(s1.relationships) == 1
    assert len(s2.relationships) == 0
    assert len(c1.relationships) == 0
    assert len(c1.component_1.relationships) == 1
    assert len(c1.component_2.relationships) == 0
    assert len(c2.relationships) == 0
    assert len(c2.component_3.relationships) == 1
    assert len(c2.component_4.relationships) == 0

def test_dynamic_attribute_access_with_labels() -> Optional[None]:

    with Workspace("w") as w:
        u = Person("Long Long Name").labeled('u')
        b = SoftwareSystem("Boring Software").labeled('b')
        t = SoftwareSystem("Tedious Software").labeled('t')
        with t:
            web = Container('Web User Interface').labeled('web')
            with web:
                Component('Database Layer').labeled('db')
                Component('API Layer').labeled('api')
                Component('UI Layer').labeled('ui')
            Container('SQL Server Database').labeled('mssql')

        u >> [
            desc("Uses", "CLI") >> b,
            desc("Uses", "UI") >> t,
        ]

    assert w.person().u.model.name == "Long Long Name"
    assert w.software_system().b.model.name == "Boring Software"
    assert w.software_system().t.web.model.name == "Web User Interface"
    assert w.software_system().t.container().web.db.model.name == "Database Layer"
    assert w.software_system().t.container().web.api.model.name == "API Layer"
    assert w.software_system().t.container().web.ui.model.name == "UI Layer"
    assert w.software_system().t.container().mssql.model.name == "SQL Server Database"

def test_grouping() -> Optional[None]:

    with Workspace("w") as w:
        with Group("Company 1") as g1:
            with SoftwareSystem("A") as a:
                with Container("a1"):
                    pass
                with Container("a2"):
                    pass
        with Group("Company 2") as g2:
            with SoftwareSystem("B") as b:
                with Container("b1"):
                    pass
                with Container("b2") as b2:
                    Component("c1")

        with SoftwareSystem("C") as c:
            pass

        a >> "Uses" >> b
        a.a1 >> "Uses" >> b.b1
        a >> "Uses" >> c

    a = w.software_system().a
    b = w.software_system().b

    assert a.model.group == "Company 1"
    assert b.model.group == "Company 2"
    assert a.container().a1.model.group == "Company 1"
    assert a.container().a2.model.group == "Company 1"
    assert b.container().b1.model.group == "Company 2"
    assert b.container().b2.model.group == "Company 2"
    assert a.model.relationships[0].destinationId == b.model.id
    assert a.container().a1.model.relationships[0].destinationId == b.container().b1.model.id
    assert b.container().b2.component().c1.model.group == "Company 2"
    assert a.model.relationships[1].destinationId == w.software_system().c.model.id

@pytest.mark.parametrize("group_separator", [".", "/"])
def test_nested_grouping(group_separator: str) -> Optional[None]:
    with Workspace("w", group_separator=group_separator) as w:
        with Group("Company 1") as comp1:
            with Group("Department 1") as dept1:
                with SoftwareSystem("A") as a:
                    with Container("a1"):
                        pass
                    with Container("a2"):
                        pass
            with Group("Department 2") as dept2:
                with SoftwareSystem("B") as b:
                    with Container("b1"):
                        pass
                    with Container("b2") as b2:
                        Component("c1")

            a >> b

    assert a.model.group == f"Company 1{group_separator}Department 1"
    assert b.model.group == f"Company 1{group_separator}Department 2"
    assert a.a1.model.group == f"Company 1{group_separator}Department 1"
    assert a.a2.model.group == f"Company 1{group_separator}Department 1"
    assert b.b2.c1.model.group == f"Company 1{group_separator}Department 2"
    assert a.model.relationships[0].destinationId == b.model.id
    assert a.model.relationships[0].sourceId == a.model.id

@pytest.mark.parametrize("group_separator", [".", "/"])
def test_group_name_contain_separator_raise(group_separator: str) -> Optional[None]:

    with pytest.raises(ValueError):
        with Workspace("w", group_separator=group_separator) as w:
            with Group(f"Company{group_separator}1") as comp1:
                with Group("Department 1") as dept1:
                    with SoftwareSystem("A") as a:
                        with Container("a1"):
                            pass
                        with Container("a2"):
                            pass
                with Group(f"Department{group_separator}2") as dept2:
                    with SoftwareSystem("B") as b:
                        with Container("b1"):
                            pass
                        with Container("b2") as b2:
                            Component("c1")

@pytest.mark.parametrize("group_separator", [".", "/"])
def test_group_separator_assigned_to_model_property(group_separator: str) -> Optional[None]:

    with Workspace("w", group_separator=group_separator) as w:
        with Group("Company 1") as comp1:
            a = SoftwareSystem("A")

    assert a.model.group == f"Company 1"
    assert w.model.model.properties['structurizr.groupSeparator'] == group_separator

@pytest.mark.parametrize("group_separator", [".", "/", "//"])
def test_group_separator_must_be_a_single_character(group_separator: str) -> Optional[None]:
    if len(group_separator) > 1:
        with pytest.raises(ValueError):
            with Workspace("w", group_separator=group_separator) as w:
                with Group("Company 1") as comp1:
                    with Group("Department 1") as dept1:
                        a = SoftwareSystem("A")
                    with Group("Department 2") as dept2:
                        b = SoftwareSystem("B")
                    a >> b

def test_dsl_relationship_without_desc() -> Optional[None]:

    with Workspace("w") as w:
        u = Person("User")
        s1 = SoftwareSystem("Software 1")
        s2 = SoftwareSystem("Software 2")
        u >> s1

    assert w.person().user.model.relationships[0].description == ""
    assert w.person().user.model.relationships[0].technology == ""
    assert w.person().user.model.relationships[0].destinationId == w.software_system().software_1.model.id

def test_dsl_relationship_without_desc_multiple_dest() -> Optional[None]:

    with Workspace("w") as w:
        u = Person("User")
        s1 = SoftwareSystem("Software 1")
        s2 = SoftwareSystem("Software 2")
        s3 = SoftwareSystem("Software 3")
        u >> [
            s1,
            desc("browses") >> s2,
            s3,
        ]

    assert len(w.person().user.model.relationships) == 3
    assert not w.person().user.model.relationships[0].description
    assert not w.person().user.model.relationships[0].technology
    assert w.person().user.model.relationships[1].description == "browses"
    assert not w.person().user.model.relationships[1].technology
    assert not w.person().user.model.relationships[2].description
    assert not w.person().user.model.relationships[2].technology
    assert w.person().user.model.relationships[0].destinationId == w.software_system().software_1.model.id
    assert w.person().user.model.relationships[1].destinationId == w.software_system().software_2.model.id
    assert w.person().user.model.relationships[2].destinationId == w.software_system().software_3.model.id

def test_json_sink() -> Optional[None]:

    with Workspace("w") as w:
        u = Person("User")
        s1 = SoftwareSystem("Software 1")
        s2 = SoftwareSystem("Software 2")
        u >> [
            desc("Uses") >> s1,
            desc("Uses") >> s2,
        ]

        SystemContextView(
            key="ss_01",
            title="System Context",
            description="A simple system context view for software 1",
            software_system_selector=lambda w: w.software_system().software_1,
        )

        SystemContextView(
            key="ss_02",
            title="System Context",
            description="A simple system context view for software 2",
            software_system_selector=lambda w: w.software_system().software_2,
        )

        w.to_json(path="test.json")

    with open("test.json", "r") as f:
        data = f.read()

    assert data

    import os
    os.remove("test.json")

def test_json_sink_empty_views() -> Optional[None]:

    # No views defined here.

    with Workspace("w") as w:
        u = Person("User")
        s1 = SoftwareSystem("Software 1")
        s2 = SoftwareSystem("Software 2")
        u >> [
            desc("Uses") >> s1,
            desc("Uses") >> s2,
        ]

        w.to_json(path="test.json")

    with open("test.json", "r") as f:
        data = f.read()

    assert data

    import os
    os.remove("test.json")