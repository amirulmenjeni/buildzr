from dataclasses import dataclass
import pytest
from buildzr.dsl import Workspace, SoftwareSystem, Person

@dataclass
class DslHolder:
    """A `dataclass` for us to hold the objects created using the DSL.

This helps by allowing us to create the workspace and other DSL objects in the
fixture once to be reused across multiple tests.
"""

    workspace: Workspace
    software_system: SoftwareSystem
    person: Person

@pytest.fixture
def dsl() -> DslHolder:

    workspace = Workspace("My Workspace", "A happy place")
    software_system = SoftwareSystem("My Software System")
    person = Person("Super user")

    return DslHolder(
        workspace=workspace,
        software_system=software_system,
        person=person,
    )

def test_element_ids(dsl: DslHolder):

    assert dsl.workspace.id is not None
    assert dsl.person.id is not None
    assert dsl.software_system.id is not None

def test_workspace_has_configuration(dsl: DslHolder):

    assert dsl.workspace.configuration is not None

def test_relationship_dsl(dsl: DslHolder):

    dsl.person >> ("uses", "cli") >> dsl.software_system

    assert dsl.person.relationships is not None
    assert len(dsl.person.relationships) == 1
    assert dsl.person.relationships[0].id is not None
    assert dsl.person.relationships[0].description == "uses"
    assert dsl.person.relationships[0].technology == "cli"

def test_workspace_model_inclusion_dsl(dsl: DslHolder):

    dsl.workspace.contains([dsl.person, dsl.software_system])

    assert any(dsl.workspace.model.people)
    assert any(dsl.workspace.model.softwareSystems)