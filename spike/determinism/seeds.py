"""Run buildzr examples under a given PYTHONHASHSEED and dump their JSON.

Each example runs in a subprocess with a fresh temp cwd. The subprocess stubs
`Workspace.save` (so nothing is written next to the example) and records
`w.to_json()` instead. The parent re-serialises with sorted keys, indent 2.

    uv run --project <worktree> python spike/determinism/seeds.py 1 2 [--mask-uuids] [--out out]
"""
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
EXAMPLES = [
    "amazon_web_services",
    "system_context_and_container_view",
    "deployment_groups",
    "dynamic_view",
    "workspace_extension",
]
UUID_RE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")
# buildzr style tags embed uuid4().hex (32 hex chars, no dashes) before the fix.
HEX32_RE = re.compile(r"(?<![0-9a-f])[0-9a-f]{32}(?![0-9a-f])")

RUNNER = r"""
import json, runpy, sys
from buildzr.dsl import Workspace
captured = []
def fake_save(self, *a, **k):
    captured.append(self.to_json())
Workspace.save = fake_save
runpy.run_path(sys.argv[1], run_name="__main__")
if not captured:
    sys.exit("example never called save()")
open(sys.argv[2], 'w').write(captured[-1])
"""


def run_example(name: str, seed: int, tmp_root: Path) -> tuple[str | None, str]:
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    with tempfile.TemporaryDirectory(dir=tmp_root) as cwd:
        p = subprocess.run(
            [sys.executable, "-c", RUNNER, str(REPO / "examples" / f"{name}.py"), str(Path(cwd) / "_captured.json")],
            cwd=cwd, env=env, capture_output=True, text=True,
        )
        captured = Path(cwd) / "_captured.json"
        text = captured.read_text() if captured.exists() else ""
    if p.returncode != 0:
        return None, p.stderr.strip().splitlines()[-1] if p.stderr.strip() else "failed"
    return text, ""


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("seeds", nargs="+", type=int)
    ap.add_argument("--mask-uuids", action="store_true")
    ap.add_argument("--out", default=str(Path(__file__).parent / "out"))
    ap.add_argument("--tag", default="", help="suffix for the seed dir, e.g. run2")
    a = ap.parse_args()
    tmp_root = Path(os.environ.get("TMPDIR_ROOT", os.path.join(tempfile.gettempdir(), "buildzr-spike")))
    tmp_root.mkdir(parents=True, exist_ok=True)
    for seed in a.seeds:
        d = Path(a.out) / f"{seed}{a.tag}"
        d.mkdir(parents=True, exist_ok=True)
        for name in EXAMPLES:
            text, err = run_example(name, seed, tmp_root)
            if text is None:
                print(f"seed {seed} {name}: SKIPPED ({err})")
                continue
            s = json.dumps(json.loads(text), sort_keys=True, indent=2) + "\n"
            if a.mask_uuids:
                s = UUID_RE.sub("<uuid>", s)
                s = HEX32_RE.sub("<uuid>", s)
            (d / f"{name}.json").write_text(s)
            print(f"seed {seed} {name}: ok ({len(s.splitlines())} lines)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
