"""``python -m buildzr.site.layout --data DIR [--k 4]``."""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Optional, Sequence

from buildzr.site.layout import ElkError, layout_workspace


def main(argv: Optional[Sequence[str]] = None) -> int:
    ap = argparse.ArgumentParser(prog="python -m buildzr.site.layout", description="Lay out levels.json into scenes.")
    ap.add_argument("--data", required=True, help="directory holding levels.json and model.json; scenes are written there")
    ap.add_argument("--k", type=float, default=4.0, help="frame area budget in leaf boxes (default 4)")
    args = ap.parse_args(list(argv) if argv is not None else None)
    with open(os.path.join(args.data, "levels.json"), encoding="utf-8") as f:
        levels = json.load(f)
    with open(os.path.join(args.data, "model.json"), encoding="utf-8") as f:
        model = json.load(f)
    try:
        metrics = layout_workspace(levels, model, args.data, k=args.k)
    except ElkError as e:
        print(f"error: {e}", file=sys.stderr)
        return 2
    print(json.dumps(metrics, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
