"""Tests for PlantUML export functionality."""

import pytest
import tempfile
import os
from pathlib import Path
from typing import Any

from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    ContainerView,
    SystemContextView,
    ComponentView,
)
from buildzr.sinks.plantuml_sink import PlantUmlSink, PlantUmlSinkConfig


class TestPlantUmlSink:
    """Test suite for PlantUML export functionality."""

    @pytest.fixture
    def sample_workspace(self) -> Any:
        """Create a sample workspace for testing."""
        with Workspace('Test Workspace', 'A test workspace for PlantUML export') as w:
            user = Person('User', 'A user of the system')

            with SoftwareSystem('BookStore', 'An online bookstore system') as bookstore:
                web_app = Container('Web Application', 'Delivers content to users', 'Python/Flask')
                database = Container('Database', 'Stores book information', 'PostgreSQL')

            # Relationships
            user >> "Browses and makes purchases using" >> web_app
            web_app >> "Reads from and writes to" >> database

            # Views
            SystemContextView(
                lambda w: w.software_system().bookstore,
                key='system-context',
                description='System context for the bookstore'
            )

            ContainerView(
                lambda w: w.software_system().bookstore,
                key='container-view',
                description='Container diagram'
            )

        return w.model

    def test_plantuml_export_basic(self, sample_workspace: Any) -> None:
        """Test basic PlantUML export to .puml files."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = PlantUmlSinkConfig(path=temp_dir, format='puml')
            sink = PlantUmlSink()

            sink.write(sample_workspace, config)

            # Check that files were created
            puml_files = list(Path(temp_dir).glob("*.puml"))
            assert len(puml_files) == 2, f"Expected 2 .puml files, got {len(puml_files)}"

            # Check file names
            file_names = {f.name for f in puml_files}
            assert 'system-context.puml' in file_names
            assert 'container-view.puml' in file_names

            # Verify file contents start with @startuml
            for puml_file in puml_files:
                content = puml_file.read_text()
                assert content.startswith('@startuml'), f"{puml_file.name} doesn't start with @startuml"
                assert '@enduml' in content, f"{puml_file.name} doesn't contain @enduml"

    def test_plantuml_export_content(self, sample_workspace: Any) -> None:
        """Test that exported PlantUML files contain expected elements."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = PlantUmlSinkConfig(path=temp_dir, format='puml')
            sink = PlantUmlSink()

            sink.write(sample_workspace, config)

            # Read system context view
            context_file = Path(temp_dir) / 'system-context.puml'
            assert context_file.exists()

            content = context_file.read_text()

            # Check for expected elements in system context view
            # Note: The Java exporter includes elements based on view configuration
            # The system should be present
            assert 'BookStore' in content

            # Read container view
            container_file = Path(temp_dir) / 'container-view.puml'
            assert container_file.exists()

            content = container_file.read_text()

            # Check for container names (containers should be in the container view)
            assert 'Web Application' in content or 'WebApplication' in content
            assert 'Database' in content

    def test_plantuml_export_empty_workspace(self) -> None:
        """Test export of an empty workspace."""
        with Workspace('Empty', 'Empty workspace') as w:
            pass

        with tempfile.TemporaryDirectory() as temp_dir:
            config = PlantUmlSinkConfig(path=temp_dir, format='puml')
            sink = PlantUmlSink()

            sink.write(w.model, config)

            # Should complete without error even with no views
            puml_files = list(Path(temp_dir).glob("*.puml"))
            assert len(puml_files) == 0  # No views, no files

    def test_plantuml_export_creates_directory(self, sample_workspace: Any) -> None:
        """Test that export creates output directory if it doesn't exist."""
        with tempfile.TemporaryDirectory() as temp_root:
            output_dir = os.path.join(temp_root, 'nested', 'output')

            config = PlantUmlSinkConfig(path=output_dir, format='puml')
            sink = PlantUmlSink()

            sink.write(sample_workspace, config)

            # Directory should be created
            assert os.path.exists(output_dir)
            assert os.path.isdir(output_dir)

            # Files should be created
            puml_files = list(Path(output_dir).glob("*.puml"))
            assert len(puml_files) > 0

    def test_plantuml_export_default_config(self, sample_workspace: Any) -> None:
        """Test export with default configuration."""
        # Save current directory
        original_dir = os.getcwd()

        with tempfile.TemporaryDirectory() as temp_dir:
            try:
                # Change to temp directory
                os.chdir(temp_dir)

                sink = PlantUmlSink()
                sink.write(sample_workspace)  # No config = default to current dir

                # Files should be created in current directory
                puml_files = list(Path(temp_dir).glob("*.puml"))
                assert len(puml_files) > 0

            finally:
                # Restore original directory
                os.chdir(original_dir)

    def test_plantuml_export_svg_format(self, sample_workspace: Any) -> None:
        """Test export to SVG format (requires PlantUML)."""
        with tempfile.TemporaryDirectory() as temp_dir:
            config = PlantUmlSinkConfig(path=temp_dir, format='svg')
            sink = PlantUmlSink()

            sink.write(sample_workspace, config)

            # Should create both .puml and .svg files
            puml_files = list(Path(temp_dir).glob("*.puml"))
            svg_files = list(Path(temp_dir).glob("*.svg"))

            assert len(puml_files) > 0
            assert len(svg_files) > 0
            assert len(puml_files) == len(svg_files)

    def test_workspace_save_plantuml_method(self) -> None:
        """Test the Workspace.save(format='plantuml') method."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create workspace using DSL
            with Workspace('Test Workspace', 'Test workspace for save()') as w:
                user = Person('User', 'A user of the system')

                with SoftwareSystem('TestSystem', 'A test system') as test_system:
                    app = Container('Application', 'The main app', 'Python')

                user >> "Uses" >> app

                SystemContextView(
                    test_system,
                    key='context',
                    description='System context'
                )

            # Use the save() method
            w.save(format='plantuml', path=temp_dir)

            # Verify output
            puml_files = list(Path(temp_dir).glob("*.puml"))
            assert len(puml_files) == 1
            assert puml_files[0].name == 'context.puml'

            content = puml_files[0].read_text()
            assert '@startuml' in content
            assert '@enduml' in content
