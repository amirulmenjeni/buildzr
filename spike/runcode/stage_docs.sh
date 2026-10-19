#!/bin/bash
# SPIKE: put what Run Code needs under docs/runcode/ (gitignored). Run in the devcontainer after `npm run build` in viewer/.
set -euo pipefail
cd "$(dirname "$0")/../.."
OUT=docs/runcode
rm -rf "$OUT" && mkdir -p "$OUT/viewer" "$OUT/wheels"
cp -r buildzr/site/static/. "$OUT/viewer/"
cp spike/runcode/embed-shim.js spike/runcode/embed-dark.css "$OUT/viewer/"
# The viewer's index.html, plus the shim (before the module) and the dark scheme.
sed -i 's#<head>#<head>\n    <script src="./embed-shim.js"></script>\n    <link rel="stylesheet" href="./embed-dark.css">#' "$OUT/viewer/index.html"
cp buildzr/site/layout/vendor/elk.bundled.js spike/runcode/elk_sync.js spike/runcode/wrap.js spike/runcode/browser_build.py "$OUT/"
rm -rf /tmp/whl && uv build --wheel -o /tmp/whl >/dev/null
uv run python spike/runcode/make_slim_wheel.py /tmp/whl/buildzr-*-py3-none-any.whl "$OUT/wheels"
uv run --no-project --with pip pip download pyhumps==3.8.0 --no-deps -d "$OUT/wheels" -q
(cd "$OUT/wheels" && ls *.whl | node -e 'process.stdout.write(JSON.stringify({wheels: require("fs").readFileSync(0, "utf8").trim().split("\n")}))') > "$OUT/manifest.json"
du -ab "$OUT" | sort -n | tail -12
