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
`build.py`, `serve.py`), the built example of `buildzr serve --example`
(`example/build.json`, `example/data/index.json`) and the layout's Node runner
with its vendored elkjs bundle. Both also carry the third-party notices:
the viewer's copy (`static/assets/THIRD_PARTY_NOTICES-<hash>.txt`, which its About
view reads) and `THIRD_PARTY_NOTICES.txt` where users find it, in the wheel's
`.dist-info/licenses/` and at the root of the sdist. The wheel version
must equal the version in `buildzr/__about__.py`. Every structurizr/themes
URL in a text file of the package (`buildzr/`) in either archive names the commit that
`buildzr/themes/assets.py` pins (`THEMES_COMMIT`), never a branch or a tag,
and neither carries the theme icons themselves (the build fetches the ones a
workspace uses). The agent skill (`skills/`) ships in
the sdist, whose tests read it, and never in the wheel. Stdlib only.
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
    f'{SITE}/example/build.json',
    f'{SITE}/example/data/index.json',
    'buildzr/themes/assets.py',
] + [
    f'{SITE}/schema/{name}.schema.json'
    for name in ('branding', 'build', 'config', 'index', 'levels', 'model', 'scene')
]
SKILL = 'skills/buildzr/SKILL.md'
NOTICES = 'THIRD_PARTY_NOTICES.txt'
ASSET_JS = re.compile(rf'^{SITE}/static/assets/[^/]+\.js$')
ASSET_NOTICES = re.compile(rf'^{SITE}/static/assets/THIRD_PARTY_NOTICES-[^/]+\.txt$')
WHEEL_NOTICES = re.compile(rf'^[^/]+\.dist-info/licenses/{re.escape(NOTICES)}$')
THEMES_REF = re.compile(r'(?:raw\.githubusercontent\.com|github\.com)/structurizr/themes/(?:(?:raw|blob|tree)/)?'
                        r'([^/\s"\'{]+)/')
TEXT = ('.py', '.json', '.txt', '.md', '.js', '.html', '.css', '.mjs')
ICONS = re.compile(r'^buildzr/themes/.+\.(png|svg|jpe?g|gif|webp)$', re.I)


def source_version() -> str:
    text = (ROOT / 'buildzr' / '__about__.py').read_text(encoding='utf-8')
    match = re.search(r'(?im)^(__version__|VERSION) *= *([\'"])v?(?P<version>.+?)\2', text)
    if match is None:
        raise ValueError('No VERSION found in buildzr/__about__.py')
    return match.group('version')


def themes_commit() -> str:
    text = (ROOT / 'buildzr' / 'themes' / 'assets.py').read_text(encoding='utf-8')
    match = re.search(r'(?m)^THEMES_COMMIT = "([0-9a-f]{40})"$', text)
    if match is None:
        raise ValueError('No full THEMES_COMMIT found in buildzr/themes/assets.py')
    return match.group(1)


def unpinned(kind: str, names: List[str], read: Callable[[str], bytes], prefix: str = '') -> List[str]:
    """Theme icons shipped, and structurizr/themes URLs naming a ref other than the pinned commit."""
    commit = themes_commit()
    result = []
    for name in names:
        rel = name[len(prefix):] if name.startswith(prefix) else name
        if ICONS.match(rel):
            result.append(f'{kind}: ships the theme icon {rel}; the build fetches the icons it needs')
        elif rel.startswith('buildzr/') and rel.endswith(TEXT):  # tests may name other refs on purpose
            refs = sorted({r for r in THEMES_REF.findall(read(name).decode('utf-8', 'replace')) if r != commit})
            if refs:
                result.append(f'{kind}: {rel} names structurizr/themes at {", ".join(refs)}, '
                              f'not the pinned commit {commit}')
    return result


def problems(kind: str, names: List[str], prefix: str = '') -> List[str]:
    """List what is missing from the file `names` of an archive."""
    names = [n[len(prefix):] if n.startswith(prefix) else n for n in names]
    found = set(names)
    result = [f'{kind}: missing {path}' for path in REQUIRED if path not in found]
    if not any(ASSET_JS.match(n) for n in names):
        result.append(f'{kind}: missing a JS bundle in {SITE}/static/assets/')
    if any(p.startswith(f"{SITE}/static/") for p in found) and not any(ASSET_NOTICES.match(n) for n in names):
        result.append(f'{kind}: missing the viewer\'s third-party notices (static/assets/THIRD_PARTY_NOTICES-*.txt)')
    if not any(p.startswith(f"{SITE}/static/") for p in found):
        result.append(
            f'{kind}: no viewer files at all. Build the viewer first: '
            '`cd viewer && npm ci && npm run build`.'
        )
    return result


def check_wheel(path: Path, expected: str) -> List[str]:
    with zipfile.ZipFile(path) as z:
        names = z.namelist()
        result = problems('wheel', names) + unpinned('wheel', names, z.read)
        if any(n.startswith('skills/') for n in names):
            result.append('wheel: contains skills/; the agent skill belongs in the sdist only')
        if not any(WHEEL_NOTICES.match(n) for n in names):
            result.append(f'wheel: missing {NOTICES} in .dist-info/licenses/')
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
        prefix = names[0].split('/')[0] + '/' if names else ''

        def read(name: str) -> bytes:
            f = t.extractfile(name)
            return f.read() if f is not None else b''

        files = [m.name for m in t.getmembers() if m.isfile()]
        result = problems('sdist', names, prefix=prefix) + unpinned('sdist', files, read, prefix=prefix)
    if prefix + SKILL not in names:
        result.append(f'sdist: missing {SKILL}')
    if prefix + NOTICES not in names:
        result.append(f'sdist: missing {NOTICES} at the root')
    return result


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
    print(f'OK: {wheel.name}' + (f' and {sdist.name}' if with_sdist else '') + ' contain the viewer, schemas, example, layout, third-party notices and command modules, and only pinned theme URLs' + (', and the sdist the agent skill.' if with_sdist else '.'))
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
