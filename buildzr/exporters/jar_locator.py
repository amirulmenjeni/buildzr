"""Locates and downloads required JAR files for PlantUML export."""

import os
import sys
from pathlib import Path
from typing import List


def get_jars_dir() -> Path:
    """Get the jars directory path."""
    return Path(__file__).parent.parent / "jars"


def get_bundled_jar_paths(auto_download: bool = True) -> List[str]:
    """
    Get paths to all required JARs for PlantUML export.

    If JARs are not found and auto_download is True, they will be
    downloaded from Maven Central automatically.

    Args:
        auto_download: If True, download missing JARs automatically.

    Returns:
        List[str]: Absolute paths to all required JAR files

    Raises:
        FileNotFoundError: If JARs cannot be found and auto_download is False

    Example:
        >>> jar_paths = get_bundled_jar_paths()
        >>> print(jar_paths)
        ['/path/to/buildzr/jars/structurizr-export.jar', ...]
    """
    required_jars = [
        "structurizr-export.jar",
        "structurizr-core.jar",
        "commons-logging.jar",
        "plantuml.jar",
    ]

    jars_dir = get_jars_dir()
    found_jars: List[str] = []
    missing_jars: List[str] = []

    # Check which JARs exist
    for jar_name in required_jars:
        jar_path = jars_dir / jar_name
        if jar_path.exists():
            found_jars.append(str(jar_path.resolve()))
        else:
            missing_jars.append(jar_name)

    # If all JARs found, return them
    if not missing_jars:
        return found_jars

    # Try auto-download if enabled
    if auto_download:
        print(f"Downloading missing JARs: {missing_jars}")
        try:
            from buildzr.exporters.download_jars import download_all_jars
            download_all_jars()

            # Re-check after download
            found_jars = []
            for jar_name in required_jars:
                jar_path = jars_dir / jar_name
                if jar_path.exists():
                    found_jars.append(str(jar_path.resolve()))

            if len(found_jars) == len(required_jars):
                return found_jars
        except Exception as e:
            print(f"Auto-download failed: {e}")

    # Still missing - raise error with helpful message
    raise FileNotFoundError(
        f"Required JARs not found: {missing_jars}\n\n"
        "JARs should be downloaded automatically during pip install.\n"
        "Try reinstalling: pip install buildzr[export-plantuml]\n\n"
        "Or download manually from Maven Central."
    )


def get_bundled_jar_path() -> str:
    """
    Get path to structurizr-export JAR (legacy method).

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
    Get the version of the structurizr-export JAR.

    Returns:
        str: Version string
    """
    return "3.2.0"
