"""Canonical JSON I/O shared by every stage of the site build.

Canonical bytes = ``json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False) + "\\n"``, UTF-8, with every coordinate passed through
:func:`rnd`. Reused from the viewer spike (``spike/tools/scene_io.py``).
"""

from __future__ import annotations

import hashlib
import json
from typing import Any

MODEL_SCHEMA = "buildzr.model/2"
SCENE_SCHEMA = "buildzr.scene/2"
INDEX_SCHEMA = "buildzr.index/2"


def rnd(v: float) -> float | int:
    """Round to 0.01; integral values become int so 12.0 is written as 12; -0 becomes 0."""
    r = round(float(v), 2)
    if r == 0:
        return 0
    return int(r) if r == int(r) else r


def dumps(obj: Any) -> str:
    """Return the canonical text of ``obj``."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def write(path: str, obj: Any) -> None:
    """Write ``obj`` to ``path`` in canonical form."""
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(obj))


def sha256_of(obj: Any) -> str:
    """Return ``sha256:<hex>`` of the canonical bytes of ``obj``."""
    return "sha256:" + hashlib.sha256(dumps(obj).encode("utf-8")).hexdigest()


def model_hash(model: dict[str, Any]) -> str:
    """Return the modelHash of a model.json object (hashed with modelHash = "")."""
    return sha256_of({**model, "modelHash": ""})
