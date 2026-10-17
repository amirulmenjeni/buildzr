"""Shared helpers of the store tests: small sites with distinct models, hashed scene names, and a store to put them in."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import uuid
from pathlib import Path
from typing import Any

from buildzr.site import canonical
from buildzr.site.store import Installed, Store

Json = dict[str, Any]


def model_path(h8: str) -> str:
    return f"model.{h8}.json"


def variant(src: Path, dest: Path, n: int, extra: bool = False) -> Path:
    """Copy the built site ``src`` to ``dest`` as variant ``n``: its own ``modelHash``, a workspace name that says ``n``
    and scene files whose names carry a hash (``landscape.<h8>.json``) like the real layout writes them."""
    shutil.copytree(src, dest)
    data = dest / "data"
    index: Json = json.loads((data / "index.json").read_text())
    old_model = data / index["model"]["file"]
    model: Json = json.loads(old_model.read_text())
    model["modelHash"] = "sha256:" + hashlib.sha256(f"variant-{n}".encode()).hexdigest()
    model["workspace"]["name"] = f"Small v{n}"
    mbytes = canonical.dumps(model).encode()
    h8 = hashlib.sha256(mbytes).hexdigest()[:8]
    old_model.unlink()
    (data / model_path(h8)).write_bytes(mbytes)
    index["model"] = {"file": model_path(h8), "hash": "sha256:" + hashlib.sha256(mbytes).hexdigest()}
    index["modelHash"] = model["modelHash"]
    for key, entry in index["scenes"].items():
        f = data / entry["file"]
        scene: Json = json.loads(f.read_text())
        scene["variant"] = n
        sbytes = canonical.dumps(scene).encode()
        sh = hashlib.sha256(sbytes).hexdigest()
        f.unlink()
        rel = entry["file"][:-len(".json")] + "." + sh[:8] + ".json"
        (data / rel).write_bytes(sbytes)
        index["scenes"][key] = {"file": rel, "hash": "sha256:" + sh}
    if extra:
        (data / "scene" / "e").mkdir(parents=True, exist_ok=True)
        (data / "scene" / "e" / "only-here.deadbeef.json").write_text('{"only":"here"}\n')
    canonical.write(str(data / "index.json"), index)
    build_json = dest / "build.json"
    if build_json.exists():
        info: Json = json.loads(build_json.read_text())
        info["modelHash"] = model["modelHash"]
        canonical.write(str(build_json), info)
    return dest


def put(store: Store, site: Path, site_path: str) -> Installed:
    """Copy ``site`` into ``incoming/`` of the store and install it at ``site_path``."""
    inc = Path(store.dir) / "incoming" / uuid.uuid4().hex
    shutil.copytree(site, inc)
    return store.install(str(inc), site_path)


def model_hash_of_variant(n: int) -> str:
    return "sha256:" + hashlib.sha256(f"variant-{n}".encode()).hexdigest()


def tree(root: str) -> list[str]:
    """Every path below ``root`` relative to it (folders end with ``/``), sorted."""
    out = []
    for d, dirs, files in os.walk(root):
        for x in dirs:
            out.append(os.path.relpath(os.path.join(d, x), root) + "/")
        for x in files:
            out.append(os.path.relpath(os.path.join(d, x), root))
    return sorted(out)
