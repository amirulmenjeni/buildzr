from buildzr.dsl import Workspace, SoftwareSystem, Person

def test_relationship_dsl():

    workspace = Workspace("My Workspace", "A happy place")
    person = Person("Super user")
    software_system = SoftwareSystem("My Software System")

    person >> "uses" >> software_system

    assert any(person.relationships)