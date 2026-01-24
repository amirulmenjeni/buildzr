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

    def test_plantuml_export_implied_relationships(self) -> None:
        """Test that implied relationships are properly exported to PlantUML.

        When a Person has a relationship to a Container inside a SoftwareSystem,
        and the workspace has implied_relationships=True, the SystemContextView
        should show the implied relationship from Person to SoftwareSystem.
        """
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create workspace with implied relationships enabled
            with Workspace('Test Implied', implied_relationships=True) as w:
                user = Person('User')

                with SoftwareSystem('System') as system:
                    database = Container('Database')

                # Direct relationship: User -> Database (container)
                # This should imply: User -> System
                user >> "Uses" >> database

                # Create a SystemContextView - should show implied relationship
                SystemContextView(
                    system,
                    key='context',
                    description='System context with implied relationships'
                )

            # Export to PlantUML
            w.save(format='plantuml', path=temp_dir)

            # Read the generated file
            context_file = Path(temp_dir) / 'context.puml'
            assert context_file.exists(), "context.puml should be created"

            content = context_file.read_text()

            # Verify both elements are present
            assert 'User' in content, "User should be in the diagram"
            assert 'System' in content, "System should be in the diagram"

            # Verify the relationship is present
            # PlantUML C4 format uses Rel() for relationships
            assert 'Rel(' in content, (
                "Implied relationship from User to System should be rendered. "
                f"Content:\n{content}"
            )

    def test_filter_empty_sprite_tags(self) -> None:
        """Test that AddElementTag lines with empty sprites are filtered out."""
        sink = PlantUmlSink()

        puml_content = """@startuml
AddElementTag("WithIcon", $bgColor="#dddddd", $sprite="img:https://example.com/icon.png", $borderStyle="solid")
AddElementTag("EmptySprite", $bgColor="#dddddd", $sprite="", $borderStyle="solid")
AddElementTag("EmptySpriteAlt", $bgColor="#dddddd", $sprite='', $borderStyle="solid")
AddBoundaryTag("Boundary", $bgColor="#ffffff", $borderColor="#9a9a9a")
Person(User, "User")
@enduml"""

        filtered = sink._filter_empty_sprite_tags(puml_content)

        # Lines with icons should be preserved
        assert 'AddElementTag("WithIcon"' in filtered
        # Lines with empty sprites should be removed
        assert 'AddElementTag("EmptySprite"' not in filtered
        assert 'AddElementTag("EmptySpriteAlt"' not in filtered
        # AddBoundaryTag should be removed (no icons)
        assert 'AddBoundaryTag' not in filtered
        # Other content should be preserved
        assert 'Person(User' in filtered
        assert '@startuml' in filtered
        assert '@enduml' in filtered

    def test_clean_svg_legend(self) -> None:
        """Test that placeholder characters are removed from SVG content."""
        sink = PlantUmlSink()

        # SVG content with placeholder character (&#9647; = U+25AF)
        svg_content = b'<svg><text>&#9647;</text><text>Legend</text></svg>'

        cleaned = sink._clean_svg_legend(svg_content)

        # Placeholder should be removed
        assert b'&#9647;' not in cleaned
        # Other content preserved
        assert b'Legend' in cleaned
        assert b'<svg>' in cleaned

    def test_clean_svg_legend_unicode_literal(self) -> None:
        """Test that Unicode literal placeholder is also removed."""
        sink = PlantUmlSink()

        # SVG content with Unicode literal (▯)
        svg_content = '▯ Legend'.encode('utf-8')

        cleaned = sink._clean_svg_legend(svg_content)

        # Unicode literal should be removed
        assert '\u25af'.encode('utf-8') not in cleaned
        assert b'Legend' in cleaned

    def test_svg_export_no_placeholder_characters(self) -> None:
        """Test that SVG export removes placeholder characters via save()."""
        with tempfile.TemporaryDirectory() as temp_dir:
            # Create workspace with styled elements
            with Workspace('Test', 'Test workspace') as w:
                user = Person('User')
                with SoftwareSystem('System') as system:
                    container = Container('Container')
                user >> "Uses" >> container

                SystemContextView(system, key='context', description='Test context')

            # Export to SVG
            w.save(format='svg', path=temp_dir)

            # Check SVG files for placeholder characters
            svg_files = list(Path(temp_dir).glob("*.svg"))
            assert len(svg_files) > 0

            for svg_file in svg_files:
                content = svg_file.read_text()
                # No placeholder characters should be present
                assert '&#9647;' not in content, f"Found placeholder in {svg_file.name}"
                assert '\u25af' not in content, f"Found Unicode placeholder in {svg_file.name}"

    def test_to_svg_no_placeholder_characters(self) -> None:
        """Test that to_svg() removes placeholder characters (used by Jupyter)."""
        # Create workspace with styled elements
        with Workspace('Test', 'Test workspace') as w:
            user = Person('User')
            with SoftwareSystem('System') as system:
                container = Container('Container')
            user >> "Uses" >> container

            SystemContextView(system, key='context', description='Test context')

        # Get SVG via to_svg() method (used by Jupyter notebooks)
        svgs = w.to_svg()

        assert len(svgs) > 0
        for view_key, svg_content in svgs.items():
            # No placeholder characters should be present
            assert '&#9647;' not in svg_content, f"Found placeholder in {view_key}"
            assert '\u25af' not in svg_content, f"Found Unicode placeholder in {view_key}"
