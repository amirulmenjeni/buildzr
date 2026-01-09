"""Hatch build hook to download JAR dependencies."""

import importlib.util
from pathlib import Path
from types import ModuleType

from hatchling.builders.hooks.plugin.interface import BuildHookInterface # type: ignore[import-not-found]

def _load_download_jars_module() -> ModuleType:
    """Load the download_jars module directly from file path.

    This avoids the chicken-and-egg problem where we need to import
    from buildzr before the package is installed.
    """
    module_path = Path(__file__).parent / "buildzr" / "exporters" / "download_jars.py"
    spec = importlib.util.spec_from_file_location("download_jars", module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


class JarDownloadHook(BuildHookInterface):
    """Build hook that downloads JAR files during wheel build."""

    PLUGIN_NAME = "jar-download"

    def initialize(self, version: str, build_data: dict) -> None:
        """Download JARs before building the wheel."""
        if self.target_name == "wheel":
            download_jars = _load_download_jars_module()

            if not download_jars.check_jars_exist():
                print("Downloading JAR dependencies...")
                download_jars.download_all_jars()
                print("JAR dependencies downloaded successfully.")
