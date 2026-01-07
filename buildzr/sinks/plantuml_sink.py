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
            import jpype  # type: ignore
        except ImportError as e:
            raise ImportError(
                "jpype1 is required for PlantUML export. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        # Initialize JVM if needed
        self._ensure_jvm_started(config)

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
        try:
            from net.sourceforge.plantuml import SourceStringReader, FileFormatOption, FileFormat  # type: ignore
        except ImportError:
            print(f"Warning: PlantUML rendering not available. Skipping {format} rendering.")
            return

        # Read PlantUML content
        with open(puml_path, 'r', encoding='utf-8') as f:
            puml_content = f.read()

        # Create reader
        reader = SourceStringReader(puml_content)

        # Determine file format
        file_format = FileFormat.SVG if format == 'svg' else FileFormat.PNG

        # Write output
        output_path = puml_path.rsplit('.', 1)[0] + f'.{format}'
        with open(output_path, 'wb') as f:
            reader.outputImage(f, FileFormatOption(file_format))

        print(f"Rendered: {output_path}")
