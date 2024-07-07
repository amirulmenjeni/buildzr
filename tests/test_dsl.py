import pytest
from buildzr.dsl import Workspace, SoftwareSystem, Person

def test_element_ids():

    workspace = Workspace("My Workspace", "A happy place")
    person = Person("Super user")
    software_system = SoftwareSystem("My Software System")

    assert workspace.id is not None
    assert person.id is not None
    assert software_system.id is not None

def test_workspace_has_configuration():

    workspace = Workspace("My Workspace", "A happy place")

    assert workspace.configuration is not None

def test_relationship_dsl():

    workspace = Workspace("My Workspace", "A happy place")
    person = Person("Super user")
    software_system = SoftwareSystem("My Software System")
    another_software_system = SoftwareSystem("Another Software System")

    person >> ("uses", "cli") >> software_system

    assert person.relationships is not None
    assert len(person.relationships) == 1
    assert person.relationships[0].id is not None
    assert person.relationships[0].description == "uses"
    assert person.relationships[0].technology == "cli"

def test_workspace_model_inclusion_dsl():

    workspace = Workspace("My Workspace", "A happy place")
    person = Person("Super user")
    software_system = SoftwareSystem("My Software System")

    workspace.contains([person, software_system])

    assert any(workspace.model.people)
    assert any(workspace.model.softwareSystems)