"""Compare two directories of JSON files byte-for-byte.

    python3 spike/determinism/compare.py DIR_A DIR_B
Exit code 1 if any file differs.
"""
from __future__ import annotations

import difflib
import sys
from pathlib import Path


def main(a: str, b: str) -> int:
    da, db = Path(a), Path(b)
    names = sorted({p.name for p in da.glob("*.json")} | {p.name for p in db.glob("*.json")})
    bad = 0
    for n in names:
        fa, fb = da / n, db / n
        if not fa.exists() or not fb.exists():
            print(f"{n}: MISSING in {'A' if not fa.exists() else 'B'}")
            bad += 1
            continue
        ta, tb = fa.read_bytes(), fb.read_bytes()
        if ta == tb:
            print(f"{n}: identical")
            continue
        bad += 1
        diff = [l for l in difflib.unified_diff(
            ta.decode().splitlines(), tb.decode().splitlines(), "A", "B", lineterm="", n=0)
            if l[:1] in "+-" and l[:3] not in ("+++", "---")]
        print(f"{n}: DIFFERENT, {len(diff)} differing lines")
        for l in diff[:5]:
            print("    " + l)
    return 1 if bad else 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1], sys.argv[2]))
