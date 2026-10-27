#!/usr/bin/env bash
# Publish the documentation to the gh-pages branch that GitHub Pages serves at https://buildzr.dev.
#
# Usage (from the repository root of a checkout of master, with `uv` and Node.js 22 on PATH):
#
#   scripts/docs_pages.sh deploy <tag> [--push]   Build the docs of a release tag (v1.2.3) from its own checkout and
#                                                  deploy them with mike to /<version>/. The highest release is also
#                                                  /latest/, the default of the site.
#   scripts/docs_pages.sh roadmap [--push]         Build the roadmap of this checkout (mkdocs-roadmap.yml) and put it
#                                                  at /roadmap/.
#   scripts/docs_pages.sh root [--push]            Put CNAME, .nojekyll and 404.html (scripts/pages/) at the root.
#   scripts/docs_pages.sh push                     Push the gh-pages branch to origin.
#
# Every command commits to the LOCAL gh-pages branch only, and also refreshes the root files. Nothing leaves the
# machine unless --push is given (or the push command is run). Release candidates and other pre-releases are refused:
# the site shows final releases only. The workflows docs-publish.yml and docs-roadmap.yml run these commands, and
# scripts/backfill_docs.sh runs `deploy` for every release.
#
# Environment: DOCS_BRANCH (gh-pages), DOCS_REMOTE (origin), DOCS_CNAME (buildzr.dev).

set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BRANCH="${DOCS_BRANCH:-gh-pages}"
REMOTE="${DOCS_REMOTE:-origin}"
CNAME="${DOCS_CNAME:-buildzr.dev}"
#: The mike of this checkout's uv.lock, also used to deploy older tags whose lock has none.
MIKE_VERSION="$(sed -n '/^name = "mike"$/{n;s/^version = "\(.*\)"$/\1/p;}' "$ROOT/uv.lock")"

WORK="$(mktemp -d)"
cleanup() {
  local wt
  for wt in "$WORK"/*/; do
    [[ -d "$wt" ]] && git -C "$ROOT" worktree remove --force "$wt" >/dev/null 2>&1 || true
  done
  rm -rf "$WORK"
  git -C "$ROOT" worktree prune
}
trap cleanup EXIT

die() { echo "docs_pages: $*" >&2; exit 1; }
log() { echo "docs_pages: $*" >&2; }

# Make the local branch current with the remote one, if the remote has it. A local branch that is ahead (commits not
# pushed yet) is kept; one that has diverged is an error.
sync_branch() {
  if git -C "$ROOT" ls-remote --exit-code --heads "$REMOTE" "$BRANCH" >/dev/null 2>&1; then
    git -C "$ROOT" fetch -q "$REMOTE" "+refs/heads/$BRANCH:refs/remotes/$REMOTE/$BRANCH"
    local remote="refs/remotes/$REMOTE/$BRANCH"
    if ! git -C "$ROOT" rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
      git -C "$ROOT" branch -q --no-track "$BRANCH" "$remote"
    elif git -C "$ROOT" merge-base --is-ancestor "refs/heads/$BRANCH" "$remote"; then
      git -C "$ROOT" update-ref "refs/heads/$BRANCH" "$remote"
    elif ! git -C "$ROOT" merge-base --is-ancestor "$remote" "refs/heads/$BRANCH"; then
      die "the local $BRANCH and $REMOTE/$BRANCH have diverged; reset the local branch to $REMOTE/$BRANCH first"
    fi
  fi
  if ! git -C "$ROOT" rev-parse -q --verify "refs/heads/$BRANCH" >/dev/null; then
    local empty
    empty="$(git -C "$ROOT" hash-object -t tree /dev/null)"
    git -C "$ROOT" branch -q "$BRANCH" "$(git -C "$ROOT" commit-tree "$empty" -m "Start the $BRANCH branch")"
  fi
}

# Run a command inside a checkout of the branch, then commit what it changed (nothing to commit, no commit).
edit_branch() {
  local message="$1"; shift
  local dir="$WORK/pages"
  git -C "$ROOT" worktree add -q "$dir" "$BRANCH"
  (cd "$dir" && "$@")
  git -C "$dir" add -A
  if ! git -C "$dir" diff --cached --quiet; then
    git -C "$dir" commit -q -m "$message"
    log "committed to $BRANCH: $message"
  fi
  git -C "$ROOT" worktree remove --force "$dir"
}

put_root_files() {
  printf '%s\n' "$CNAME" > CNAME
  touch .nojekyll
  cp "$ROOT/scripts/pages/404.html" 404.html
}

cmd_root() {
  edit_branch "Update the root files (CNAME, .nojekyll, 404.html)" put_root_files
}

# The versions of the branch's versions.json, one per line.
published_versions() {
  git -C "$ROOT" show "$BRANCH:versions.json" 2>/dev/null |
    grep -o '"version": *"[^"]*"' | sed 's/.*"\([^"]*\)"$/\1/' || true
}

# The version that "latest" points to, if any.
latest_version() {
  git -C "$ROOT" show "$BRANCH:versions.json" 2>/dev/null | tr -d '\n ' |
    grep -o '{[^{}]*"aliases":\[[^]]*"latest"[^]]*\][^{}]*}' | grep -o '"version":"[^"]*"' | cut -d'"' -f4 || true
}

# Older tags have no version selector and no outdated banner; add both (and Material's outdated script, fixed)
# without touching the content.
add_version_selector() {
  if ! grep -q 'provider: mike' mkdocs.yml; then
    if grep -q '^extra:' mkdocs.yml; then
      sed -i.bak 's/^extra:$/extra:\
  version:\
    provider: mike\
    default: latest/' mkdocs.yml && rm mkdocs.yml.bak
    else
      printf '\nextra:\n  version:\n    provider: mike\n    default: latest\n' >> mkdocs.yml
    fi
    log "added the version selector to mkdocs.yml of this tag"
  fi
  if [[ -f overrides/main.html ]] && ! grep -q '{% block outdated %}' overrides/main.html; then
    sed -n '/{% block outdated %}/,/{% endblock %}/p' "$ROOT/overrides/main.html" |
      { echo; cat; } >> overrides/main.html
    log "added the outdated banner to overrides/main.html of this tag"
  fi
  local partial=overrides/partials/javascripts/outdated.html
  if [[ -d overrides && ! -f "$partial" ]]; then
    mkdir -p "$(dirname "$partial")"
    cp "$ROOT/$partial" "$partial"
    log "added the fixed outdated script to $partial of this tag"
  fi
}

cmd_deploy() {
  local tag="$1"
  [[ "$tag" =~ ^v(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)$ ]] ||
    die "'$tag' is not the tag of a final release (vX.Y.Z); release candidates are not published to the docs"
  local version="${tag#v}"
  git -C "$ROOT" rev-parse -q --verify "refs/tags/$tag^{commit}" >/dev/null || die "no tag $tag (fetch the tags)"
  [[ -n "$MIKE_VERSION" ]] || die "no mike in $ROOT/uv.lock"

  local latest highest
  latest="$(latest_version)"
  highest="$( { published_versions; echo "$version"; } | grep -E '^[0-9]+(\.[0-9]+)*$' | sort -V | tail -1)"

  local src="$WORK/$tag"
  git -C "$ROOT" worktree add -q --detach "$src" "$tag"
  (
    cd "$src"
    # The tag's own toolchain: its uv.lock, its viewer, its Run Code script. mike is added when the lock has none.
    uv sync -q --extra docs --locked
    uv run --no-sync python -c 'import mike' 2>/dev/null || uv pip install -q "mike==$MIKE_VERSION"
    (cd viewer && npm ci --no-audit --no-fund --loglevel=error)
    uv run --no-sync python scripts/build_docs_assets.py
    add_version_selector
    uv run --no-sync mkdocs build --strict --quiet
    if [[ "$version" == "$highest" ]]; then
      uv run --no-sync mike deploy --branch "$BRANCH" --alias-type copy --update-aliases \
        --title "$version (latest)" "$version" latest
      uv run --no-sync mike set-default --branch "$BRANCH" latest
      if [[ -n "$latest" && "$latest" != "$version" ]]; then
        uv run --no-sync mike retitle --branch "$BRANCH" "$latest" "$latest"
      fi
    else
      uv run --no-sync mike deploy --branch "$BRANCH" --alias-type copy --title "$version" "$version"
    fi
  )
  git -C "$ROOT" worktree remove --force "$src"

  # The roadmap is not versioned: it lives at /roadmap/ (see `roadmap`), and 404.html sends /<version>/roadmap/ there.
  remove_versioned_roadmap() {
    rm -rf "$version/roadmap"
    if [[ "$version" == "$highest" ]]; then rm -rf latest/roadmap; fi
    put_root_files
  }
  edit_branch "Remove the versioned roadmap of $version; update the root files" remove_versioned_roadmap
  log "deployed $tag to /$version/$([[ "$version" == "$highest" ]] && echo ' and /latest/')"
}

cmd_roadmap() {
  local out="$WORK/roadmap-site"
  (cd "$ROOT" && uv run mkdocs build --strict --quiet --config-file mkdocs-roadmap.yml --site-dir "$out")
  rm -f "$out/404.html"
  put_roadmap() { rm -rf roadmap; cp -R "$out" roadmap; put_root_files; }
  edit_branch "Publish the roadmap of $(git -C "$ROOT" rev-parse --short HEAD) at /roadmap/" put_roadmap
}

cmd_push() {
  git -C "$ROOT" push "$REMOTE" "refs/heads/$BRANCH:refs/heads/$BRANCH"
}

main() {
  local command="${1:-}" push=false args=()
  [[ $# -gt 0 ]] && shift
  local a
  for a in "$@"; do
    case "$a" in
      --push) push=true ;;
      -*) die "unknown option $a" ;;
      *) args+=("$a") ;;
    esac
  done
  case "$command" in
    deploy) [[ ${#args[@]} -eq 1 ]] || die "usage: deploy <tag> [--push]"; sync_branch; cmd_deploy "${args[0]}" ;;
    roadmap) sync_branch; cmd_roadmap ;;
    root) sync_branch; cmd_root ;;
    push) cmd_push; return ;;
    *) sed -n '2,20p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//' >&2; exit 2 ;;
  esac
  if $push; then cmd_push; fi
}

main "$@"
