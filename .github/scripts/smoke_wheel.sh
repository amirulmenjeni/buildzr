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

step "buildzr --version"
WHEEL_VERSION="$(basename "$WHEEL" | cut -d- -f2)"
version_line="$(buildzr --version)" || fail "buildzr --version exited with $?"
echo "$version_line"
[[ "$version_line" = "buildzr $WHEEL_VERSION" ]] \
  || fail "buildzr --version printed '$version_line', expected 'buildzr $WHEEL_VERSION'"

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
# The viewer of a built workspace carries its font and the third-party notices its About view shows, all local.
notices=(.buildzr/build/a/assets/THIRD_PARTY_NOTICES-*.txt)
[[ -f "${notices[0]}" ]] || fail "buildzr build wrote no THIRD_PARTY_NOTICES-*.txt next to the viewer of workspace a"
get "http://127.0.0.1:$PORT/a/assets/$(basename "${notices[0]}")" "$WORK/notices.txt"
grep -q 'SIL OPEN FONT LICENSE Version 1.1' "$WORK/notices.txt" || fail "the viewer's notices lack the Inter font licence"
for weight in 400 700; do
  fonts=(.buildzr/build/a/assets/fonts/inter-latin-$weight-normal-*.woff2)
  [[ -f "${fonts[0]}" ]] || fail "buildzr build wrote no Inter $weight font for workspace a"
  get "http://127.0.0.1:$PORT/a/assets/fonts/$(basename "${fonts[0]}")" "$WORK/inter-$weight.woff2"
done
python -I -c 'import importlib.metadata as m, sys; sys.exit(0 if m.distribution("buildzr").read_text("licenses/THIRD_PARTY_NOTICES.txt") else 1)' \
  || fail "the installed wheel has no THIRD_PARTY_NOTICES.txt in its dist-info"
get "http://127.0.0.1:$PORT/a/api/v1/" "$WORK/api.json"
grep -q '"name":"a"' "$WORK/api.json" || fail "/a/api/v1/ is not the orientation document of workspace a"
# The example has a deployment view: it is built (its scene is in data/index.json) and the API lists it.
grep -q '"v/deployment-view-production-ecommerce"' .buildzr/build/a/data/index.json \
  || fail "buildzr build wrote no scene for the deployment view of workspace a"
get "http://127.0.0.1:$PORT/a/api/v1/views?environment=production" "$WORK/deployment-views.json"
python -I -c 'import json, sys; items = json.load(open(sys.argv[1]))["items"]; sys.exit([(v["key"], v["kind"]) for v in items] != [("deployment-view-production-ecommerce", "deployment")])' \
  "$WORK/deployment-views.json" || fail "/a/api/v1/views?environment=production does not list the deployment view"
get "http://127.0.0.1:$PORT/a/api/v1/element?id=deploy/production/aws/ecs-cluster/web-app" "$WORK/instance.json"
grep -q '"instanceOf":"e-commerce-system/web-app"' "$WORK/instance.json" \
  || fail "/a/api/v1/element does not answer for the container instance deploy/production/aws/ecs-cluster/web-app"
get "http://127.0.0.1:$PORT/_buildzr/v1/workspaces" "$WORK/list.json"
python -I -c 'import json, sys; names = [w["name"] for w in json.load(open(sys.argv[1]))["workspaces"]]; sys.exit(names != ["a", "b"])' \
  "$WORK/list.json" || fail "/_buildzr/v1/workspaces does not list a and b"

step "buildzr serve --example (from a folder with a broken buildzr.yaml; nothing is written there)"
mkdir "$WORK/ex" && cd "$WORK/ex"
printf 'workspaces: [\n' >buildzr.yaml   # not valid YAML: --example must not read it
EXPORT="$(free_port)"
buildzr serve --example -p "$EXPORT" >"$WORK/serve-example.log" 2>&1 &
EXPID=$!
PIDS+=($EXPID)
wait_for "http://127.0.0.1:$EXPORT/_buildzr/v1/workspaces" "buildzr serve --example"
code="$(status "http://127.0.0.1:$EXPORT/")"
[[ "$code" = 302 ]] || fail "GET / answered $code, expected 302"
get "http://127.0.0.1:$EXPORT/example/" "$WORK/example.html"
grep -q 'id="root"' "$WORK/example.html" || fail "/example/ has no viewer root element (id=\"root\")"
get "http://127.0.0.1:$EXPORT/example/api/v1/" "$WORK/example-api.json"
grep -q '"name":"example"' "$WORK/example-api.json" || fail "/example/api/v1/ is not the example workspace"
get "http://127.0.0.1:$EXPORT/example/api/v1/views" "$WORK/example-views.json"
[[ "$(ls -A "$WORK/ex")" = "buildzr.yaml" ]] || fail "serve --example wrote into the working folder: $(ls -A "$WORK/ex")"
kill -TERM "$EXPID"
wait "$EXPID" 2>/dev/null || true
if curl -sS -o /dev/null --max-time 2 "http://127.0.0.1:$EXPORT/" 2>/dev/null; then fail "serve --example still answers after SIGTERM"; fi
echo "serve --example stopped on SIGTERM"
cd "$WORK/run"

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

step "buildzr build of a workspaces: list (one entry with its own k, one data-only entry)"
mkdir -p "$WORK/list/architecture" && cd "$WORK/list"
example billing >architecture/billing.py
example platform >architecture/platform.py
example catalog >architecture/api_catalog.py
example draft >architecture/draft.py   # not listed: never built
cat >buildzr.yaml <<'YAML'
build:
  k: 4
workspaces:
  - architecture/billing.py
  - path: architecture/platform.py
    build:
      k: 9
  - path: architecture/api_catalog.py
    build:
      viewer: false
YAML
buildzr build
python -I -c '
import json, os, sys
out = ".buildzr/build"
names = sorted(os.listdir(out))
k = {n: json.load(open(os.path.join(out, n, "build.json")))["k"] for n in names}
viewer = {n: os.path.isfile(os.path.join(out, n, "index.html")) for n in names}
sys.exit(0 if names == ["billing", "catalog", "platform"] and k == {"billing": 4, "catalog": 4, "platform": 9}
         and viewer == {"billing": True, "catalog": False, "platform": True} else 1)' \
  || fail "the workspaces: list did not build billing (k 4), platform (k 9) and catalog (data only)"
LIST="$(free_port)"
buildzr serve -p "$LIST" >"$WORK/serve-list.log" 2>&1 &
PIDS+=($!)
wait_for "http://127.0.0.1:$LIST/_buildzr/v1/workspaces" "buildzr serve (workspaces: list)"
grep -q '^up to date: billing, catalog, platform$' "$WORK/serve-list.log" \
  || fail "buildzr serve did not find the three listed workspaces up to date"
get "http://127.0.0.1:$LIST/" "$WORK/index-list.html"
grep -q 'href="/catalog/"' "$WORK/index-list.html" && fail "the index page links the data-only workspace to a viewer"
grep -q 'href="/catalog/api/v1/"' "$WORK/index-list.html" || fail "the index page does not link catalog's Model API"
get "http://127.0.0.1:$LIST/_buildzr/v1/workspaces" "$WORK/list-list.json"
python -I -c '
import json, sys
ws = {w["name"]: w for w in json.load(open(sys.argv[1]))["workspaces"]}
sys.exit(0 if ws["catalog"]["viewerUrl"] is None and ws["platform"]["viewerUrl"] == "/platform/" else 1)' \
  "$WORK/list-list.json" || fail "catalog should have viewerUrl null and platform /platform/: $(cat "$WORK/list-list.json")"
echo "catalog: data only (viewerUrl null), platform: k 9"

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
