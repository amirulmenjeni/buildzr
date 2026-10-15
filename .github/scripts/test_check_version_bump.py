"""Table tests for check_version_bump.py.

Run with:
    uv run --no-project --with packaging==26.3 python .github/scripts/test_check_version_bump.py
"""

import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / 'check_version_bump.py'
RELEASE_WORKFLOW = SCRIPTS.parent / 'workflows' / 'release.yml'

sys.path.insert(0, str(SCRIPTS))
import check_version_bump  # noqa: E402

TAGS = ['v0.0.32', 'v0.0.33', 'v0.0.34']

# (base, head, tags, exit code, expected annotation or None for no output)
CASES = [
    ('0.0.34', '0.0.34', TAGS, 0, None),
    ('0.0.34', '0.0.35', TAGS, 0, '::notice title=Version bump::Merging this pull request WILL release v0.0.35'),
    ('0.0.34', '0.0.35.dev0', TAGS, 0, '::notice title=Version bump::\'0.0.35.dev0\' is a development version'),
    ('0.0.34', '0.0.34.dev0', TAGS, 1, '::error title=Version bump::\'0.0.34.dev0\' is not higher than the latest release v0.0.34'),
    ('0.0.34', '0.0.035', TAGS, 1, '::error title=Version bump::\'0.0.035\' is not in canonical form'),
    ('0.0.34', '0.0.035.dev0', TAGS, 1, '::error title=Version bump::\'0.0.035.dev0\' is not in canonical form'),
    ('0.0.34', '0.0.35dev0', TAGS, 1, '::error title=Version bump::\'0.0.35dev0\' is not in canonical form'),
    ('0.0.34', '0.0.35rc1', TAGS, 0, '::notice title=Version bump::\'0.0.35rc1\' is not a final version'),
    ('0.0.34', '0.0.34.post1', TAGS, 0, '::notice title=Version bump::\'0.0.34.post1\' is not a final version'),
    ('0.0.34', '0.0.35+local', TAGS, 1, '::error title=Version bump::\'0.0.35+local\' has a local version label'),
    ('0.0.34', 'garbage', TAGS, 1, '::error title=Version bump::\'garbage\' is not a valid PEP 440 version'),
    ('0.0.34', '0.0.35 ', TAGS, 1, '::error title=Version bump::\'0.0.35 \' is not in canonical form'),
    ('0.0.35.dev0', '0.0.34', TAGS, 1, '::error title=Version bump::v0.0.34 is already released'),
    ('0.0.34', '0.0.33', TAGS, 1, '::error title=Version bump::v0.0.33 is already released'),
    ('0.0.34', '0.0.33', ['v0.0.34'], 1, '::error title=Version bump::\'0.0.33\' is not higher than the latest release v0.0.34'),
    ('0.0.34', '1.0.0', TAGS, 0, '::notice title=Version bump::Merging this pull request WILL release v1.0.0'),
    ('0.0.9', '0.0.10', ['v0.0.8', 'v0.0.9'], 0, '::notice title=Version bump::Merging this pull request WILL release v0.0.10'),
    ('0.0.10', '0.0.11', ['v0.0.9', 'v0.0.10'], 0, '::notice title=Version bump::Merging this pull request WILL release v0.0.11'),
    ('0.0.10.dev0', '0.0.9', ['v0.0.10'], 1, '::error title=Version bump::\'0.0.9\' is not higher than the latest release v0.0.10'),
    ('0.1.0.dev0', '0.0.35', TAGS, 0, '::warning title=Version bump::\'0.0.35\' is lower than the base version \'0.1.0.dev0\''),
    ('0.0.34', '0.0.35', [], 0, '::notice title=Version bump::Merging this pull request WILL release v0.0.35'),
    ('0.0.34', '0.0.35', TAGS + ['latest', 'vnext'], 0, '::notice title=Version bump::Merging this pull request WILL release v0.0.35'),
]


def run(base: str, head: str, tags: list) -> subprocess.CompletedProcess:
    env = {k: v for k, v in os.environ.items() if k != 'GITHUB_STEP_SUMMARY'}
    return subprocess.run(
        [sys.executable, str(SCRIPT), base, head],
        input='\n'.join(tags) + '\n',
        capture_output=True,
        text=True,
        env=env,
    )


class TestCheckVersionBump(unittest.TestCase):

    def test_table(self) -> None:
        for base, head, tags, code, annotation in CASES:
            with self.subTest(base=base, head=head, tags=tags):
                result = run(base, head, tags)
                result_lines = result.stdout.strip().splitlines()
                print(
                    f'{base!r:16} -> {head!r:16} tags={",".join(tags) or "-":32}'
                    f' exit={result.returncode} {result.stdout.strip() or "(silent)"}'
                )
                self.assertEqual(result.returncode, code, result.stdout + result.stderr)
                if annotation is None:
                    self.assertEqual(result.stdout, '')
                else:
                    self.assertTrue(
                        any(line.startswith(annotation) for line in result_lines),
                        result.stdout,
                    )

    def test_final_regex_matches_release_workflow(self) -> None:
        workflow = RELEASE_WORKFLOW.read_text(encoding='utf-8')
        match = re.search(r'if \[\[ ! "\$VERSION" =~ (\S+) \]\]', workflow)
        assert match is not None
        self.assertEqual(match.group(1), check_version_bump.FINAL_VERSION_REGEX)

    def test_read_version(self) -> None:
        self.assertEqual(
            check_version_bump.read_version('# x\nVERSION = "0.0.34"\n'),
            '0.0.34',
        )
        self.assertEqual(
            check_version_bump.read_version("VERSION = 'v0.0.35.dev0'\n"),
            '0.0.35.dev0',
        )
        with self.assertRaises(ValueError):
            check_version_bump.read_version('NAME = "buildzr"\n')

    def test_summary(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            summary = Path(tmp) / 'summary.md'
            env = dict(os.environ, GITHUB_STEP_SUMMARY=str(summary))
            subprocess.run(
                [sys.executable, str(SCRIPT), '0.0.34', '0.0.35'],
                input='v0.0.34\n', capture_output=True, text=True, env=env, check=True,
            )
            self.assertIn('WILL release v0.0.35', summary.read_text(encoding='utf-8'))


if __name__ == '__main__':
    unittest.main(verbosity=2)
