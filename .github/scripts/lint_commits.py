"""Lint the commit messages of a pull request with commitlint.

Usage:
    lint_commits.py BASE_SHA HEAD_SHA

Every commit in BASE_SHA..HEAD_SHA is linted with the repository's commitlint
configuration, except the commits in EXEMPT_COMMITS. Those commits predate the
check, are already in the shared history of release/1.0 and cannot be reworded
without rewriting it. A commit is exempt only when its full SHA is listed, so
a new commit, even one with the same message, is always linted.

Set COMMITLINT to the commitlint command (default: `commitlint`). Exits with 1
when a commit does not pass.
"""

import os
import shlex
import subprocess
import sys
from typing import Callable, Dict, List, Optional, Sequence

# Full SHA -> the rule it breaks. Do not add to this without a reason: new
# commits must pass.
EXEMPT_COMMITS: Dict[str, str] = {
    '6a158a8af9598590aa834fd396d94d15ec9c350a': 'header-max-length',
    '29a3c889269753803bdcff3df7c7d4a1ec57b9f4': 'subject-case',
    '06e8d399fcfa9bb8c3bc5160d14df15a82829b7c': 'subject-case',
}

Linter = Callable[[str], bool]


def git(*args: str, cwd: Optional[str] = None) -> str:
    return subprocess.run(
        ['git', *args], cwd=cwd, check=True, capture_output=True, text=True
    ).stdout


def commits_in_range(base: str, head: str, cwd: Optional[str] = None) -> List[str]:
    """Return the SHAs reachable from head and not from base, oldest first."""
    return git('rev-list', '--reverse', f'{base}..{head}', cwd=cwd).split()


def commitlint_linter(command: Sequence[str], cwd: Optional[str] = None) -> Linter:
    """Return a linter that runs commitlint on the message of a commit."""

    def lint(sha: str) -> bool:
        message = git('log', '-1', '--format=%B', sha, cwd=cwd)
        result = subprocess.run(
            list(command), input=message, cwd=cwd, text=True,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        )
        if result.returncode != 0:
            print(result.stdout)
        return result.returncode == 0

    return lint


def lint_commits(
    base: str,
    head: str,
    lint: Linter,
    exempt: Dict[str, str] = EXEMPT_COMMITS,
    cwd: Optional[str] = None,
) -> List[str]:
    """Lint the commits in base..head and return the SHAs that failed."""
    failed = []
    for sha in commits_in_range(base, head, cwd):
        if sha in exempt:
            print(f'{sha[:7]}: exempt ({exempt[sha]})')
        elif lint(sha):
            print(f'{sha[:7]}: ok')
        else:
            print(f'::error::{sha[:7]}: commit message failed commitlint')
            failed.append(sha)
    return failed


def main(argv: List[str]) -> int:
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 2
    command = shlex.split(os.environ.get('COMMITLINT', 'commitlint'))
    return 1 if lint_commits(argv[1], argv[2], commitlint_linter(command)) else 0


if __name__ == '__main__':
    sys.exit(main(sys.argv))
