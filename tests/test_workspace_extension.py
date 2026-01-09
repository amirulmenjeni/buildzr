"""Tests for workspace extension functionality."""

import json
import os
import tempfile
import pytest
from typing import Optional, Generator

from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    Component,
)
from buildzr.dsl.factory import GenerateId
from buildzr.loaders import JsonLoader


@pytest.fixture
def parent_workspace_json() -> str:
    """Create a temporary parent workspace.json file for testing."""
    parent_data = {
        "id": 0,
        "name": "Parent Workspace",
        "description": "A parent workspace for testing",
        "model": {
            "softwareSystems": [
                {
                    "id": "1",
                    "name": "System A",
                    "description": "First system",
                    "tags": "Element,Software System",
                    "containers": [
                        {
                            "id": "3",
                            "name": "Container X",
                            "description": "A container in System A",
                            "tags": "Element,Container",
                            "components": [
                                {
                                    "id": "5",
                                    "name": "Component Y",
                                    "description": "A component",
                                    "tags": "Element,Component"
                                }
                            ]
                        }
                    ],
                    "relationships": [
                        {
                            "id": "4",
                            "description": "Uses",
                            "sourceId": "1",
                            "destinationId": "2",
                            "tags": "Relationship"
                        }
                    ]
                },
                {
                    "id": "2",
                    "name": "System B",
                    "description": "Second system",
                    "tags": "Element,Software System"
                }
            ],
            "people": [
                {
                    "id": "6",
                    "name": "User",
                    "description": "A user",
                    "tags": "Element,Person"
                }
            ]
        }
    }

    with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
        json.dump(parent_data, f)
        return f.name


@pytest.fixture(autouse=True)
def reset_id_counter() -> Generator[None, None, None]:
    """Reset ID counter before each test."""
    GenerateId.reset()
    yield
    GenerateId.reset()


class TestJsonLoader:
    """Tests for JsonLoader."""

    def test_load_from_file(self, parent_workspace_json: str) -> None:

        """Test loading workspace from a local file."""
        loader = JsonLoader()
        workspace = loader.load(parent_workspace_json)

        assert workspace.name == "Parent Workspace"
        assert workspace.model is not None
        assert len(workspace.model.softwareSystems) == 2
        assert workspace.model.softwareSystems[0].name == "System A"
        assert workspace.model.softwareSystems[1].name == "System B"

    def test_get_max_element_id(self, parent_workspace_json: str) -> None:
        """Test finding the maximum element ID in a workspace."""
        loader = JsonLoader()
        workspace = loader.load(parent_workspace_json)
        max_id = loader.get_max_element_id(workspace)

        # Maximum ID in parent is 6 (User)
        assert max_id == 6


class TestWorkspaceExtension:
    """Tests for Workspace with extend parameter."""

    def test_extend_workspace_basic(self, parent_workspace_json: str) -> None:
        """Test basic workspace extension."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            assert isinstance(w, Workspace)
            # Parent elements should be accessible directly on workspace
            system_a = w.software_system().system_a
            assert system_a.model.id == "1"
            assert system_a.model.name == "System A"

    def test_access_parent_software_systems(self, parent_workspace_json: str) -> None:
        """Test accessing software systems from parent workspace."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            system_b = w.software_system().system_b

            assert isinstance(system_a, SoftwareSystem)
            assert isinstance(system_b, SoftwareSystem)
            assert system_a.model.name == "System A"
            assert system_b.model.name == "System B"

    def test_access_parent_containers(self, parent_workspace_json: str) -> None:
        """Test accessing containers from parent software system."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            container_x = system_a.container().container_x

            assert isinstance(container_x, Container)
            assert container_x.model.name == "Container X"

    def test_access_parent_components(self, parent_workspace_json: str) -> None:
        """Test accessing components from parent container."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            container_x = system_a.container().container_x
            component_y = container_x.component().component_y

            assert isinstance(component_y, Component)
            assert component_y.model.name == "Component Y"

    def test_access_parent_people(self, parent_workspace_json: str) -> None:
        """Test accessing people from parent workspace."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            user = w.person().user

            assert isinstance(user, Person)
            assert user.model.name == "User"

    def test_new_element_ids_dont_collide(self, parent_workspace_json: str) -> None:
        """Test that new elements have IDs that don't collide with parent."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            # Parent max ID is 6, so new elements should start at 7
            new_sys = SoftwareSystem("New System")
            assert int(new_sys.model.id) > 6

    def test_relationship_to_parent_element(self, parent_workspace_json: str) -> None:
        """Test creating relationships to parent elements."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_b = w.software_system().system_b
            new_sys = SoftwareSystem("New System")
            rel = new_sys >> "Calls" >> system_b

            assert rel.model.sourceId == new_sys.model.id
            assert rel.model.destinationId == "2"  # System B's ID

    def test_add_container_to_parent_system(self, parent_workspace_json: str) -> None:
        """Test adding a new container to a parent software system."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            with system_a:
                new_container = Container("New Container")

            # Container should be added to System A's containers
            assert any(
                c.name == "New Container"
                for c in system_a.model.containers
            )

    def test_add_component_to_parent_container(self, parent_workspace_json: str) -> None:
        """Test adding a new component to a parent container."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            container_x = system_a.container().container_x
            with container_x:
                new_component = Component("New Component")

            # Component should be added to Container X's components
            assert any(
                c.name == "New Component"
                for c in container_x.model.components
            )

    def test_export_merges_workspaces(self, parent_workspace_json: str) -> None:
        """Test that to_json merges parent and child workspaces."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_path = f.name

        try:
            with Workspace("Child", extend=parent_workspace_json) as w:
                system_b = w.software_system().system_b
                new_sys = SoftwareSystem("New System")
                new_sys >> "Uses" >> system_b
                w.save(path=output_path)

            with open(output_path, 'r') as f:
                output = json.load(f)

            # Should contain both parent and child systems
            system_names = [ss['name'] for ss in output['model']['softwareSystems']]
            assert "System A" in system_names  # From parent
            assert "System B" in system_names  # From parent
            assert "New System" in system_names  # From child

            # Child workspace name should be used
            assert output['name'] == "Child"
        finally:
            os.unlink(output_path)

    def test_relationship_in_merged_output(self, parent_workspace_json: str) -> None:

        """Test that relationships to parent elements appear in merged output."""
        with tempfile.NamedTemporaryFile(mode='w', suffix='.json', delete=False) as f:
            output_path = f.name

        try:
            with Workspace("Child", extend=parent_workspace_json) as w:
                system_b = w.software_system().system_b
                new_sys = SoftwareSystem("New System")
                new_sys >> "Calls API of" >> system_b
                w.save(path=output_path)

            with open(output_path, 'r') as f:
                output = json.load(f)

            # Find New System in output
            new_sys_data = next(
                ss for ss in output['model']['softwareSystems']
                if ss['name'] == "New System"
            )

            # Check relationship exists
            assert len(new_sys_data['relationships']) == 1
            rel = new_sys_data['relationships'][0]
            assert rel['description'] == "Calls API of"
            assert rel['destinationId'] == "2"  # System B
        finally:
            os.unlink(output_path)


class TestParentElementRelationships:
    """Tests for relationships involving parent elements."""

    def test_parent_element_as_source(self, parent_workspace_json: str) -> None:
        """Test creating relationship where parent element is the source."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            new_sys = SoftwareSystem("New System")

            # Parent element as source
            rel = system_a >> "Depends on" >> new_sys

            assert rel.model.sourceId == "1"  # System A
            assert rel.model.destinationId == new_sys.model.id

    def test_parent_to_parent_relationship(self, parent_workspace_json: str) -> None:
        """Test creating relationship between two parent elements."""
        with Workspace("Child", extend=parent_workspace_json) as w:
            system_a = w.software_system().system_a
            system_b = w.software_system().system_b

            # Create relationship between parent elements
            # (This adds a new relationship in the child workspace)
            rel = system_b >> "Also uses" >> system_a

            assert rel.model.sourceId == "2"  # System B
            assert rel.model.destinationId == "1"  # System A
