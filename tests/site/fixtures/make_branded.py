"""Write the 'branded' fixture: a real build of ``tests/site/branded_workspace.py`` (a theme, icons, branding).

Run: ``uv run python tests/site/fixtures/make_branded.py`` (needs Node for the layout). The output under
``tests/site/fixtures/branded/`` is committed; ``tests/site/test_branding.py`` fails when it no longer matches the
workspace.
"""

from __future__ import annotations

import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
sys.path.insert(0, ROOT)

from buildzr.site.build import build_workspace  # noqa: E402

OUT = os.path.join(HERE, "branded")
WORKSPACE = "from tests.site.branded_workspace import branded_workspace\nw = branded_workspace()\n"


def main(out: str = OUT) -> None:
    os.environ["PYTHONPATH"] = ROOT + os.pathsep + os.environ.get("PYTHONPATH", "")
    with tempfile.TemporaryDirectory(prefix="buildzr-branded-") as tmp:
        src = os.path.join(tmp, "workspace.py")
        with open(src, "w", encoding="utf-8") as f:
            f.write(WORKSPACE)
        info = build_workspace(src, os.path.join(tmp, "out"), viewer=False)
        if info.get("status") != "ok":
            raise SystemExit(f"build failed: {info.get('errors')}")
        shutil.rmtree(out, ignore_errors=True)
        shutil.copytree(os.path.join(tmp, "out", "data"), out)


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else OUT)
