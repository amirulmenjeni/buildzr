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

    person >> "uses" >> software_system

    assert person.relationships is not None
    assert len(person.relationships) == 1