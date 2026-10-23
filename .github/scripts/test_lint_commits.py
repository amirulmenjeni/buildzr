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

    def test_exemptions_are_full_shas_with_a_reason(self) -> None:
        for sha, reason in lint_commits.EXEMPT_COMMITS.items():
            self.assertRegex(sha, r'^[0-9a-f]{40}$')
            self.assertTrue(reason)

    def test_exemptions_are_exactly_the_known_commits(self) -> None:
        self.assertEqual(
            lint_commits.EXEMPT_COMMITS,
            {
                '6a158a8af9598590aa834fd396d94d15ec9c350a': 'header-max-length',
                '29a3c889269753803bdcff3df7c7d4a1ec57b9f4': 'subject-case',
                '06e8d399fcfa9bb8c3bc5160d14df15a82829b7c': 'subject-case',
                '11c9f39156a08e51faa1f0d5f50d6f3e7debd598': 'type-enum',
                '748e7d8d2be69b3f5eecb8a7a8f499367ffa83ea': 'subject-case,type-enum',
                'b1e654f0ab273a7eedf45a002a2169f05d82a263': 'type-enum',
                'c9eb80d75c92bd77072049fb47a9e92422077618': 'subject-case',
                '726bfca6619b4bd1167a974cb1b124afddb5a92c': 'subject-case',
                'c32f55dd3b50d2cafdde5b43e23360f9ee71ff17': 'type-enum',
                '4e15ed0237a710d8db38fc1bf9544045d1d78a74': 'type-enum',
                'a28e6790dd5e16c241fdfc61b43be1c1b0d04709': 'type-enum',
                'bfb9d716badad71e56144888665b61f9cec938f9': 'type-enum',
                '75b42240a3e9cb40c85d700ed2d16c681c919486': 'type-enum',
                '4f34fe519e332633c1b7beef8b5a6a2866d2086c': 'type-enum',
                '60c511a5d489dd0ae813a98df4eacb03f91af437': 'type-enum',
                'c20ebfafe28b897cbd724a3a0e20fa5b612a0106': 'type-enum',
                'c9bb749639299ea053830faee47fecef18fedaa4': 'type-enum',
            },
        )


if __name__ == '__main__':
    unittest.main()
