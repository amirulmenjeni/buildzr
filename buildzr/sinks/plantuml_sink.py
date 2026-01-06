"""PlantUML sink for exporting workspaces to PlantUML diagrams."""

import os
from dataclasses import dataclass
from typing import Optional, Literal
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
            import jpype
        except ImportError as e:
            raise ImportError(
                "jpype1 is required for PlantUML export. "
                "Install with: pip install buildzr[export-plantuml]"
            ) from e

        # Initialize JVM if needed
        self._ensure_jvm_started(config)

        # TODO: Phase 2 - Convert workspace to Java
        # TODO: Phase 3 - Export using Java exporter
        # TODO: Phase 4 - Write files and render

        # Placeholder implementation
        print(f"PlantUML export to {config.path} (format: {config.format})")

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
