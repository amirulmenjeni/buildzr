"""Material's version picker survives the mike plugin.

Material copies ``extra.version`` into the page only if the mike plugin is absent or has ``version_selector`` on
(``base.html``). With ``version_selector: false`` the page gets ``"version": null`` and no picker is drawn. mike has no
Material support, so with the option on it adds no selector of its own.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Any

import pytest
import yaml

from tests.docs.browser import build_docs
from tests.docs.blocks import DOCS, ROOT

MANIFEST = os.path.join(DOCS, "runcode", "manifest.json")


def _plugin_options(config: dict[str, Any], name: str) -> Any:
    """The options of a plugin entry of an mkdocs config (``None``: not listed; ``{}``: listed without options)."""
    for entry in config.get("plugins", []):
        if entry == name:
            return {}
        if isinstance(entry, dict) and name in entry:
            return entry[name] or {}
    return None


def test_the_mike_plugin_does_not_switch_off_the_version_selector() -> None:
    with open(os.path.join(ROOT, "mkdocs.yml"), encoding="utf-8") as f:
        config = yaml.safe_load(f)
    assert config["extra"]["version"] == {"provider": "mike", "default": "latest"}
    mike = _plugin_options(config, "mike")
    assert mike is not None, "the mike plugin is not listed"
    assert mike.get("version_selector", True) is not False, (
        "version_selector: false makes Material drop extra.version, so the version picker disappears")
    assert mike.get("canonical_version") == "latest"


@pytest.mark.skipif(not os.path.isfile(MANIFEST), reason="the Run Code assets are not built (scripts/build_docs_assets.py)")
def test_a_built_page_hands_the_version_to_material(tmp_path: Path) -> None:
    site = build_docs(tmp_path)
    for page in ("index.html", "user-guide/views/index.html"):
        html = (site / page).read_text(encoding="utf-8")
        found = re.search(r'<script id="__config" type="application/json">(.*?)</script>', html, re.S)
        assert found, f"{page}: no __config"
        assert json.loads(found.group(1))["version"] == {"provider": "mike", "default": "latest"}, page
    # mike adds no selector files or references of its own for Material
    assert not (site / "js" / "version-select.js").exists() and not (site / "css" / "version-select.css").exists()
    assert "version-select" not in (site / "index.html").read_text(encoding="utf-8")
