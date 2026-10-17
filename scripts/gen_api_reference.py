#!/usr/bin/env python3
"""Write the endpoint index of ``docs/agent-api.md`` from the orientation document of a site.

The orientation document (``GET api/v1/``) lists the endpoints as URL templates and the limits of each. This script
builds the model of ``examples/buildzr_models_example.py`` in this process, asks the API module for that document
(no server, no subprocess) and writes a table between these two lines of the page::

    <!-- BEGIN generated: endpoints -->
    <!-- END generated: endpoints -->

Everything outside the two lines stays as written by hand.

Usage::

    python scripts/gen_api_reference.py           # rewrite docs/agent-api.md
    python scripts/gen_api_reference.py --check   # exit 1 when the page differs from a fresh generation
"""

from __future__ import annotations

import argparse
import os
import re
import sys
import tempfile
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PAGE = os.path.join(ROOT, "docs", "agent-api.md")
EXAMPLE = os.path.join(ROOT, "examples", "buildzr_models_example.py")
BEGIN = "<!-- BEGIN generated: endpoints -->"
END = "<!-- END generated: endpoints -->"

#: Which key of ``limits`` in the orientation document belongs to which endpoint name.
LIMIT_OF = {"search": "elements", "relationships": "relationships", "neighbours": "neighbours", "tree": "tree",
            "path": "pathChains"}


def orientation() -> dict[str, Any]:
    """The answer of ``GET api/v1/`` for the models example, without serving anything."""
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from buildzr.site.api import Api
    from buildzr.site.export import load_workspaces
    from buildzr.site.model import export_model

    here = os.getcwd()
    with tempfile.TemporaryDirectory() as scratch:
        os.chdir(scratch)  # the example saves a JSON file into the current folder when it is imported
        try:
            workspace = load_workspaces(EXAMPLE)[-1]
        finally:
            os.chdir(here)
    answer: dict[str, Any] = Api(export_model(workspace)).answer("", "")
    return answer


def parameters(template: str) -> tuple[list[str], list[str]]:
    """The required and the optional parameters of a template such as ``/api/v1/path?from={from}&to={to}{&maxHops}``."""
    required = re.findall(r"[?&]([A-Za-z]+)=\{", template)
    optional: list[str] = []
    for group in re.findall(r"\{[?&]([^}]*)\}", template):
        optional += group.split(",")
    return required, optional


def table(doc: dict[str, Any]) -> str:
    rows = ["| Name | Template | Required | Optional | `limit` (default / largest) |", "|---|---|---|---|---|"]
    for name, template in doc["endpoints"].items():
        required, optional = parameters(template)
        limit = doc["limits"].get(LIMIT_OF.get(name, ""))
        rows.append("| `{}` | `{}` | {} | {} | {} |".format(
            name, template, ", ".join(f"`{p}`" for p in required) or "none",
            ", ".join(f"`{p}`" for p in optional) or "none",
            f"{limit['default']} / {limit['max']}" if limit else "none"))
    return "\n".join(rows)


def generate(text: str, doc: Optional[dict[str, Any]] = None) -> str:
    """``text`` (the page) with the lines between the markers replaced by a fresh table."""
    start, stop = text.index(BEGIN), text.index(END)
    body = table(doc if doc is not None else orientation())
    return text[:start + len(BEGIN)] + "\n" + body + "\n" + text[stop:]


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check", action="store_true", help="do not write; exit 1 if the page is out of date")
    args = ap.parse_args(argv)
    with open(PAGE, encoding="utf-8") as f:
        old = f.read()
    new = generate(old)
    if args.check:
        if new != old:
            print(f"{PAGE} is out of date; run python scripts/gen_api_reference.py", file=sys.stderr)
            return 1
        return 0
    if new != old:
        with open(PAGE, "w", encoding="utf-8") as f:
            f.write(new)
        print(f"updated {PAGE}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
