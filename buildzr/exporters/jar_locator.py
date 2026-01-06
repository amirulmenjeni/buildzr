"""Locates the bundled structurizr-export JAR files."""

import os
import sys
from pathlib import Path
from typing import List


def get_bundled_jar_paths() -> List[str]:
    """
    Get paths to all bundled structurizr JARs (export and core).

    Searches in multiple locations:
    1. Relative to this file (development/installed package)
    2. System-wide installation directories

    Returns:
        List[str]: Absolute paths to all required JAR files

    Raises:
        FileNotFoundError: If JARs cannot be found

    Example:
        >>> jar_paths = get_bundled_jar_paths()
        >>> print(jar_paths)
        ['/path/to/buildzr/jars/structurizr-export.jar', '/path/to/buildzr/jars/structurizr-core.jar']
    """
    required_jars = ["structurizr-export.jar", "structurizr-core.jar", "commons-logging.jar"]
    found_jars = []

    # Check package data location (relative to this file)
    jars_dir = Path(__file__).parent.parent / "jars"

    if jars_dir.exists():
        for jar_name in required_jars:
            jar_path = jars_dir / jar_name
            if jar_path.exists():
                found_jars.append(str(jar_path.resolve()))

    # If we found all JARs, return them
    if len(found_jars) == len(required_jars):
        return found_jars

    # Fallback: check install locations in sys.path
    found_jars = []
    for path_str in sys.path:
        jars_dir = Path(path_str) / "buildzr" / "jars"
        if jars_dir.exists():
            for jar_name in required_jars:
                jar_path = jars_dir / jar_name
                if jar_path.exists():
                    found_jars.append(str(jar_path.resolve()))

            if len(found_jars) == len(required_jars):
                return found_jars

    # Not found - provide helpful error message
    missing_jars = [jar for jar in required_jars if not any(jar in path for path in found_jars)]
    raise FileNotFoundError(
        f"Required JARs not found: {missing_jars}. "
        "Please install with PlantUML export support: "
        "pip install buildzr[export-plantuml]"
    )


def get_bundled_jar_path() -> str:
    """
    Get path to bundled structurizr-export JAR (legacy method).

    Deprecated: Use get_bundled_jar_paths() instead.

    Returns:
        str: Absolute path to the structurizr-export JAR file

    Raises:
        FileNotFoundError: If JAR cannot be found
    """
    jar_paths = get_bundled_jar_paths()
    # Return the export JAR (first one)
    return jar_paths[0]


def get_jar_version() -> str:
    """
    Get the version of the bundled structurizr-export JAR.

    Returns:
        str: Version string (e.g., "5.0.1")

    Note:
        This is a placeholder. Actual version detection would require
        reading JAR manifest or using a version file.
    """
    # TODO: Implement actual version detection
    return "5.0.1"
