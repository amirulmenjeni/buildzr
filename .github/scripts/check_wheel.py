"""Fail unless a built wheel (and optionally sdist) ships what `buildzr build` needs.

Usage:
    check_wheel.py DIST_DIR [--sdist]
    check_wheel.py path/to/buildzr-X.Y.Z-py3-none-any.whl [--sdist]

DIST_DIR is searched for exactly one `buildzr-*.whl` (and, with `--sdist`,
exactly one `buildzr-*.tar.gz`). The viewer bundle is gitignored build output,
so a build made without `npm run build` in `viewer/` silently lacks it. This
check makes such a build fail before it can be published.

Every archive must contain the viewer (`index.html` and a JS bundle), the five
JSON schemas, the modules of `buildzr build` and `buildzr serve` (`cli.py`,
`build.py`, `serve.py`) and the layout's Node runner with its vendored elkjs
bundle. The wheel version
must equal the version in `buildzr/__about__.py`. Stdlib only.
"""

import re
import sys
import tarfile
import zipfile
from pathlib import Path
from typing import Callable, List, Optional

ROOT = Path(__file__).resolve().parents[2]
SITE = 'buildzr/site'
REQUIRED = [
    f'{SITE}/static/index.html',
    f'{SITE}/cli.py',
    f'{SITE}/build.py',
    f'{SITE}/serve.py',
    f'{SITE}/layout/runner.mjs',
    f'{SITE}/layout/vendor/elk.bundled.js',
] + [
    f'{SITE}/schema/{name}.schema.json'
    for name in ('config', 'index', 'levels', 'model', 'scene')
]
ASSET_JS = re.compile(rf'^{SITE}/static/assets/[^/]+\.js$')


def source_version() -> str:
    text = (ROOT / 'buildzr' / '__about__.py').read_text(encoding='utf-8')
    match = re.search(r'(?im)^(__version__|VERSION) *= *([\'"])v?(?P<version>.+?)\2', text)
    if match is None:
        raise ValueError('No VERSION found in buildzr/__about__.py')
    return match.group('version')


def problems(kind: str, names: List[str], prefix: str = '') -> List[str]:
    """List what is missing from the file `names` of an archive."""
    names = [n[len(prefix):] if n.startswith(prefix) else n for n in names]
    found = set(names)
    result = [f'{kind}: missing {path}' for path in REQUIRED if path not in found]
    if not any(ASSET_JS.match(n) for n in names):
        result.append(f'{kind}: missing a JS bundle in {SITE}/static/assets/')
    if not any(p.startswith(f"{SITE}/static/") for p in found):
        result.append(
            f'{kind}: no viewer files at all. Build the viewer first: '
            '`cd viewer && npm ci && npm run build`.'
        )
    return result


def check_wheel(path: Path, expected: str) -> List[str]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        result = problems('wheel', names)
        metadata = [n for n in names if re.fullmatch(r'[^/]+\.dist-info/METADATA', n)]
        if len(metadata) != 1:
            return result + ['wheel: expected exactly one .dist-info/METADATA']
        match = re.search(r'(?m)^Version: (.+)$', z.read(metadata[0]).decode('utf-8'))
    version = match.group(1).strip() if match else None
    if version != expected:
        result.append(
            f"wheel: version is '{version}' but buildzr/__about__.py says '{expected}'."
        )
    return result


def check_sdist(path: Path) -> List[str]:
    with tarfile.open(path) as t:
        names = t.getnames()
    # Members are prefixed by the `buildzr-X.Y.Z/` folder.
    return problems('sdist', names, prefix=names[0].split('/')[0] + '/' if names else '')


def pick(target: Path, pattern: str, label: str, errors: List[str]) -> Optional[Path]:
    if target.is_file():
        return target
    files = sorted(target.glob(pattern))
    if len(files) != 1:
        errors.append(f'{label}: expected exactly one {pattern} in {target}, found {len(files)}.')
        return None
    return files[0]


def main(argv: List[str]) -> int:
    args = [a for a in argv if a != '--sdist']
    with_sdist = len(args) != len(argv)
    if len(args) != 1:
        print(__doc__, file=sys.stderr)
        return 2
    target = Path(args[0])
    errors: List[str] = []
    checks: List[Callable[[], List[str]]] = []

    wheel = pick(target, 'buildzr-*.whl', 'wheel', errors)
    if wheel is not None:
        checks.append(lambda: check_wheel(wheel, source_version()))
    if with_sdist:
        sdist = pick(target, 'buildzr-*.tar.gz', 'sdist', errors)
        if sdist is not None:
            checks.append(lambda: check_sdist(sdist))
    for check in checks:
        errors.extend(check())

    for message in errors:
        print(f'::error title=Package check::{message}')
    if errors:
        print(f'FAILED: {len(errors)} problem(s) found in the built package.', file=sys.stderr)
        return 1
    print(f'OK: {wheel.name}' + (f' and {sdist.name}' if with_sdist else '') + ' contain the viewer, schemas, layout and command modules.')
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
