"""Tests for Jupyter notebook display features."""

import json
import pytest
from buildzr.dsl import Workspace, SoftwareSystem, Person, Container, SystemContextView


class TestJsonMethods:
    """Tests for to_dict(), to_json_string(), and _repr_json_()."""

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

    def test_to_json_string_returns_string(self) -> None:
        """to_json_string() should return a valid JSON string."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json_string()

        assert isinstance(result, str)
        # Should be valid JSON
        parsed = json.loads(result)
        assert parsed["name"] == "Test"

    def test_to_json_string_pretty_format(self) -> None:
        """to_json_string(pretty=True) should return indented JSON."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json_string(pretty=True)

        # Pretty formatted JSON should have newlines
        assert "\n" in result
        assert "  " in result  # 2-space indent

    def test_to_json_string_compact_format(self) -> None:
        """to_json_string(pretty=False) should return compact JSON."""
        with Workspace("Test") as w:
            Person("User")

        result = w.to_json_string(pretty=False)

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


class TestPlantUmlStringMethods:
    """Tests for to_plantuml_string() and to_svg_string()."""

    def test_to_plantuml_string_requires_jpype(self) -> None:
        """to_plantuml_string() should raise ImportError if jpype not installed."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        # This test assumes jpype IS installed in the test environment
        # If not, it would raise ImportError which is the expected behavior
        try:
            result = w.to_plantuml_string()
            # If we get here, jpype is installed
            assert isinstance(result, dict)
        except ImportError as e:
            # Expected if jpype not installed
            assert "jpype1" in str(e).lower() or "plantuml" in str(e).lower()

    def test_to_svg_string_requires_jpype(self) -> None:
        """to_svg_string() should raise ImportError if jpype not installed."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        try:
            result = w.to_svg_string()
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

    def test_to_plantuml_string_returns_dict(self, skip_if_no_jpype: None) -> None:
        """to_plantuml_string() should return dict of view_key -> puml content."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.to_plantuml_string()

        assert isinstance(result, dict)
        assert "context" in result
        assert "@startuml" in result["context"]
        assert "@enduml" in result["context"]

    def test_to_plantuml_string_multiple_views(self, skip_if_no_jpype: None) -> None:
        """to_plantuml_string() should include all views."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            with system:
                container = Container("Container")

            from buildzr.dsl import SystemContextView, ContainerView
            SystemContextView(system, key="context", description="Context view")
            ContainerView(system, key="containers", description="Container view")

        result = w.to_plantuml_string()

        assert len(result) == 2
        assert "context" in result
        assert "containers" in result

    def test_to_svg_string_returns_svg_content(self, skip_if_no_jpype: None) -> None:
        """to_svg_string() should return dict of view_key -> SVG content."""
        with Workspace("Test") as w:
            system = SoftwareSystem("System")
            SystemContextView(system, key="context", description="Context view")

        result = w.to_svg_string()

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
