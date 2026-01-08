"""Hatch build hook to download JAR dependencies."""

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class JarDownloadHook(BuildHookInterface):
    """Build hook that downloads JAR files during wheel build."""

    PLUGIN_NAME = "jar-download"

    def initialize(self, version: str, build_data: dict) -> None:
        """Download JARs before building the wheel."""
        if self.target_name == "wheel":
            from buildzr.exporters.download_jars import download_all_jars, check_jars_exist

            if not check_jars_exist():
                print("Downloading JAR dependencies...")
                download_all_jars()
                print("JAR dependencies downloaded successfully.")
