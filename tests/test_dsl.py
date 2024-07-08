from dataclasses import dataclass, fields
import inspect
import pytest
import importlib
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

def test_docstrings(dsl: DslHolder):
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

def test_element_ids(dsl: DslHolder):

    assert dsl.workspace._m.id is not None
    assert dsl.person._m.id is not None
    assert dsl.software_system._m.id is not None

def test_workspace_has_configuration(dsl: DslHolder):

    assert dsl.workspace._m.configuration is not None

def test_relationship_dsl(dsl: DslHolder):

    dsl.person >> ("uses", "cli") >> dsl.software_system

    assert dsl.person._m.relationships is not None
    assert len(dsl.person._m.relationships) == 1
    assert dsl.person._m.relationships[0].id is not None
    assert dsl.person._m.relationships[0].description == "uses"
    assert dsl.person._m.relationships[0].technology == "cli"

def test_workspace_model_inclusion_dsl(dsl: DslHolder):

    dsl.workspace.contains([dsl.person, dsl.software_system])

    assert any(dsl.workspace._m.model.people)
    assert any(dsl.workspace._m.model.softwareSystems)