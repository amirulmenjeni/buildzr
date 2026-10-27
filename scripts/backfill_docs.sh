#!/usr/bin/env bash
# Deploy the docs of every final release since 1.0.0 to the gh-pages branch, oldest first, so that the highest one
# is /latest/; then publish the roadmap of this checkout at /roadmap/ and the root files.
#
# Usage (from the repository root of an up-to-date checkout of master, tags fetched, `uv` and Node.js 22 on PATH):
#
#   scripts/backfill_docs.sh [--from vX.Y.Z] [--push]
#
# Each tag is built from its own checkout with its own uv.lock (see `deploy` in scripts/docs_pages.sh). A tag that
# cannot be built is skipped, and the summary at the end says which and why to look in the log above it. Release
# candidates and other pre-releases (v1.0.0rc1, ...) are skipped: the site shows final releases only.
#
# Idempotent: a version deployed again replaces its folder, and the roadmap and the root files are replaced. Without
# --push, everything is committed to the LOCAL gh-pages branch only; preview it with `uv run mike serve` (or check out
# the branch and serve it with any static server). With --push, the branch is pushed to origin once, at the end, and
# only when every tag was deployed.

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
FROM="v1.0.0"
PUSH=false
while [[ $# -gt 0 ]]; do
  case "$1" in
    --from) FROM="${2:?--from needs a tag}"; shift 2 ;;
    --push) PUSH=true; shift ;;
    -h|--help) sed -n '2,16p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "backfill_docs: unknown argument $1" >&2; exit 2 ;;
  esac
done

from="${FROM#v}"
deployed=() skipped=() failed=()
for tag in $(git -C "$ROOT" tag --list 'v*' | sort -V); do
  version="${tag#v}"
  if [[ ! "$version" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]]; then
    [[ "$(printf '%s\n%s\n' "$from" "${version%%[a-z]*}" | sort -V | head -1)" == "$from" ]] &&
      skipped+=("$tag (not a final release)")
    continue
  fi
  [[ "$(printf '%s\n%s\n' "$from" "$version" | sort -V | head -1)" == "$from" ]] || continue
  echo "backfill_docs: deploying $tag" >&2
  if "$ROOT/scripts/docs_pages.sh" deploy "$tag"; then
    deployed+=("$tag")
  else
    failed+=("$tag")
  fi
done

"$ROOT/scripts/docs_pages.sh" roadmap

echo
echo "Deployed: ${deployed[*]:-none}"
echo "Skipped:  ${skipped[*]:-none}"
echo "Failed:   ${failed[*]:-none} (see the log above)"

if $PUSH; then
  if [[ ${#failed[@]} -gt 0 ]]; then
    echo "backfill_docs: not pushing, a tag failed" >&2
    exit 1
  fi
  "$ROOT/scripts/docs_pages.sh" push
else
  echo "Nothing pushed. Push with: scripts/docs_pages.sh push"
fi
[[ ${#failed[@]} -eq 0 ]]
