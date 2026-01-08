"""Download required JAR files from Maven Central."""

import os
import urllib.request
from pathlib import Path
from typing import List, Tuple

# JAR dependencies with Maven coordinates and versions
JARS: List[Tuple[str, str, str]] = [
    # (group_id, artifact_id, version)
    ("com/structurizr", "structurizr-export", "3.2.0"),
    ("com/structurizr", "structurizr-core", "3.1.0"),
    ("commons-logging", "commons-logging", "1.3.4"),
    ("net/sourceforge/plantuml", "plantuml", "1.2024.8"),
]

MAVEN_CENTRAL = "https://repo1.maven.org/maven2"


def get_jar_url(group_id: str, artifact_id: str, version: str) -> str:
    """Construct Maven Central URL for a JAR."""
    return f"{MAVEN_CENTRAL}/{group_id}/{artifact_id}/{version}/{artifact_id}-{version}.jar"


def get_jars_dir() -> Path:
    """Get the jars directory path."""
    return Path(__file__).parent.parent / "jars"


def download_jar(url: str, dest_path: Path) -> None:
    """Download a JAR file from URL to destination path."""
    print(f"Downloading {url}...")
    urllib.request.urlretrieve(url, dest_path)
    print(f"  -> {dest_path}")


def download_all_jars(force: bool = False) -> None:
    """
    Download all required JAR files.

    Args:
        force: If True, re-download even if files exist.
    """
    jars_dir = get_jars_dir()
    jars_dir.mkdir(parents=True, exist_ok=True)

    for group_id, artifact_id, version in JARS:
        jar_name = f"{artifact_id}.jar"
        dest_path = jars_dir / jar_name

        if dest_path.exists() and not force:
            print(f"Skipping {jar_name} (already exists)")
            continue

        url = get_jar_url(group_id, artifact_id, version)
        try:
            download_jar(url, dest_path)
        except Exception as e:
            print(f"Error downloading {jar_name}: {e}")
            raise


def check_jars_exist() -> bool:
    """Check if all required JARs exist."""
    jars_dir = get_jars_dir()
    for _, artifact_id, _ in JARS:
        jar_path = jars_dir / f"{artifact_id}.jar"
        if not jar_path.exists():
            return False
    return True


def main() -> None:
    """CLI entry point."""
    import argparse

    parser = argparse.ArgumentParser(description="Download JAR dependencies for buildzr")
    parser.add_argument("--force", action="store_true", help="Re-download even if files exist")
    args = parser.parse_args()

    download_all_jars(force=args.force)
    print("All JARs downloaded successfully!")


if __name__ == "__main__":
    main()
