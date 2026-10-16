"""Canonical scene-graph I/O shared by every spike stage (stdlib only).

Canonical bytes = json.dumps(obj, sort_keys=True, separators=(",", ":"),
ensure_ascii=False) + "\\n", UTF-8, with every coordinate passed through rnd().
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

SCHEMA = "buildzr.scene/1"


def rnd(v: float) -> float | int:
    """Round to 0.01; integral values become int so 12.0 is written as 12; -0 becomes 0."""
    r = round(float(v), 2)
    if r == 0:
        return 0
    return int(r) if r == int(r) else r


def dumps(obj: Any) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False) + "\n"


def write(path: str, obj: Any) -> None:
    with open(path, "w", encoding="utf-8", newline="\n") as f:
        f.write(dumps(obj))


def sha256_of(obj: Any) -> str:
    return "sha256:" + hashlib.sha256(dumps(obj).encode("utf-8")).hexdigest()
