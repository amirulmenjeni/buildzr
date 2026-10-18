"""Helpers of the doc tests: fenced code blocks of a page, the directives before them, and output normalising."""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any, Optional

ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DOCS = os.path.join(ROOT, "docs")

#: The pages whose examples are tested: the Publishing section in its order, then the Quick Start.
PAGES = ["cli.md", "config.md", "deploy.md", "publishing-recipes.md", "store.md", "ui-settings.md",
         "viewer-hash-routes.md", "model-api.md", "getting-started/quick-start.md"]

FENCE = re.compile(r"^(\s*)```([\w+-]*)(?:\s+\w[^`]*)?\s*$")  # attributes such as hl_lines="2-4" may follow
DIRECTIVE = re.compile(r"^<!--\s*doctest:\s*(\w+)\s*(.*?)\s*-->\s*$")


@dataclass
class Block:
    """One fenced code block. ``directive`` is ``(name, argument)`` of the ``<!-- doctest: ... -->`` line before it."""

    page: str
    line: int  # 1-based line of the opening fence
    lang: str
    text: str
    directive: Optional[tuple[str, str]] = None

    @property
    def id(self) -> str:
        return f"{self.page}:{self.line}"


def extract_blocks(page: str) -> list[Block]:
    with open(os.path.join(DOCS, page), encoding="utf-8") as f:
        lines = f.read().split("\n")
    blocks: list[Block] = []
    i = 0
    while i < len(lines):
        m = FENCE.match(lines[i])
        if not m:
            i += 1
            continue
        indent, lang = m.group(1), m.group(2)
        j = i + 1
        body: list[str] = []
        while j < len(lines):
            closing = FENCE.match(lines[j])
            if closing and not closing.group(2):
                break
            body.append(lines[j][len(indent):] if lines[j].startswith(indent) else lines[j])
            j += 1
        directive: Optional[tuple[str, str]] = None
        k = i - 1
        if k >= 0 and not lines[k].strip():
            k -= 1
        if k >= 0:
            d = DIRECTIVE.match(lines[k].strip())
            if d:
                directive = (d.group(1), d.group(2))
        blocks.append(Block(page, i + 1, lang, "\n".join(body) + "\n", directive))
        i = j + 1
    return blocks


# --- output normalising -------------------------------------------------------------------------------------

_RULES: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r"sha256:[0-9a-f]{64}"), "sha256:HASH"),
    (re.compile(r"sha256:[0-9a-f]{4,}…?"), "sha256:HASH"),
    (re.compile(r"(?<![\w:/.])/[\w.@+\-/]+"), "<PATH>"),
    (re.compile(r"(?<=[\d\]]):\d{2,5}\b"), ":PORT"),
    (re.compile(r"\b\d+ files, \d+ (?:B|KB|MB)\b"), "N files, SIZE"),
    (re.compile(r"\(\d+ (?:B|KB|MB) compressed\)"), "(SIZE compressed)"),
    (re.compile(r"\bsite is \d+ MB\b"), "site is N MB"),
    (re.compile(r"\b\d+ ms\b"), "N ms"),
]


def normalise(line: str) -> str:
    """Hashes, absolute paths, ports, file counts and sizes, and timings replaced by fixed words."""
    for pat, repl in _RULES:
        line = pat.sub(repl, line)
    return line.rstrip()


def same_lines(expected: list[str], actual: list[str]) -> Optional[str]:
    """``None`` when ``actual`` matches ``expected`` after normalising (a line ``...`` stands for any lines), else a
    message that shows both."""
    exp = [normalise(x) for x in expected]
    act = [normalise(x) for x in actual]

    def match(i: int, j: int) -> bool:
        if i == len(exp):
            return j == len(act)
        if exp[i] == "...":
            return any(match(i + 1, k) for k in range(j, len(act) + 1))
        return j < len(act) and exp[i] == act[j] and match(i + 1, j + 1)

    if match(0, 0):
        return None
    return "expected:\n  " + "\n  ".join(exp) + "\nactual:\n  " + "\n  ".join(act)


# --- JSON shapes ------------------------------------------------------------------------------------------

_HASH = re.compile(r"^sha256:[0-9a-f]{64}$")


def _kind(v: Any) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "bool"
    if isinstance(v, (int, float)):
        return "number"
    if isinstance(v, str):
        return "string"
    return "array" if isinstance(v, list) else "object"


def compare_json(doc: Any, live: Any, where: str = "$", values: bool = True,
                 ignore: frozenset[str] = frozenset()) -> list[str]:
    """Differences between the JSON of a page (``doc``) and a live answer: same keys, same types (a ``null`` on
    either side stands for 'depends on the build') and, with ``values``, the same values. Keys in ``ignore`` are
    only checked for their type. A ``modelHash`` is a hash on both sides."""
    out: list[str] = []
    kd, kl = _kind(doc), _kind(live)
    if kd == "null" or kl == "null":
        return out
    if kd != kl:
        return [f"{where}: the page has {kd}, the server answers {kl}"]
    if isinstance(doc, dict):
        if set(doc) != set(live):
            out.append(f"{where}: keys differ: only on the page {sorted(set(doc) - set(live))}, "
                       f"only in the answer {sorted(set(live) - set(doc))}")
        for k in doc:
            if k in live:
                out += compare_json(doc[k], live[k], f"{where}.{k}", values and k not in ignore, ignore)
    elif isinstance(doc, list):
        if doc and live:
            if values:
                if len(doc) != len(live):
                    out.append(f"{where}: the page lists {len(doc)} items, the server {len(live)}")
                for n, (a, b) in enumerate(zip(doc, live)):
                    out += compare_json(a, b, f"{where}[{n}]", values, ignore)
            else:
                out += compare_json(doc[0], live[0], f"{where}[0]", values, ignore)
    elif values and doc != live:
        if isinstance(doc, str) and _HASH.match(doc) and isinstance(live, str) and _HASH.match(live):
            return out
        out.append(f"{where}: the page has {doc!r}, the server answers {live!r}")
    return out
