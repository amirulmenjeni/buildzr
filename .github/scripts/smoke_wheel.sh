#!/usr/bin/env bash
# Prove that a built wheel works for a user: install it into a fresh venv and
# run the real commands (build, serve, deploy) against it.
#
# Usage: smoke_wheel.sh [DIST_DIR]    (default: dist, relative to the repo)
#
# Run it from anywhere after `cd viewer && npm ci && npm run build && cd .. &&
# uv build`. It needs uv, python 3.10 or newer, node 18 or newer and curl.
# Everything happens in a temporary folder outside the repository, so the
# checkout cannot be imported by accident. Set KEEP=1 to keep the folder.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST="$(cd "${1:-$REPO/dist}" && pwd)"
WORK="$(mktemp -d)"
PIDS=()

fail() { echo "::error title=Smoke test::$*" >&2; echo "SMOKE TEST FAILED: $*" >&2; exit 1; }
step() { echo; echo "== $*"; }

cleanup() {
  status=$?
  for pid in "${PIDS[@]:-}"; do [[ -n "$pid" ]] && kill "$pid" 2>/dev/null || true; done
  if [[ $status -ne 0 ]]; then
    for log in "$WORK"/*.log; do
      [[ -f "$log" ]] && { echo "--- $(basename "$log")"; cat "$log"; } >&2
    done
  fi
  if [[ "${KEEP:-}" = 1 ]]; then echo "kept $WORK"; else rm -rf "$WORK"; fi
}
trap cleanup EXIT

free_port() {
  "$WORK/venv/bin/python" -c 'import socket; s = socket.socket(); s.bind(("127.0.0.1", 0)); print(s.getsockname()[1])'
}

# get URL BODY_FILE: fail unless URL answers 200
get() {
  local code
  code="$(curl -sS -o "$2" -w '%{http_code}' --max-time 20 "$1")" || fail "cannot reach $1"
  [[ "$code" = 200 ]] || fail "GET $1 answered $code, expected 200"
  echo "200 $1 ($(wc -c <"$2" | tr -d ' ') bytes)"
}

wait_for() {
  for _ in $(seq 1 60); do
    curl -sS -o /dev/null --max-time 2 "$1" 2>/dev/null && return 0
    sleep 0.5
  done
  fail "$2 did not start listening at $1 within 30 seconds"
}

shopt -s nullglob
wheels=("$DIST"/buildzr-*.whl)
[[ ${#wheels[@]} -eq 1 ]] || fail "expected exactly one wheel in $DIST, found ${#wheels[@]}"
WHEEL="${wheels[0]}"

# The venv's python runs the stdlib-only helper scripts too, so the machine
# needs no other python.
step "Create a fresh venv"
uv venv --python 3.10 "$WORK/venv" >/dev/null

step "Check the package"
"$WORK/venv/bin/python" "$REPO/.github/scripts/check_wheel.py" "$DIST" --sdist

step "Install $(basename "$WHEEL") with the serve extra"
uv pip install --python "$WORK/venv/bin/python" "buildzr[serve] @ file://$WHEEL" >/dev/null
export PATH="$WORK/venv/bin:$PATH"
cd "$WORK"
mkdir run && cd run   # the working folder holds no checkout files
python -I -c 'import buildzr, sys; print(buildzr.__file__); sys.exit(0 if "'"$WORK"'/venv" in buildzr.__file__ else 1)' \
  || fail "buildzr is not imported from the fresh venv"

step "buildzr build"
cp "$REPO/examples/buildzr_models_example.py" model.py
buildzr build -w model.py -o site
[[ -f site/index.html ]] || fail "buildzr build wrote no site/index.html (the viewer is missing)"
[[ -f site/data/index.json ]] || fail "buildzr build wrote no site/data/index.json"

step "buildzr serve"
PORT="$(free_port)"
buildzr serve site -p "$PORT" >"$WORK/serve.log" 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$PORT/data/index.json" "buildzr serve"
get "http://127.0.0.1:$PORT/" "$WORK/page.html"
grep -q 'id="root"' "$WORK/page.html" || fail "the served page has no viewer root element (id=\"root\")"
get "http://127.0.0.1:$PORT/data/index.json" "$WORK/index.json"
get "http://127.0.0.1:$PORT/api/v1/" "$WORK/api.json"

step "buildzr serve --store --accept-deploys, then buildzr deploy"
READ="$(free_port)"
DEPLOY="$(free_port)"
buildzr serve --store "$WORK/store" --accept-deploys -p "$READ" --deploy-port "$DEPLOY" >"$WORK/instance.log" 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$READ/" "the instance"
cat >buildzr.yaml <<YAML
workspace: model.py
targets:
  smoke: {url: "http://127.0.0.1:$DEPLOY", path: "pr/1"}
YAML
buildzr deploy -t smoke
get "http://127.0.0.1:$READ/pr/1/" "$WORK/pr.html"
grep -q 'id="root"' "$WORK/pr.html" || fail "the deployed page has no viewer root element (id=\"root\")"
get "http://127.0.0.1:$READ/pr/1/api/v1/" "$WORK/pr-api.json"

step "uvx --from the wheel buildzr build (the isolated route of the docs)"
if command -v uvx >/dev/null 2>&1; then
  # An empty folder and a tool environment of their own: nothing of the venv above is used.
  mkdir "$WORK/uvx" && cd "$WORK/uvx"
  cp "$REPO/examples/buildzr_models_example.py" model.py
  PATH="${PATH#"$WORK/venv/bin:"}" uvx --from "$WHEEL" buildzr build -w model.py -o out
  [[ -f out/index.html ]] || fail "uvx buildzr build wrote no out/index.html (the viewer is missing)"
  [[ -f out/data/index.json ]] || fail "uvx buildzr build wrote no out/data/index.json"
else
  echo "uvx not available, skipping the isolated-run check"
fi

echo
echo "SMOKE TEST PASSED: $(basename "$WHEEL")"
