"""Tests for Jupyter notebook display features and export API."""

import json
import os
import pytest
from pathlib import Path
from buildzr.dsl import Workspace, SoftwareSystem, Person, Container, SystemContextView


class TestJsonMethods:
    """Tests for to_dict(), to_json(), and _repr_json_()."""

    def test_to_dict_returns_dict(self) -> None:
        """to_dict() should return a JSON-serializable dictionary."""
        with Workspace("Test", "A test workspace") as w:
            person = Person("User")
            system = SoftwareSystem("System")
            person >> "uses" >> system

        result = w.to_dict()

        assert isinstance(result, dict)
        assert result["name"] == "Test"
        assert result["description"] == "A test workspace"
        assert "model" in result

    def test_to_dict_has_camelcase_keys(self) -> None:
        """to_dict() should return keys in camelCase format."""
        with Workspace("Test") as w:
            system = SoftwareSystem("My System")
            with system:
                Container("My Container")

        result = w.to_dict()

        # Check for camelCase keys (not snake_case)
        assert "softwareSystems" in result["model"]
        assert "deploymentNodes" not in result["model"] or result["model"]["deploymentNodes"] is not None

    def test_to_json_returns_string(self) -> None:
        """to_json() should return a valid JSON string."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json()

        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["name"] == "Test"

    def test_to_json_pretty_format(self) -> None:
        """to_json(pretty=True) should return indented JSON."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json(pretty=True)

        # Pretty formatted JSON should have newlines
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_to_json_compact_format(self) -> None:
        """to_json(pretty=False) should return compact JSON."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json(pretty=False)

        # Compact JSON should not have newlines (between keys)
        # Note: might have newlines in values, so just check for lack of indentation
        lines = result.split("\n")
        # In compact mode, should be single line or minimal lines
        assert len(lines) <= 2  # Allow for trailing newline

    def test_repr_json_returns_tuple(self) -> None:
        """_repr_json_() should return (data, metadata) tuple."""
        with Workspace("Test") as w:
            Person("User")

        result = w._repr_json_()

        assert isinstance(result, tuple)
        assert len(result) == 2
        data, metadata = result
        assert isinstance(data, dict)
        assert isinstance(metadata, dict)
        assert data["name"] == "Test"
        assert "expanded" in metadata

    def test_to_dict_includes_views(self) -> None:
        """to_dict() should include defined views."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.to_dict()

        assert "views" in result
        assert "systemContextViews" in result["views"]
        assert len(result["views"]["systemContextViews"]) == 1


class TestPlantUmlMethods:
    """Tests for to_plantuml() and to_svg()."""

    def test_to_plantuml_requires_jpype(self) -> None:
        """to_plantuml() should raise ImportError if jpype not installed."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        # This test assumes jpype IS installed in the test environment
        # If not, it would raise ImportError which is the expected behavior
        try:
            result = w.to_plantuml()
            # If we get here, jpype is installed
            assert isinstance(result, dict)
        except ImportError as e:
            # Expected if jpype not installed
            assert "jpype1" in str(e).lower() or "plantuml" in str(e).lower()

    def test_to_svg_requires_jpype(self) -> None:
        """to_svg() should raise ImportError if jpype not installed."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        try:
            result = w.to_svg()
            # If we get here, jpype is installed and rendering worked
            assert isinstance(result, dict)
            for key, svg in result.items():
                assert isinstance(svg, str)
                assert "<svg" in svg.lower() or "<?xml" in svg.lower()
        except ImportError as e:
            # Expected if jpype not installed
            assert "jpype1" in str(e).lower() or "plantuml" in str(e).lower()

    def test_repr_html_requires_plantuml(self) -> None:
        """_repr_html_() should raise ImportError if PlantUML not available."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        try:
            result = w._repr_html_()
            # If we get here, PlantUML is installed
            assert isinstance(result, str)
            assert "<div" in result or "<svg" in result.lower()
        except ImportError as e:
            # Expected if PlantUML not installed
            assert "plantuml" in str(e).lower()


class TestPlantUmlWithJpype:
    """Tests that run only if jpype is available."""

    @pytest.fixture
    def skip_if_no_jpype(self) -> None:
        """Skip test if jpype is not installed."""
        try:
            import jpype  # type: ignore
        except ImportError:
            pytest.skip("jpype1 not installed")

    def test_to_plantuml_returns_dict(self, skip_if_no_jpype: None) -> None:
        """to_plantuml() should return dict of view_key -> puml content."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.to_plantuml()

        assert isinstance(result, dict)
        assert "context" in result
        assert "@startuml" in result["context"]
        assert "@enduml" in result["context"]

    def test_to_plantuml_multiple_views(self, skip_if_no_jpype: None) -> None:
        """to_plantuml() should include all views."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            with system:
                container = Container("Container")

            from buildzr.dsl import SystemContextView, ContainerView
            SystemContextView(system, key="context", description="Context view")
            ContainerView(system, key="containers", description="Container view")

        result = w.to_plantuml()

        assert len(result) == 2
        assert "context" in result
        assert "containers" in result

    def test_to_svg_returns_svg_content(self, skip_if_no_jpype: None) -> None:
        """to_svg() should return dict of view_key -> SVG content."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.to_svg()

        assert isinstance(result, dict)
        assert "context" in result
        svg_content = result["context"]
        assert isinstance(svg_content, str)
        # SVG should contain svg tag
        assert "<svg" in svg_content.lower() or "<?xml" in svg_content

    def test_repr_html_contains_all_views(self, skip_if_no_jpype: None) -> None:
        """_repr_html_() should include all views as SVGs."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            with system:
                Container("Container")

            from buildzr.dsl import SystemContextView, ContainerView
            SystemContextView(system, key="context", description="Context view")
            ContainerView(system, key="containers", description="Container view")

        result = w._repr_html_()

        assert isinstance(result, str)
        # Should have headings for both views
        assert "context" in result
        assert "containers" in result
        # Should have SVG content
        assert "<svg" in result.lower() or "<?xml" in result

    def test_repr_html_empty_views(self, skip_if_no_jpype: None) -> None:
        """_repr_html_() should handle workspace with no views."""
        with Workspace("Test") as w:
            SoftwareSystem("System")
            # No views defined

        result = w._repr_html_()

        assert isinstance(result, str)
        assert "No views" in result


class TestSaveMethod:
    """Tests for the save() method."""

    def test_save_json_default_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """save() with default args creates JSON in cwd with workspace name."""
        monkeypatch.chdir(tmp_path)

        with Workspace("My Test Workspace") as w:
            Person("User")

        result = w.save()

        assert isinstance(result, str)
        assert result == str(tmp_path / "my_test_workspace.json")
        assert Path(result).exists()
        # Verify it's valid JSON
        content = Path(result).read_text()
        parsed = json.loads(content)
        assert parsed["name"] == "My Test Workspace"

    def test_save_json_custom_path(self, tmp_path: Path) -> None:
        """save() respects custom path for JSON."""
        with Workspace("Test") as w:
            Person("User")

        output_path = tmp_path / "custom" / "output.json"
        result = w.save(format='json', path=output_path, pretty=True)

        assert isinstance(result, str)
        assert Path(result).exists()
        content = Path(result).read_text()
        # Pretty formatted
        assert "\n" in content
        # Valid JSON
        parsed = json.loads(content)
        assert parsed["name"] == "Test"

    def test_save_json_creates_parent_dirs(self, tmp_path: Path) -> None:
        """save() creates parent directories if they don't exist."""
        with Workspace("Test") as w:
            Person("User")

        output_path = tmp_path / "deeply" / "nested" / "dir" / "workspace.json"
        result = w.save(path=output_path)

        assert isinstance(result, str)
        assert Path(result).exists()
        assert Path(result).parent.exists()

    def test_save_invalid_format_raises(self) -> None:
        """save() with invalid format raises ValueError."""
        with Workspace("Test") as w:
            Person("User")

        with pytest.raises(ValueError, match="Unsupported format"):
            w.save(format='invalid')  # type: ignore


class TestSaveMethodWithJpype:
    """Tests for save() with diagram formats (requires jpype)."""

    @pytest.fixture
    def skip_if_no_jpype(self) -> None:
        """Skip test if jpype is not installed."""
        try:
            import jpype
        except ImportError:
            pytest.skip("jpype1 not installed")

    def test_save_plantuml_returns_file_list(self, tmp_path: Path, skip_if_no_jpype: None) -> None:
        """save(format='plantuml') returns list of created files."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            from buildzr.dsl import SystemContextView, ContainerView
            SystemContextView(system, key="context", description="Context view")
            with system:
                Container("Container")
            ContainerView(system, key="containers", description="Containers view")

        result = w.save(format='plantuml', path=tmp_path)

        assert isinstance(result, list)
        assert len(result) == 2
        assert all(f.endswith('.puml') for f in result)
        # Verify files exist
        for f in result:
            assert Path(f).exists()

    def test_save_svg_format(self, tmp_path: Path, skip_if_no_jpype: None) -> None:
        """save(format='svg') creates SVG files."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.save(format='svg', path=tmp_path)

        assert isinstance(result, list)
        assert any(f.endswith('.svg') for f in result)
        # Verify file exists and contains SVG content
        for f in result:
            assert Path(f).exists()
            content = Path(f).read_text()
            assert "<svg" in content.lower() or "<?xml" in content

    def test_save_png_format(self, tmp_path: Path, skip_if_no_jpype: None) -> None:
        """save(format='png') creates PNG files."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.save(format='png', path=tmp_path)

        assert isinstance(result, list)
        assert any(f.endswith('.png') for f in result)
        # Verify files exist
        for f in result:
            assert Path(f).exists()

    def test_save_plantuml_default_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, skip_if_no_jpype: None) -> None:
        """save(format='plantuml') defaults to cwd for output directory."""
        monkeypatch.chdir(tmp_path)

        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.save(format='plantuml')

        assert isinstance(result, list)
        assert len(result) == 1
        # Should be in cwd
        assert str(tmp_path) in result[0]
