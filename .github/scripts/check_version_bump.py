"""Validate the version bump of a pull request before it can release.

Usage:
    check_version_bump.py BASE_VERSION HEAD_VERSION < tags
    check_version_bump.py read-version < buildzr/__about__.py

BASE_VERSION is the version on the base branch and HEAD_VERSION the version
that merging the pull request would put on it. Existing tags (e.g. `v0.0.34`)
are read from stdin, one per line.

When the version is unchanged, the check passes silently. Otherwise:

- A final version (e.g. `0.0.35`) or a release candidate (e.g. `0.1.0rc1`)
  must not already be tagged and must be higher than the latest tag, by PEP 440
  ordering (`0.1.0rc1` < `0.1.0rc2` < `0.1.0`). Merging it releases it to PyPI.
- A development version (e.g. `0.0.35.dev0`) must be higher than the latest
  tag. Merging it does not release anything.
- Other canonical PEP 440 versions (`aN`, `bN`, post-releases) pass with a
  notice, because the release workflow skips them.
- Anything else fails: not PEP 440, leading zeros, not in canonical form, or
  with a local version label (`+...`), which PyPI rejects.

Results are printed as GitHub Actions workflow commands and, when
`GITHUB_STEP_SUMMARY` is set, appended to the job summary. Exits with 1 when
the check fails.
"""

import os
import re
import sys
from typing import Iterable, List, Optional

from packaging.version import InvalidVersion, Version

FINAL_VERSION_REGEX = r'^(0|[1-9][0-9]*)(\.(0|[1-9][0-9]*))*$'
RC_VERSION_REGEX = FINAL_VERSION_REGEX[:-1] + r'rc(0|[1-9][0-9]*)$'
# Keep in sync with the "Check for unreleased version" step of
# .github/workflows/release.yml (test_check_version_bump.py enforces this).
RELEASE_VERSION_REGEX = FINAL_VERSION_REGEX[:-1] + r'(rc(0|[1-9][0-9]*))?$'
DEV_VERSION_REGEX = FINAL_VERSION_REGEX[:-1] + r'\.dev(0|[1-9][0-9]*)$'

# The default pattern of hatch's regex version source.
VERSION_FILE_REGEX = (
    r'(?im)^(__version__|VERSION) *= *([\'"])v?(?P<version>.+?)\2'
)


def escape(message: str) -> str:
    """Escape a message for use in a workflow command."""
    return (
        message.replace('%', '%25').replace('\r', '%0D').replace('\n', '%0A')
    )


def summary(message: str) -> None:
    """Append a line to the job summary, if there is one."""
    path = os.environ.get('GITHUB_STEP_SUMMARY')
    if path:
        with open(path, 'a', encoding='utf-8') as f:
            f.write(message + '\n')


def notice(message: str) -> int:
    print(f'::notice title=Version bump::{escape(message)}')
    summary(f'ℹ️ {message}')
    return 0


def warning(message: str) -> int:
    print(f'::warning title=Version bump::{escape(message)}')
    summary(f'⚠️ {message}')
    return 0


def error(message: str) -> int:
    print(f'::error title=Version bump::{escape(message)}')
    summary(f'❌ {message}')
    return 1


def latest_tag(tags: Iterable[str]) -> Optional[str]:
    """Return the highest `v<version>` tag by PEP 440 ordering."""
    versions = []
    for tag in tags:
        if not tag.startswith('v'):
            continue
        try:
            versions.append((Version(tag[1:]), tag))
        except InvalidVersion:
            continue
    return max(versions)[1] if versions else None


def check(base: str, head: str, tags: List[str]) -> int:
    """Check the bump from `base` to `head`; return the exit code."""
    if head == base:
        return 0

    try:
        version = Version(head)
    except InvalidVersion:
        return error(
            f"'{head}' is not a valid PEP 440 version. Set VERSION in "
            "buildzr/__about__.py to a final version such as '0.0.35', a release "
            "candidate such as '0.1.0rc1' or a development version such as "
            "'0.0.35.dev0'."
        )

    is_final = re.match(FINAL_VERSION_REGEX, head) is not None
    is_rc = re.match(RC_VERSION_REGEX, head) is not None
    is_dev = re.match(DEV_VERSION_REGEX, head) is not None
    if not (is_final or is_rc or is_dev) and str(version) != head:
        return error(
            f"'{head}' is not in canonical form (leading zeros or "
            f"non-standard separators). Did you mean '{version}'?"
        )

    if version.local is not None:
        return error(
            f"'{head}' has a local version label, which PyPI rejects. "
            f"Remove the '+{version.local}' suffix."
        )

    tag = f'v{head}'
    latest = latest_tag(tags)
    if (is_final or is_rc) and tag in tags:
        return error(
            f'{tag} is already released. Bump VERSION in '
            'buildzr/__about__.py to a higher version.'
        )
    if latest is not None and version <= Version(latest[1:]):
        return error(
            f"'{head}' is not higher than the latest release {latest}. "
            'Bump VERSION in buildzr/__about__.py above it.'
        )

    status = 0
    try:
        if version < Version(base):
            status = warning(f"'{head}' is lower than the base version '{base}'.")
    except InvalidVersion:
        pass

    if is_final or is_rc:
        note = ' (a release candidate, installed only with `pip install --pre`)' if is_rc else ''
        notice(f'Merging this pull request WILL release {tag} to PyPI{note}.')
    elif is_dev:
        notice(
            f"'{head}' is a development version. Merging this pull request "
            'will NOT release it.'
        )
    else:
        notice(
            f"'{head}' is not a final version or a release candidate. "
            'Merging this pull request will NOT release it, because the '
            'release workflow only publishes final versions and release '
            'candidates (`X.Y.ZrcN`).'
        )
    return status


def read_version(text: str) -> str:
    """Read the version from the contents of `buildzr/__about__.py`."""
    match = re.search(VERSION_FILE_REGEX, text)
    if match is None:
        raise ValueError('No VERSION found in buildzr/__about__.py')
    return match.group('version')


def main(argv: List[str]) -> int:
    if argv == ['read-version']:
        print(read_version(sys.stdin.read()))
        return 0
    if len(argv) != 2:
        print(__doc__, file=sys.stderr)
        return 2
    return check(argv[0], argv[1], sys.stdin.read().split())


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
