"""TEST HELPER ONLY: a stand-in for ``buildzr.site.layout.layout_site`` (W2).

It does no layout: it copies the hand-made fixture scenes and index.json from
``tests/site/fixtures/small`` and adds ``levels-digest.json`` (a hash of the
levels it was given) so that tests can see non-determinism upstream.
"""

from __future__ import annotations

import os
import shutil
from typing import Any

from buildzr.site import canonical

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "small")


def stub_layout(levels: dict[str, Any], model: dict[str, Any], data_dir: str, k: int = 4) -> None:
    shutil.copytree(os.path.join(FIXTURE, "scene"), os.path.join(data_dir, "scene"))
    shutil.copy2(os.path.join(FIXTURE, "index.json"), os.path.join(data_dir, "index.json"))
    canonical.write(os.path.join(data_dir, "levels-digest.json"),
                    {"k": k, "levels": canonical.sha256_of(levels), "model": canonical.sha256_of(model)})
