"""``buildzr.yaml``: find, load, validate and resolve the config file.

Typical use (what the commands do)::

    path = find_config(Path.cwd())            # None when there is no file
    cfg = load_config(path)                   # strict parse + validation, no env needed
    build = resolve_build(cfg, os.environ)    # ${VAR} expanded in build.out
    serve = resolve_serve(cfg, os.environ)    # ${VAR} expanded in serve.public_url, host and cors_origins

``load_config`` never reads the environment. ``${VAR}`` is expanded only by the
``resolve_*`` functions, and only for the parts they are asked about.

Every problem is reported as ``buildzr.yaml:<line>: <dotted.key>: <message>``;
all problems of one call are collected in a single :class:`ConfigError`.

PyYAML is imported here and nowhere else, so ``import buildzr.dsl`` stays light.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Optional, Sequence, Union

import yaml

__all__ = [
    "CONFIG_NAME",
    "BuildSettings",
    "Config",
    "ConfigError",
    "ResolvedBuild",
    "ResolvedServe",
    "ServeSettings",
    "find_config",
    "load_config",
    "resolve_build",
    "resolve_serve",
    "resolve_workspaces",
]

CONFIG_NAME = "buildzr.yaml"
_MISNAMED = ("buildzr.yml", ".buildzr.yaml")
DEFAULT_OUT = ".buildzr/build"
DEFAULT_WORKSPACES = "workspaces"
DEFAULT_HOST = "127.0.0.1"
DEFAULT_PORT = 8000
PORT_MESSAGE = "expected a whole number from 1 to 65535"

_VAR_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
_SECRET_KEYS = ("token", "password", "secret")


class ConfigError(Exception):
    """One or more problems with the config file.

    Attributes:
        problems: The message lines exactly as they are printed, one per problem.
    """

    def __init__(self, problems: Sequence[str]) -> None:
        self.problems = list(problems)
        super().__init__("\n".join(self.problems))


# --------------------------------------------------------------------------- data


@dataclass(frozen=True)
class BuildSettings:
    """The ``build:`` section with defaults filled in (``out`` is still unexpanded text)."""

    k: int = 4
    text_color: str = "wcag"
    viewer: bool = True
    out: str = DEFAULT_OUT


@dataclass(frozen=True)
class ServeSettings:
    """The ``serve:`` section as written: ``None`` for a key that is not set; text is still unexpanded."""

    public_url: Optional[str] = None
    port: Optional[int] = None
    host: Optional[str] = None
    cors_origins: Optional[tuple[str, ...]] = None


@dataclass(frozen=True)
class Config:
    """A loaded and validated ``buildzr.yaml``.

    Attributes:
        path: Absolute path of the file.
        workspaces: The ``workspaces:`` text (a folder or a ``.py`` file), unexpanded and unresolved, or ``None``.
        build: The build settings with defaults.
        lines: Line number of every key, by dotted key (for messages); ``serve.cors_origins[0]`` for list items.
        serve: The serve settings; ``buildzr build`` never reads them.
    """

    path: Path
    version: int = 1
    workspaces: Optional[str] = None
    build: BuildSettings = field(default_factory=BuildSettings)
    lines: Mapping[str, int] = field(default_factory=dict)
    serve: ServeSettings = field(default_factory=ServeSettings)

    @property
    def root(self) -> Path:
        """The folder holding the file; relative paths in it are relative to this."""
        return self.path.parent

    @property
    def name(self) -> str:
        """The file name used in messages."""
        return self.path.name


@dataclass(frozen=True)
class ResolvedBuild:
    """Build settings after ``${VAR}`` expansion; ``out`` is absolute."""

    k: int
    text_color: str
    viewer: bool
    out: Path


@dataclass(frozen=True)
class ResolvedServe:
    """Serve settings after ``${VAR}`` expansion and checking; ``None`` where the file does not set the key.

    ``public_url`` has no trailing slash, as the ``--public-url`` option gives it.
    """

    public_url: Optional[str]
    port: Optional[int]
    host: Optional[str]
    cors_origins: Optional[list[str]]


# ------------------------------------------------------------------- discovery


def find_config(start: Union[str, "os.PathLike[str]"]) -> Optional[Path]:
    """Find ``buildzr.yaml`` from ``start`` upward.

    Looks in ``start``, then each parent, and stops after the first folder that
    contains ``.git`` (the repository root).

    Args:
        start: Folder to start in (usually the current folder).

    Returns:
        The absolute path of the file, or ``None`` if there is none.

    Raises:
        ConfigError: A folder has ``buildzr.yml`` or ``.buildzr.yaml`` but no ``buildzr.yaml``.
    """
    d = Path(os.path.abspath(start))
    while True:
        cand = d / CONFIG_NAME
        if cand.is_file():
            return cand
        for wrong in _MISNAMED:
            if (d / wrong).is_file():
                raise ConfigError([f"found {wrong}; the config file must be named {CONFIG_NAME}"])
        if (d / ".git").exists() or d.parent == d:
            return None
        d = d.parent


# -------------------------------------------------------------------- YAML layer


class _Reject(Exception):
    def __init__(self, msg: str, line: int) -> None:
        super().__init__(msg)
        self.msg = msg
        self.line = line


class _StrictLoader(yaml.SafeLoader):
    """SafeLoader without YAML 1.1's implicit types, anchors, aliases and tags."""

    # Own table (a class attribute, so add_implicit_resolver copies nothing from SafeLoader).
    yaml_implicit_resolvers: dict[Any, Any] = {}

    def compose_node(self, parent: Any, index: Any) -> Any:
        ev = self.peek_event()
        line = ev.start_mark.line + 1
        if isinstance(ev, yaml.AliasEvent):
            raise _Reject("aliases (*name) are not allowed", line)
        if ev.anchor is not None:
            raise _Reject("anchors (&name) are not allowed", line)
        if ev.tag is not None:
            raise _Reject(f'tags ({ev.tag}) are not allowed', line)
        return super().compose_node(parent, index)


_T = "tag:yaml.org,2002:"
_StrictLoader.add_implicit_resolver(_T + "null", re.compile(r"^(?:~|null|)$"), ["~", "n", ""])
_StrictLoader.add_implicit_resolver(_T + "bool", re.compile(r"^(?:true|false)$"), ["t", "f"])
_StrictLoader.add_implicit_resolver(_T + "int", re.compile(r"^[-+]?(?:0|[1-9][0-9]*)$"), list("-+0123456789"))
_StrictLoader.add_implicit_resolver(
    _T + "float", re.compile(r"^[-+]?(?:0|[1-9][0-9]*)\.[0-9]+$"), list("-+0123456789")
)


@dataclass
class _Node:
    """A parsed value with its line. ``value`` is a scalar, ``dict[str, _Node]`` or ``list``."""

    value: Any
    line: int
    key_lines: dict[str, int] = field(default_factory=dict)


def _describe(n: _Node) -> str:
    v = n.value
    if isinstance(v, dict):
        return "a mapping"
    if isinstance(v, list):
        return "a list"
    if v is None:
        return "nothing (null)"
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return f"the whole number {v}"
    if isinstance(v, float):
        return f"the number {v}"
    return f'the text "{v}"'


class _Problems:
    def __init__(self, name: str) -> None:
        self.name = name
        self._items: list[tuple[int, int, str]] = []

    def add(self, line: int, key: str, msg: str) -> None:
        where = f"{self.name}:{line}: "
        self._items.append((line, len(self._items), where + (f"{key}: " if key else "") + msg))

    def lines(self) -> list[str]:
        return [t for _, _, t in sorted(self._items)]

    def __bool__(self) -> bool:
        return bool(self._items)


def _convert(node: Any, path: str, probs: _Problems) -> _Node:
    line = node.start_mark.line + 1
    if isinstance(node, yaml.ScalarNode):
        tag = node.tag
        raw = node.value
        value: Any
        if tag == _T + "null":
            value = None
        elif tag == _T + "bool":
            value = raw == "true"
        elif tag == _T + "int":
            value = int(raw)
        elif tag == _T + "float":
            value = float(raw)
        else:
            value = raw
        return _Node(value, line)
    if isinstance(node, yaml.SequenceNode):
        return _Node([_convert(c, path, probs) for c in node.value], line)
    items: dict[str, _Node] = {}
    key_lines: dict[str, int] = {}
    for k, v in node.value:
        kline = k.start_mark.line + 1
        if not isinstance(k, yaml.ScalarNode):
            probs.add(kline, path, "keys must be plain text")
            continue
        here = f"{path}.{k.value}" if path else k.value
        if k.value == "<<":
            probs.add(kline, path, 'merge keys ("<<") are not allowed')
            continue
        if k.value in items:
            probs.add(kline, path, f'duplicate key "{k.value}" (first used on line {key_lines[k.value]})')
            continue
        key_lines[k.value] = kline
        items[k.value] = _convert(v, here, probs)
    return _Node(items, line, key_lines)


def _parse(text: str, name: str, probs: _Problems) -> Optional[_Node]:
    loader = _StrictLoader(text)
    try:
        node = loader.get_single_node()
        if node is None:
            return _Node({}, 1)
        return _convert(node, "", probs)
    except _Reject as e:
        probs.add(e.line, "", e.msg)
    except yaml.YAMLError as e:
        mark = getattr(e, "problem_mark", None) or getattr(e, "context_mark", None)
        what = getattr(e, "problem", None) or "invalid YAML"
        probs.add(mark.line + 1 if mark else 1, "", f"YAML syntax error: {what}")
    finally:
        loader.dispose()
    return None


# ---------------------------------------------------------------- ${VAR} templates


class _TemplateError(Exception):
    pass


# A part is a literal string or (NAME, fallback or None).
_Part = Union[str, tuple[str, Optional[str]]]
_VAR_AT = re.compile(r"\$\{([A-Z_][A-Z0-9_]*)(?::-([^}$]*))?\}")


def _parse_template(text: str) -> list[_Part]:
    parts: list[_Part] = []
    lit: list[str] = []
    i = 0
    while i < len(text):
        c = text[i]
        if c != "$":
            lit.append(c)
            i += 1
        elif text.startswith("$$", i):
            lit.append("$")
            i += 2
        else:
            m = _VAR_AT.match(text, i)
            if not m:
                raise _TemplateError(
                    f'invalid "$" at position {i + 1} in "{text}"; '
                    "use ${NAME} (NAME like [A-Z_][A-Z0-9_]*), ${NAME:-fallback} or $$ for a literal $"
                )
            if lit:
                parts.append("".join(lit))
                lit = []
            parts.append((m.group(1), m.group(2)))
            i = m.end()
    if lit:
        parts.append("".join(lit))
    return parts


def _expand(parts: list[_Part], text: str, env: Mapping[str, str]) -> tuple[str, list[str]]:
    out: list[str] = []
    errs: list[str] = []
    for p in parts:
        if isinstance(p, str):
            out.append(p)
            continue
        name, fallback = p
        val = env.get(name)
        if val:
            out.append(val)
        elif fallback is not None:
            out.append(fallback)
        else:
            state = "not set" if val is None else "empty"
            errs.append(f'environment variable {name} is {state} (used in "{text}")')
    return "".join(out), errs


# ----------------------------------------------------------------- the loader

_TOP_KEYS = ("version", "workspaces", "build", "serve")
_BUILD_KEYS = ("k", "text_color", "viewer", "out")
_SERVE_KEYS = ("public_url", "port", "host", "cors_origins")
#: Keys of earlier versions, each with the one line that says what to do instead.
_REMOVED = {
    "targets": "removed: buildzr deploy no longer exists; delete this key",
    "default_target": "removed: buildzr deploy no longer exists; delete this key",
    "workspace": "removed: use workspaces: (a folder; a single .py file path also works)",
}


class _Validator:
    def __init__(self, name: str, probs: _Problems) -> None:
        self.p = probs
        self.name = name
        self.lines: dict[str, int] = {}

    def keys(self, n: _Node, key: str, allowed: Sequence[str]) -> None:
        for k, line in n.key_lines.items():
            self.lines[f"{key}.{k}" if key else k] = line
            if k in allowed:
                continue
            if not key and k in _REMOVED:
                self.p.add(line, k, _REMOVED[k])
            elif k in _SECRET_KEYS:
                self.p.add(line, key, f'unknown key "{k}". Secrets never go in this file; keep them in an environment variable.')
            else:
                self.p.add(line, key, f'unknown key "{k}"; allowed keys: {", ".join(allowed)}')

    def mapping(self, n: _Node, key: str) -> Optional[dict[str, _Node]]:
        if isinstance(n.value, dict):
            return n.value
        self.p.add(n.line, key, f"expected a mapping, got {_describe(n)}")
        return None

    def text(self, n: _Node, key: str, template: bool = False) -> Optional[str]:
        if not isinstance(n.value, str):
            self.p.add(n.line, key, f"expected text, got {_describe(n)}")
            return None
        if template:
            try:
                _parse_template(n.value)
            except _TemplateError as e:
                self.p.add(n.line, key, str(e))
                return None
        return n.value

    def literal(self, n: _Node, key: str, text: str, kind: str) -> None:
        """Check a URL or origin now when it has no ``${VAR}`` (else :func:`resolve_serve` checks it)."""
        if "$" in text:
            return
        from buildzr.site.api import normalise_origin, normalise_public_url  # not at import time: keep this light

        try:
            (normalise_public_url if kind == "public_url" else normalise_origin)(text)
        except ValueError as e:
            self.p.add(n.line, key, str(e))

    def boolean(self, n: _Node, key: str) -> Optional[bool]:
        if isinstance(n.value, bool):
            return n.value
        self.p.add(n.line, key, f"expected true or false, got {_describe(n)}")
        return None


def load_config(path: Union[str, "os.PathLike[str]"]) -> Config:
    """Read and validate a ``buildzr.yaml``.

    Parsing is strict (see the module notes in ``docs/config.md``): ``yes``, ``on``,
    ``0755`` and dates stay text, duplicate keys, anchors, aliases and tags are
    errors, and types are checked, never converted. The environment is not read;
    ``${VAR}`` text is kept as written until a ``resolve_*`` call.

    Args:
        path: The config file.

    Returns:
        The validated :class:`Config`.

    Raises:
        ConfigError: The file cannot be read or has any problem; all problems are listed.
    """
    cpath = Path(os.path.abspath(path))
    probs = _Problems(cpath.name)
    try:
        text = cpath.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as e:
        raise ConfigError([f"buildzr: error: cannot read {cpath}: {e}"]) from e
    root = _parse(text, cpath.name, probs)
    if root is None or probs:
        raise ConfigError(probs.lines())
    v = _Validator(cpath.name, probs)
    top = v.mapping(root, "")
    if top is None:
        raise ConfigError(probs.lines())
    v.keys(root, "", _TOP_KEYS)

    version = 1
    if "version" in top:
        n = top["version"]
        if not (isinstance(n.value, int) and not isinstance(n.value, bool)) or n.value != 1:
            probs.add(n.line, "version", f"expected 1 (the only supported version), got {_describe(n)}")
        else:
            version = n.value

    workspaces: Optional[str] = None
    if "workspaces" in top:
        n = top["workspaces"]
        workspaces = v.text(n, "workspaces", template=True)

    build = BuildSettings()
    if "build" in top:
        bn = top["build"]
        b = v.mapping(bn, "build")
        if b is not None:
            v.keys(bn, "build", _BUILD_KEYS)
            k, tc, viewer, out = build.k, build.text_color, build.viewer, build.out
            if "k" in b:
                n = b["k"]
                if isinstance(n.value, int) and not isinstance(n.value, bool) and n.value >= 1:
                    k = n.value
                else:
                    probs.add(n.line, "build.k", f"expected a whole number of at least 1, got {_describe(n)}")
            if "text_color" in b:
                n = b["text_color"]
                if n.value in ("wcag", "c4") and isinstance(n.value, str):
                    tc = n.value
                else:
                    probs.add(n.line, "build.text_color", f"expected wcag or c4, got {_describe(n)}")
            if "viewer" in b:
                bv = v.boolean(b["viewer"], "build.viewer")
                viewer = viewer if bv is None else bv
            if "out" in b:
                o = v.text(b["out"], "build.out", template=True)
                if o is not None:
                    if o == "":
                        probs.add(b["out"].line, "build.out", "expected a folder, got empty text")
                    else:
                        out = o
            build = BuildSettings(k, tc, viewer, out)

    serve = ServeSettings()
    if "serve" in top:
        sn = top["serve"]
        sv = v.mapping(sn, "serve")
        if sv is not None:
            v.keys(sn, "serve", _SERVE_KEYS)
            public_url = host = None
            port: Optional[int] = None
            origins: Optional[tuple[str, ...]] = None
            if "public_url" in sv:
                public_url = v.text(sv["public_url"], "serve.public_url", template=True)
                if public_url is not None:
                    v.literal(sv["public_url"], "serve.public_url", public_url, "public_url")
            if "host" in sv:
                host = v.text(sv["host"], "serve.host", template=True)
                if host == "":
                    probs.add(sv["host"].line, "serve.host", "expected a host name or address, got empty text")
            if "port" in sv:
                n = sv["port"]
                if isinstance(n.value, int) and not isinstance(n.value, bool) and 1 <= n.value <= 65535:
                    port = n.value
                else:
                    probs.add(n.line, "serve.port", f"{PORT_MESSAGE}, got {_describe(n)}")
            if "cors_origins" in sv:
                n = sv["cors_origins"]
                if not isinstance(n.value, list):
                    probs.add(n.line, "serve.cors_origins", f"expected a list of origins, got {_describe(n)}")
                else:
                    items = []
                    for i, item in enumerate(n.value):
                        key = f"serve.cors_origins[{i}]"
                        v.lines[key] = item.line
                        t = v.text(item, key, template=True)
                        if t is not None:
                            v.literal(item, key, t, "origin")
                            items.append(t)
                    origins = tuple(items)
            serve = ServeSettings(public_url, port, host, origins)

    if probs:
        raise ConfigError(probs.lines())
    return Config(cpath, version, workspaces, build, dict(v.lines), serve)


# ------------------------------------------------------------------- resolving


class _Resolver:
    def __init__(self, cfg: Config, env: Mapping[str, str]) -> None:
        self.cfg = cfg
        self.env = env
        self.errors: list[tuple[int, str]] = []

    def expand(self, key: str, text: str) -> str:
        line = self.cfg.lines.get(key, 1)
        out, errs = _expand(_parse_template(text), text, self.env)
        for e in errs:
            self.errors.append((line, f"{self.cfg.name}:{line}: {key}: {e}"))
        return out

    def problem(self, key: str, msg: str) -> None:
        line = self.cfg.lines.get(key, 1)
        self.errors.append((line, f"{self.cfg.name}:{line}: {key}: {msg}"))

    def folder(self, value: str) -> Path:
        return Path(os.path.abspath(self.cfg.root / value))

    def raise_if_any(self) -> None:
        if self.errors:
            raise ConfigError([m for _, m in sorted(self.errors, key=lambda t: t[0])])


def resolve_workspaces(cfg: Config, env: Mapping[str, str]) -> Optional[Path]:
    """The ``workspaces:`` folder (or file) as an absolute path (relative to the config's folder).

    Returns:
        The path, or ``None`` when the file does not set ``workspaces``.

    Raises:
        ConfigError: A ``${VAR}`` in it is unset or empty.
    """
    if cfg.workspaces is None:
        return None
    r = _Resolver(cfg, env)
    text = r.expand("workspaces", cfg.workspaces)
    r.raise_if_any()
    if text == "":
        r.problem("workspaces", "expected a folder or a file, got empty text")
        r.raise_if_any()
    return r.folder(text)


def resolve_build(cfg: Config, env: Mapping[str, str]) -> ResolvedBuild:
    """The build settings with ``build.out`` expanded and made absolute.

    Raises:
        ConfigError: A ``${VAR}`` in ``build.out`` is unset or empty.
    """
    r = _Resolver(cfg, env)
    out = r.expand("build.out", cfg.build.out)
    if not r.errors and out == "":
        r.problem("build.out", "expected a folder, got empty text")
    r.raise_if_any()
    b = cfg.build
    return ResolvedBuild(b.k, b.text_color, b.viewer, r.folder(out))


def resolve_serve(cfg: Config, env: Mapping[str, str]) -> ResolvedServe:
    """The ``serve:`` settings with ``${VAR}`` expanded in ``public_url``, ``host`` and each of ``cors_origins``.

    ``public_url`` and the origins are checked as the ``--public-url`` and ``--cors-origin`` options are, with the
    same messages.

    Raises:
        ConfigError: A ``${VAR}`` is unset or empty, or a value is not a valid URL, origin or host.
    """
    from buildzr.site.api import normalise_origin, normalise_public_url  # not at import time: keep this module light

    s = cfg.serve
    r = _Resolver(cfg, env)
    public_url: Optional[str] = None
    if s.public_url is not None:
        text = r.expand("serve.public_url", s.public_url)
        if not r.errors:
            try:
                public_url = normalise_public_url(text)
            except ValueError as e:
                r.problem("serve.public_url", str(e))
    host: Optional[str] = None
    if s.host is not None:
        n = len(r.errors)
        host = r.expand("serve.host", s.host)
        if len(r.errors) == n and host == "":
            r.problem("serve.host", "expected a host name or address, got empty text")
    origins: Optional[list[str]] = None
    if s.cors_origins is not None:
        origins = []
        for i, item in enumerate(s.cors_origins):
            key = f"serve.cors_origins[{i}]"
            n = len(r.errors)
            text = r.expand(key, item)
            if len(r.errors) > n:
                continue
            try:
                origins.append(normalise_origin(text))
            except ValueError as e:
                r.problem(key, str(e))
        origins = list(dict.fromkeys(origins))
    r.raise_if_any()
    return ResolvedServe(public_url, s.port, host, origins)
