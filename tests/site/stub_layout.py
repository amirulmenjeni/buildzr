"""TEST HELPER ONLY: a stand-in for ``buildzr.site.layout.layout_workspace`` (W2).

It does no layout: it copies the hand-made fixture scenes and index.json from
``tests/site/fixtures/small`` (stamped with the model's hash) and adds ``levels-digest.json`` (a hash of the
levels it was given) so that tests can see non-determinism upstream. The data passes the checker only for the
small workspace (``tests/site/small_workspace.py``); for any other model, replace ``build.check_workspace``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from typing import Any

from buildzr.site import canonical
from buildzr.site.layout import ELK_VERSION  # noqa: F401  (import the package first: scene <-> layout cycle)
from buildzr.site.scene import model_path

FIXTURE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "small")


def stub_layout(levels: dict[str, Any], model: dict[str, Any], data_dir: str, k: int = 4) -> None:
    with open(os.path.join(FIXTURE, "index.json"), encoding="utf-8") as f:
        index = json.load(f)
    index["modelHash"] = model["modelHash"]
    for entry in index["scenes"].values():  # the scenes carry the model's hash, as real ones do
        with open(os.path.join(FIXTURE, entry["file"]), encoding="utf-8") as f:
            scene = json.load(f)
        scene["modelHash"] = model["modelHash"]
        os.makedirs(os.path.dirname(os.path.join(data_dir, entry["file"])), exist_ok=True)
        canonical.write(os.path.join(data_dir, entry["file"]), scene)
        with open(os.path.join(data_dir, entry["file"]), "rb") as f:
            entry["hash"] = "sha256:" + hashlib.sha256(f.read()).hexdigest()
    model_bytes = canonical.dumps(model).encode("utf-8")  # like the real layout: data/model.<h8>.json
    digest = hashlib.sha256(model_bytes).hexdigest()
    with open(os.path.join(data_dir, model_path(digest[:8])), "wb") as mf:
        mf.write(model_bytes)
    index["model"] = {"file": model_path(digest[:8]), "hash": "sha256:" + digest}
    canonical.write(os.path.join(data_dir, "index.json"), index)
    canonical.write(os.path.join(data_dir, "levels-digest.json"),
                    {"k": k, "levels": canonical.sha256_of(levels), "model": canonical.sha256_of(model)})
