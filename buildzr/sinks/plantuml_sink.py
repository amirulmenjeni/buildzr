"""PlantUML sink for exporting workspaces to PlantUML diagrams."""

import os
from dataclasses import dataclass
from typing import Optional, Literal, Any
from buildzr.models.models import Workspace
from buildzr.sinks.interfaces import Sink


@dataclass
class PlantUmlSinkConfig:
    """
    Configuration for PlantUML export.

    Attributes:
        path: Output directory path where .puml files will be written
        format: Output format - 'puml' for text files, 'svg'/'png' for rendered images
        structurizr_export_jar_path: Optional custom path to structurizr-export JAR.
            If not provided, uses the bundled JAR.
    """

    path: str
    format: Literal["puml", "svg", "png"] = "puml"
    structurizr_export_jar_path: Optional[str] = None


class PlantUmlSink(Sink[PlantUmlSinkConfig]):
    """
    Sink for exporting workspace views to PlantUML format.

    This sink uses the official structurizr-export Java library via JPype
    to generate PlantUML diagrams from workspace views.

    Examples:
        >>> from buildzr.sinks.plantuml_sink import PlantUmlSink, PlantUmlSinkConfig
        >>> sink = PlantUmlSink()
        >>> config = PlantUmlSinkConfig(path='output/diagrams')
        >>> sink.write(workspace, config)
    """

    def export_to_dict(self, workspace: Workspace) -> dict[str, str]:
        """
        Export workspace views to PlantUML strings without writing files.

        Args:
            workspace: The workspace to export

        Returns:
            Dictionary mapping view keys to PlantUML source strings.

        Raises:
            ImportError: If jpype1 is not installed (install with: pip install buildzr[export-plantuml])
            FileNotFoundError: If structurizr-export JAR cannot be found
        """
        try:
            import jpype  # type: ignore
        except ImportError as e:
            raise ImportError(
                "jpype1 is required for PlantUML export. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        # Initialize JVM with default config
        self._ensure_jvm_started(PlantUmlSinkConfig(path=""))

        # Enable C4-PlantUML tags for icon/sprite support
        self._ensure_c4plantuml_tags_enabled(workspace)

        # Convert workspace to Java
        from buildzr.exporters.workspace_converter import WorkspaceConverter
        converter = WorkspaceConverter()
        java_workspace = converter.to_java(workspace)

        # Export and return
        return self._export_workspace(java_workspace)

    def render_to_svg_dict(self, workspace: Workspace) -> dict[str, str]:
        """
        Export workspace views and render to SVG strings.

        Args:
            workspace: The workspace to export

        Returns:
            Dictionary mapping view keys to SVG content strings.

        Raises:
            ImportError: If jpype1 is not installed (install with: pip install buildzr[export-plantuml])
            FileNotFoundError: If structurizr-export JAR cannot be found
        """
        # First get PlantUML strings
        diagrams = self.export_to_dict(workspace)

        # Render each to SVG
        result: dict[str, str] = {}
        for view_key, puml_content in diagrams.items():
            svg_bytes = self._render_to_bytes(puml_content, "svg")
            result[view_key] = svg_bytes.decode('utf-8')

        return result

    def _render_to_bytes(self, puml_content: str, format: str) -> bytes:
        """
        Render PlantUML content to image bytes.

        Args:
            puml_content: PlantUML source string
            format: Output format ('svg' or 'png')

        Returns:
            Image content as bytes.
        """
        try:
            from net.sourceforge.plantuml import SourceStringReader, FileFormatOption, FileFormat  # type: ignore
            from java.io import ByteArrayOutputStream  # type: ignore
        except ImportError as e:
            raise ImportError(
                "PlantUML rendering not available. "
                "Ensure the PlantUML JAR is in the classpath."
            ) from e

        reader = SourceStringReader(puml_content)
        file_format = FileFormat.SVG if format == 'svg' else FileFormat.PNG

        # Use Java ByteArrayOutputStream for compatibility
        output = ByteArrayOutputStream()
        reader.outputImage(output, FileFormatOption(file_format))
        return bytes(output.toByteArray())

    def write(self, workspace: Workspace, config: Optional[PlantUmlSinkConfig] = None) -> None:
        """
        Export workspace views to PlantUML files.

        Args:
            workspace: The workspace to export
            config: Optional configuration. If None, uses default (puml format, current directory)

        Raises:
            ImportError: If jpype1 is not installed (install with: pip install buildzr[export-plantuml])
            FileNotFoundError: If structurizr-export JAR cannot be found
            RuntimeError: If JVM initialization or export fails
        """
        if config is None:
            config = PlantUmlSinkConfig(path=os.curdir)

        # Check for jpype first
        try:
            import jpype
        except ImportError as e:
            raise ImportError(
                "jpype1 is required for PlantUML export. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        # Initialize JVM if needed
        self._ensure_jvm_started(config)

        # Enable C4-PlantUML tags for icon/sprite support
        self._ensure_c4plantuml_tags_enabled(workspace)

        # Phase 2: Convert workspace to Java
        from buildzr.exporters.workspace_converter import WorkspaceConverter
        converter = WorkspaceConverter()
        java_workspace = converter.to_java(workspace)

        # Phase 3: Export using Java exporter
        diagrams = self._export_workspace(java_workspace)

        # Phase 4: Write files and render
        self._write_diagrams(diagrams, config)

    def _ensure_jvm_started(self, config: PlantUmlSinkConfig) -> None:
        """
        Ensure JVM is started with the structurizr-export and dependency JARs.

        Args:
            config: Configuration containing optional custom JAR path

        Raises:
            FileNotFoundError: If JARs cannot be found
        """
        import jpype
        from buildzr.exporters.jar_locator import get_bundled_jar_paths

        if jpype.isJVMStarted():
            return  # JVM already running

        # Determine JAR paths
        if config.structurizr_export_jar_path:
            # Custom JAR path provided - use only that
            jar_paths = [config.structurizr_export_jar_path]
            if not os.path.exists(jar_paths[0]):
                raise FileNotFoundError(
                    f"structurizr-export JAR not found at {jar_paths[0]}"
                )
        else:
            # Use bundled JARs (export + dependencies)
            jar_paths = get_bundled_jar_paths()  # Raises if not found

        # Start JVM with JARs in classpath
        jpype.startJVM(classpath=jar_paths)
        print(f"JVM started with JARs: {', '.join(jar_paths)}")

    def _ensure_c4plantuml_tags_enabled(self, workspace: Workspace) -> None:
        """
        Ensure the c4plantuml.tags property is set to enable icon/sprite support.

        The C4PlantUML exporter only outputs AddElementTag() with sprites when
        the c4plantuml.tags property is set to "true". This method ensures that
        property is set when the workspace has element styles with icons.

        Args:
            workspace: The workspace to configure
        """
        from buildzr.models.models import Configuration

        if not workspace.views:
            return

        # Ensure configuration exists
        if not workspace.views.configuration:
            workspace.views.configuration = Configuration()

        config = workspace.views.configuration

        # Ensure properties dict exists
        if not config.properties:
            config.properties = {}

        # Enable c4plantuml.tags if not explicitly set
        if 'c4plantuml.tags' not in config.properties:
            config.properties['c4plantuml.tags'] = 'true'

    def _export_workspace(self, java_workspace: Any) -> dict[str, str]:
        """
        Export all views in Java workspace to PlantUML diagrams.

        Args:
            java_workspace: Java com.structurizr.Workspace object

        Returns:
            Dictionary mapping view keys to PlantUML diagram content
        """
        from com.structurizr.export.plantuml import C4PlantUMLExporter  # type: ignore

        exporter = C4PlantUMLExporter()
        diagrams = {}

        # Get all views from workspace
        views = java_workspace.getViews()

        # Export system landscape views
        for view in views.getSystemLandscapeViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export system context views
        for view in views.getSystemContextViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export container views
        for view in views.getContainerViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export component views
        for view in views.getComponentViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export deployment views
        for view in views.getDeploymentViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export dynamic views
        for view in views.getDynamicViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        # Export custom views
        for view in views.getCustomViews():
            diagram = exporter.export(view)
            diagrams[str(view.getKey())] = str(diagram.getDefinition())

        return diagrams

    def _write_diagrams(self, diagrams: dict[str, str], config: PlantUmlSinkConfig) -> None:
        """
        Write PlantUML diagrams to files.

        Args:
            diagrams: Dictionary mapping view keys to PlantUML content
            config: Export configuration
        """
        # Create output directory if needed
        os.makedirs(config.path, exist_ok=True)

        for view_key, puml_content in diagrams.items():
            # Write .puml file
            puml_path = os.path.join(config.path, f"{view_key}.puml")
            with open(puml_path, 'w', encoding='utf-8') as f:
                f.write(puml_content)
            print(f"Exported: {puml_path}")

            # Render to image if requested
            if config.format in ['svg', 'png']:
                self._render_diagram(puml_path, config.format)

    def _render_diagram(self, puml_path: str, format: str) -> None:
        """
        Render PlantUML diagram to image format.

        Args:
            puml_path: Path to .puml file
            format: Output format ('svg' or 'png')
        """
        # Read PlantUML content
        with open(puml_path, 'r', encoding='utf-8') as f:
            puml_content = f.read()

        # Render to bytes using our helper method
        try:
            image_bytes = self._render_to_bytes(puml_content, format)
        except ImportError:
            print(f"Warning: PlantUML rendering not available. Skipping {format} rendering.")
            return

        # Write output
        output_path = puml_path.rsplit('.', 1)[0] + f'.{format}'
        with open(output_path, 'wb') as f:
            f.write(image_bytes)

        print(f"Rendered: {output_path}")
