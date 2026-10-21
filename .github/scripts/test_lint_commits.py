"""Tests for lint_commits.py.

Run with:
    python .github/scripts/test_lint_commits.py
"""

import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from typing import List

SCRIPTS = Path(__file__).resolve().parent

sys.path.insert(0, str(SCRIPTS))
import lint_commits  # noqa: E402

BAD = 'Bad message'
GOOD = 'docs: add a note'


def run(cwd: str, *args: str) -> str:
    return subprocess.run(
        ['git', '-c', 'user.name=t', '-c', 'user.email=t@example.com', *args],
        cwd=cwd, check=True, capture_output=True, text=True,
    ).stdout.strip()


def commit(cwd: str, message: str) -> str:
    run(cwd, 'commit', '--allow-empty', '-m', message)
    return run(cwd, 'rev-parse', 'HEAD')


class LintCommitsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.cwd = self.tmp.name
        run(self.cwd, 'init', '-q')
        self.base = commit(self.cwd, 'chore: base')
        self.linted: List[str] = []

    def lint(self, sha: str) -> bool:
        message = run(self.cwd, 'log', '-1', '--format=%B', sha)
        self.linted.append(sha)
        return message == GOOD

    def check(self, head: str, exempt: dict) -> List[str]:  # type: ignore[type-arg]
        return lint_commits.lint_commits(
            self.base, head, self.lint, exempt, self.cwd
        )

    def test_exempt_commit_is_not_linted(self) -> None:
        old = commit(self.cwd, BAD)
        self.assertEqual(self.check(old, {old: 'subject-case'}), [])
        self.assertEqual(self.linted, [])

    def test_new_invalid_commit_fails_next_to_exempt_one(self) -> None:
        old = commit(self.cwd, BAD)
        new = commit(self.cwd, BAD)
        self.assertEqual(self.check(new, {old: 'subject-case'}), [new])

    def test_same_message_as_exempt_commit_still_fails(self) -> None:
        old = commit(self.cwd, BAD)
        self.assertEqual(self.check(old, {}), [old])
        new = commit(self.cwd, BAD)
        self.assertEqual(self.check(new, {old: 'subject-case'}), [new])

    def test_abbreviated_sha_does_not_exempt(self) -> None:
        old = commit(self.cwd, BAD)
        self.assertEqual(self.check(old, {old[:7]: 'subject-case'}), [old])

    def test_valid_commit_passes(self) -> None:
        self.assertEqual(self.check(commit(self.cwd, GOOD), {}), [])

    def test_exemptions_are_exactly_the_three_known_commits(self) -> None:
        self.assertEqual(
            sorted(lint_commits.EXEMPT_COMMITS),
            [
                '06e8d399fcfa9bb8c3bc5160d14df15a82829b7c',
                '29a3c889269753803bdcff3df7c7d4a1ec57b9f4',
                '6a158a8af9598590aa834fd396d94d15ec9c350a',
            ],
        )


if __name__ == '__main__':
    unittest.main()
