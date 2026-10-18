"""Tests for check_wheel.py.

Run with:
    python .github/scripts/test_check_wheel.py
"""

import subprocess
import sys
import tarfile
import tempfile
import unittest
import zipfile
from pathlib import Path
from typing import Iterable, List

SCRIPTS = Path(__file__).resolve().parent
SCRIPT = SCRIPTS / 'check_wheel.py'

sys.path.insert(0, str(SCRIPTS))
import check_wheel  # noqa: E402

VERSION = check_wheel.source_version()
VIEWER = [
    'buildzr/site/static/index.html',
    'buildzr/site/static/assets/index-abc.js',
    'buildzr/site/static/assets/index-abc.css',
]
OTHER = [path for path in check_wheel.REQUIRED if '/static/' not in path] + ['buildzr/__init__.py']


def make_wheel(folder: Path, files: Iterable[str], version: str = VERSION) -> Path:
    path = folder / f'buildzr-{version}-py3-none-any.whl'
    with zipfile.ZipFile(path, 'w') as z:
        for name in files:
            z.writestr(name, '')
        z.writestr(
            f'buildzr-{version}.dist-info/METADATA',
            f'Metadata-Version: 2.4\nName: buildzr\nVersion: {version}\n',
        )
    return path


def make_sdist(folder: Path, files: Iterable[str]) -> Path:
    path = folder / f'buildzr-{VERSION}.tar.gz'
    src = folder / 'sdist-src'
    with tarfile.open(path, 'w:gz') as t:
        for name in files:
            file = src / f'buildzr-{VERSION}' / name
            file.parent.mkdir(parents=True, exist_ok=True)
            file.write_text('')
            t.add(file, arcname=f'buildzr-{VERSION}/{name}')
    return path


def run(*args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], capture_output=True, text=True
    )


class TestCheckWheel(unittest.TestCase):

    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.tmp = Path(self._tmp.name)

    def test_good_wheel(self) -> None:
        make_wheel(self.tmp, VIEWER + OTHER)
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        self.assertIn('OK:', result.stdout)

    def test_wheel_without_viewer(self) -> None:
        make_wheel(self.tmp, OTHER)
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 1)
        self.assertIn('wheel: missing buildzr/site/static/index.html', result.stdout)
        self.assertIn('wheel: missing a JS bundle', result.stdout)
        self.assertIn('npm run build', result.stdout)

    def test_wheel_without_js_bundle(self) -> None:
        make_wheel(self.tmp, [VIEWER[0]] + OTHER)
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 1)
        self.assertIn('wheel: missing a JS bundle', result.stdout)

    def test_wheel_without_schema_or_module(self) -> None:
        files: List[str] = [
            f for f in VIEWER + OTHER
            if not f.endswith(('model.schema.json', 'serve.py'))
        ]
        make_wheel(self.tmp, files)
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 1)
        self.assertIn('missing buildzr/site/schema/model.schema.json', result.stdout)
        self.assertIn('missing buildzr/site/serve.py', result.stdout)

    def test_wrong_version(self) -> None:
        make_wheel(self.tmp, VIEWER + OTHER, version='9.9.9')
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 1)
        self.assertIn(f"version is '9.9.9' but buildzr/__about__.py says '{VERSION}'", result.stdout)

    def test_wheel_path_argument(self) -> None:
        wheel = make_wheel(self.tmp, VIEWER + OTHER)
        self.assertEqual(run(str(wheel)).returncode, 0)

    def test_no_wheel(self) -> None:
        result = run(str(self.tmp))
        self.assertEqual(result.returncode, 1)
        self.assertIn('expected exactly one buildzr-*.whl', result.stdout)

    def test_sdist(self) -> None:
        make_wheel(self.tmp, VIEWER + OTHER)
        make_sdist(self.tmp, VIEWER + OTHER)
        result = run(str(self.tmp), '--sdist')
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_sdist_without_viewer(self) -> None:
        make_wheel(self.tmp, VIEWER + OTHER)
        make_sdist(self.tmp, OTHER)
        result = run(str(self.tmp), '--sdist')
        self.assertEqual(result.returncode, 1)
        self.assertIn('sdist: missing buildzr/site/static/index.html', result.stdout)
        # Without --sdist the sdist is not looked at.
        self.assertEqual(run(str(self.tmp)).returncode, 0)

    def test_usage(self) -> None:
        self.assertEqual(run().returncode, 2)


if __name__ == '__main__':
    unittest.main(verbosity=2)
