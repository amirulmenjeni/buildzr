"""``buildzr serve --example``: the bundled example workspace, built ahead of time and served from a temporary folder.

``buildzr/site/example/`` holds the built workspace (``build.json`` and ``data/``, made by
``scripts/build_serve_example.py``) and ``buildzr/site/static/`` the viewer bundle, so nothing is laid out at run time
and Node is not needed. :func:`stage` puts both into a folder of the caller, where :mod:`buildzr.site.serve` serves them.
"""

from __future__ import annotations

import os
import shutil

from buildzr.site.build import STATIC_DIR

EXAMPLE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "example")

#: The name of the example workspace: it is served at ``/example/``.
EXAMPLE_NAME = "example"


class ExampleError(Exception):
    """The example cannot be served from this installation; the message is meant for the user."""


def stage(dest: str) -> str:
    """Copy the example (data and viewer) to ``dest/example`` and return that folder; ``dest`` is a build output."""
    if not os.path.isfile(os.path.join(EXAMPLE_DIR, "build.json")) or not os.path.isdir(os.path.join(EXAMPLE_DIR, "data")):
        raise ExampleError(f"the bundled example is missing ({EXAMPLE_DIR}); reinstall buildzr, or run "
                           "scripts/build_serve_example.py in a source checkout")
    if not os.path.isfile(os.path.join(STATIC_DIR, "index.html")):
        raise ExampleError(f"the viewer bundle is missing ({STATIC_DIR}/index.html); reinstall buildzr, or build the "
                           "viewer in a source checkout (cd viewer && npm ci && npm run build)")
    folder = os.path.join(dest, EXAMPLE_NAME)
    shutil.copytree(STATIC_DIR, folder)
    shutil.copytree(EXAMPLE_DIR, folder, dirs_exist_ok=True)
    return folder
