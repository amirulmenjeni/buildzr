from dataclasses import dataclass, fields
import inspect
import pytest
import importlib
from typing import Optional
from buildzr.dsl import Workspace, SoftwareSystem, Person, Container, DslRelationship, With
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

@pytest.fixture
def dsl() -> DslHolder:

    workspace = Workspace("My Workspace", "A happy place")
    software_system = SoftwareSystem("My Software System")
    person = Person("Super user")
    container = Container("My container")

    return DslHolder(
        workspace=workspace,
        software_system=software_system,
        person=person,
        container=container,
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

def test_workspace_has_configuration(dsl: DslHolder) -> Optional[None]:

    assert dsl.workspace._m.configuration is not None

def test_relationship_dsl(dsl: DslHolder) -> Optional[None]:

    dsl.person >> ("uses", "cli") >> dsl.software_system

    assert dsl.person._m.relationships is not None
    assert len(dsl.person._m.relationships) == 1
    assert dsl.person._m.relationships[0].id is not None
    assert dsl.person._m.relationships[0].description == "uses"
    assert dsl.person._m.relationships[0].technology == "cli"

def test_relationship_with_extra_info_using_with(dsl: DslHolder) -> Optional[None]:

    dsl.person >> ("uses", "cli") >> dsl.software_system | With(
        tags=["bash", "terminal"],
        properties={
            "authentication": "ssh",
        },
        url="http://example.com/info/relationship-user-uses-cli",
    )

    assert "bash" in dsl.person.model.relationships[0].tags
    assert "terminal" in dsl.person.model.relationships[0].tags
    assert "authentication" in dsl.person.model.relationships[0].properties.keys()
    assert "http://example.com/info/relationship-user-uses-cli" == dsl.person.model.relationships[0].url

def test_relationship_with_extra_info_using_has(dsl: DslHolder) -> Optional[None]:

    (dsl.person >> ("uses", "cli") >> dsl.software_system).has(
        tags=["bash", "terminal"],
        properties={
            "authentication": "ssh",
        },
        url="http://example.com/info/relationship-user-uses-cli",
    )

    assert "bash" in dsl.person.model.relationships[0].tags
    assert "terminal" in dsl.person.model.relationships[0].tags
    assert "authentication" in dsl.person.model.relationships[0].properties.keys()
    assert "http://example.com/info/relationship-user-uses-cli" == dsl.person.model.relationships[0].url

def test_relationship_dont_work_with_workspace(dsl: DslHolder) -> Optional[None]:

    with pytest.raises(TypeError):
        dsl.workspace >> "uses" >> dsl.person #type: ignore[operator]

    with pytest.raises(TypeError):
        dsl.person >> "uses" >> dsl.workspace #type: ignore[operator]

    with pytest.raises(TypeError):
        dsl.workspace >> "uses" >> dsl.software_system #type: ignore[operator]

def test_workspace_model_inclusion_dsl(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.contains(dsl.person, dsl.software_system)

    assert any(dsl.workspace._m.model.people)
    assert any(dsl.workspace._m.model.softwareSystems)

def test_parenting(dsl: DslHolder) -> Optional[None]:

    dsl.workspace.contains(dsl.person, dsl.software_system)
    dsl.software_system.contains(dsl.container)

    assert dsl.person.parent.model.id == dsl.workspace.model.id
    assert dsl.software_system.parent.model.id == dsl.workspace.model.id
    assert dsl.container.parent.model.id == dsl.software_system.model.id

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
    w1.contains(u1, s1)

    w2 = Workspace("w")
    w2.model.id = 1
    u2 = Person("u")
    u2.model.id = "2"
    s2 = SoftwareSystem("s")
    s2.model.id = "3"
    w2.contains(u2, s2)
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

    dsl.workspace.contains(
        dsl.person,
        dsl.software_system,
    )

    relationship = dsl.person >> "Uses" >> dsl.software_system

    assert isinstance(relationship, DslRelationship)
    assert relationship.model.description == "Uses"
    assert relationship.model.destinationId == dsl.software_system.model.id

def test_fluent_workspace_definition() -> Optional[None]:

    w = Workspace("w")\
        .contains(
            Person("u"),
            SoftwareSystem("s")\
            .contains(
                Container("webapp"),
                Container("database")
            )\
            .where(lambda webapp, database: [
                webapp >> "Uses" >> database
            ])
        )\
        .where(lambda u, s: [
            u >> "Uses" >> s | With(
                tags=["5g-network"],
            )
        ])

    assert any(w.model.model.people)
    assert any(w.model.model.people[0].relationships)
    assert any(w.model.model.softwareSystems)
    assert any(w.model.model.softwareSystems[0].containers)
    assert any(w.model.model.softwareSystems[0].containers[0].relationships)