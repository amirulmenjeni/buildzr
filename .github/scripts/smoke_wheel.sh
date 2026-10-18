#!/usr/bin/env bash
# Prove that a built wheel works for a user: install it into a fresh venv and
# run the real commands (build, serve) against a workspaces folder.
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

# status URL: the HTTP status of URL, without following a redirect
status() {
  curl -sS -o /dev/null -w '%{http_code}' --max-time 20 "$1" || fail "cannot reach $1"
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

step "Install $(basename "$WHEEL")"
uv pip install --python "$WORK/venv/bin/python" "buildzr @ file://$WHEEL" >/dev/null
export PATH="$WORK/venv/bin:$PATH"
cd "$WORK"
mkdir run && cd run   # the working folder holds no checkout files
python -I -c 'import buildzr, sys; print(buildzr.__file__); sys.exit(0 if "'"$WORK"'/venv" in buildzr.__file__ else 1)' \
  || fail "buildzr is not imported from the fresh venv"

# example NAME: the bundled example as a workspace called NAME
example() {
  sed "s/Workspace('microservices-example'/Workspace('$1'/" "$REPO/examples/buildzr_models_example.py"
}

step "buildzr build (two workspaces in workspaces/)"
mkdir workspaces
example a >workspaces/a.py
example b >workspaces/b.py
buildzr build
for name in a b; do
  [[ -f .buildzr/build/$name/index.html ]] || fail "buildzr build wrote no .buildzr/build/$name/index.html (the viewer is missing)"
  [[ -f .buildzr/build/$name/data/index.json ]] || fail "buildzr build wrote no .buildzr/build/$name/data/index.json"
done

step "buildzr serve (both up to date: nothing is built)"
PORT="$(free_port)"
buildzr serve -p "$PORT" >"$WORK/serve.log" 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$PORT/_buildzr/v1/workspaces" "buildzr serve"
grep -q '^up to date: a, b$' "$WORK/serve.log" || fail "buildzr serve did not find both workspaces up to date"
get "http://127.0.0.1:$PORT/" "$WORK/index.html"
grep -q 'href="/a/"' "$WORK/index.html" && grep -q 'href="/b/"' "$WORK/index.html" \
  || fail "the index page does not link both workspaces"
for name in a b; do
  get "http://127.0.0.1:$PORT/$name/" "$WORK/$name.html"
  grep -q 'id="root"' "$WORK/$name.html" || fail "/$name/ has no viewer root element (id=\"root\")"
done
get "http://127.0.0.1:$PORT/a/api/v1/" "$WORK/api.json"
grep -q '"name":"a"' "$WORK/api.json" || fail "/a/api/v1/ is not the orientation document of workspace a"
get "http://127.0.0.1:$PORT/_buildzr/v1/workspaces" "$WORK/list.json"
python -I -c 'import json, sys; names = [w["name"] for w in json.load(open(sys.argv[1]))["workspaces"]]; sys.exit(names != ["a", "b"])' \
  "$WORK/list.json" || fail "/_buildzr/v1/workspaces does not list a and b"

step "buildzr build with a broken workspace (exit code 1, shown as broken)"
printf 'from buildzr.dsl import Workspace\nwith Workspace("broken") as w:\n    raise RuntimeError("smoke: boom")\n' >workspaces/broken.py
set +e
buildzr build >"$WORK/build-broken.log" 2>&1
code=$?
set -e
cat "$WORK/build-broken.log"
[[ "$code" = 1 ]] || fail "buildzr build exited with $code for a broken workspace, expected 1"
grep -q '^buildzr: BROKEN: workspace broken (workspaces/broken.py) failed at the model step$' "$WORK/build-broken.log" \
  || fail "buildzr build printed no BROKEN block for the broken workspace"
# The running serve finds the new workspace on the next request to the list.
get "http://127.0.0.1:$PORT/_buildzr/v1/workspaces" "$WORK/list-broken.json"
python -I -c '
import json, sys
ws = {w["name"]: w for w in json.load(open(sys.argv[1]))["workspaces"]}
b = ws.get("broken", {})
ok = [ws[n]["status"] for n in ("a", "b")] == ["ok", "ok"]
sys.exit(0 if ok and b.get("status") == "broken" and b.get("stage") == "model"
         and "RuntimeError: smoke: boom" in b.get("errors", []) else 1)' "$WORK/list-broken.json" \
  || fail "/_buildzr/v1/workspaces does not show broken as broken next to a and b: $(cat "$WORK/list-broken.json")"
code="$(status "http://127.0.0.1:$PORT/broken/api/v1/")"
[[ "$code" = 503 ]] || fail "GET /broken/api/v1/ answered $code, expected 503"
echo "503 http://127.0.0.1:$PORT/broken/api/v1/ (broken, no data)"

step "buildzr serve of a project with one workspace (it builds, / redirects)"
mkdir "$WORK/one" && cd "$WORK/one"
mkdir workspaces
example solo >workspaces/solo.py
ONE="$(free_port)"
buildzr serve -p "$ONE" >"$WORK/serve-one.log" 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$ONE/_buildzr/v1/workspaces" "buildzr serve (one workspace)"
code="$(status "http://127.0.0.1:$ONE/")"
[[ "$code" = 302 ]] || fail "GET / answered $code, expected 302"
location="$(curl -sS -o /dev/null -w '%{redirect_url}' --max-time 20 "http://127.0.0.1:$ONE/")"
[[ "$location" = "http://127.0.0.1:$ONE/solo/" ]] || fail "GET / redirects to $location, expected /solo/"
echo "302 http://127.0.0.1:$ONE/ -> /solo/"
get "http://127.0.0.1:$ONE/solo/" "$WORK/solo.html"

step "uvx --from the wheel buildzr build (the isolated route of the docs)"
if command -v uvx >/dev/null 2>&1; then
  # An empty folder and a tool environment of their own: nothing of the venv above is used.
  mkdir -p "$WORK/uvx/workspaces" && cd "$WORK/uvx"
  example model >workspaces/model.py
  PATH="${PATH#"$WORK/venv/bin:"}" uvx --from "$WHEEL" buildzr build
  [[ -f .buildzr/build/model/index.html ]] || fail "uvx buildzr build wrote no .buildzr/build/model/index.html (the viewer is missing)"
  [[ -f .buildzr/build/model/data/index.json ]] || fail "uvx buildzr build wrote no .buildzr/build/model/data/index.json"
else
  echo "uvx not available, skipping the isolated-run check"
fi

echo
echo "SMOKE TEST PASSED: $(basename "$WHEEL")"
