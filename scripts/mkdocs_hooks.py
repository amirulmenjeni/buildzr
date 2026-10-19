"""mkdocs hook: refuse to build the docs without the Run Code assets (``docs/runcode/``, see build_docs_assets.py)."""

from __future__ import annotations

import os
from typing import Any

from mkdocs.exceptions import PluginError

NEEDED = ("manifest.json", "viewer/index.html", "elk.bundled.js", "browser_elk.js")


def missing_runcode_assets(docs_dir: str) -> list[str]:
    """The files of ``docs/runcode/`` that the Run Code button loads and that are not there."""
    folder = os.path.join(docs_dir, "runcode")
    return [name for name in NEEDED if not os.path.isfile(os.path.join(folder, name))]


def on_config(config: Any) -> Any:
    missing = missing_runcode_assets(config["docs_dir"])
    if missing:
        raise PluginError(
            "The Run Code assets are missing from docs/runcode/ (" + ", ".join(missing) + "). Build them first: "
            "`cd viewer && npm ci && cd .. && uv run python scripts/build_docs_assets.py` (Node.js 22 needed).")
    return config
