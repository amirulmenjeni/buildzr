"""``buildzr.yaml``: find, load, validate and resolve the config file.

Typical use (what the commands do)::

    path = find_config(Path.cwd())            # None when there is no file
    cfg = load_config(path)                   # strict parse + validation, no env needed
    target = resolve_target(cfg, "preview", os.environ)   # ${VAR} expanded for this target only

``load_config`` never reads the environment. ``${VAR}`` is expanded only by the
``resolve_*`` functions, and only for the parts they are asked about, so
``deploy -t dev`` does not fail on a variable that only ``prod`` uses.

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
from urllib.parse import urlsplit

import yaml

__all__ = [
    "CONFIG_NAME",
    "BuildSettings",
    "Config",
    "ConfigError",
    "ResolvedBuild",
    "ResolvedTarget",
    "TargetSpec",
    "find_config",
    "load_config",
    "resolve_build",
    "resolve_target",
    "resolve_workspace",
]

CONFIG_NAME = "buildzr.yaml"
_MISNAMED = ("buildzr.yml", ".buildzr.yaml")
DEFAULT_OUT = ".buildzr/site"
DEFAULT_TIMEOUT = 120.0

_TARGET_NAME = re.compile(r"^[a-z][a-z0-9_-]*$")
_PATH_SEGMENT = re.compile(r"^[a-z0-9][a-z0-9._-]*$")
_VAR_NAME = re.compile(r"[A-Z_][A-Z0-9_]*")
_SECRET_KEYS = ("token", "password", "secret")


class ConfigError(Exception):
    """One or more problems with the config file or a target lookup.

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
class TargetSpec:
    """One entry of ``targets:`` as written (``dir``, ``url`` and ``path`` unexpanded).

    Exactly one of ``dir`` and ``url`` is set. ``viewer`` is ``None`` when the
    target does not say, which means "use ``build.viewer``".
    """

    name: str
    dir: Optional[str] = None
    url: Optional[str] = None
    path: str = ""
    viewer: Optional[bool] = None
    timeout: float = DEFAULT_TIMEOUT


@dataclass(frozen=True)
class Config:
    """A loaded and validated ``buildzr.yaml``.

    Attributes:
        path: Absolute path of the file.
        workspace: The ``workspace:`` text, unexpanded and unresolved, or ``None``.
        build: The build settings with defaults.
        default_target: The ``default_target`` value, or the only target's name
            when there is exactly one target, else ``None``.
        targets: Targets by name, in file order.
        lines: Line number of every key, by dotted key (for messages).
    """

    path: Path
    version: int = 1
    workspace: Optional[str] = None
    build: BuildSettings = field(default_factory=BuildSettings)
    default_target: Optional[str] = None
    targets: Mapping[str, TargetSpec] = field(default_factory=dict)
    lines: Mapping[str, int] = field(default_factory=dict)

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
class ResolvedTarget:
    """A target after ``${VAR}`` expansion and validation.

    Attributes:
        name: The target's name.
        dir: Absolute folder for a ``dir`` target, else ``None``.
        url: Deploy address for a ``url`` target, else ``None``.
        path: The site path: no leading or trailing ``/``, ``""`` for the root.
        viewer: The target's ``viewer`` or else ``build.viewer``.
        timeout: Seconds (``url`` targets).
    """

    name: str
    dir: Optional[Path]
    url: Optional[str]
    path: str
    viewer: bool
    timeout: float

    @property
    def site_dir(self) -> Optional[Path]:
        """Where a ``dir`` target's site goes (``dir`` plus ``path``), else ``None``."""
        if self.dir is None:
            return None
        return self.dir / self.path if self.path else self.dir


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


# ------------------------------------------------------------ value validation


def _check_path(value: str) -> tuple[str, Optional[str]]:
    """Normalise a site path. Returns (path, error)."""
    p = value.strip("/")
    if not p:
        return "", None
    for seg in p.split("/"):
        if seg == "..":
            return "", 'must not contain a ".." segment'
        if not _PATH_SEGMENT.match(seg):
            return "", f'segment "{seg}" is not allowed; segments match [a-z0-9][a-z0-9._-]*'
    return p, None


def _check_url(value: str) -> Optional[str]:
    try:
        u = urlsplit(value)
        ok = u.scheme in ("http", "https") and bool(u.netloc) and not re.search(r"\s", value)
    except ValueError:
        ok = False
    return None if ok else f'expected a URL starting with http:// or https://, got "{value}"'


# ----------------------------------------------------------------- the loader

_TOP_KEYS = ("version", "workspace", "build", "default_target", "targets")
_BUILD_KEYS = ("k", "text_color", "viewer", "out")
_TARGET_KEYS = ("dir", "url", "path", "viewer", "timeout")
_TOKEN_ENV_MSG = (
    "token_env is reserved and not supported in this version; deploy tokens are not implemented, "
    "so nothing would be protected. Remove it."
)


class _Validator:
    def __init__(self, name: str, probs: _Problems) -> None:
        self.p = probs
        self.name = name
        self.lines: dict[str, int] = {}

    def keys(self, n: _Node, key: str, allowed: Sequence[str], target: bool = False) -> None:
        for k, line in n.key_lines.items():
            self.lines[f"{key}.{k}" if key else k] = line
            if k in allowed:
                continue
            if k in _SECRET_KEYS:
                self.p.add(line, key, f'unknown key "{k}". Secrets never go in this file; keep them in an environment variable.')
            elif target and k == "token_env":
                self.p.add(line, f"{key}.{k}", _TOKEN_ENV_MSG)
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

    def boolean(self, n: _Node, key: str) -> Optional[bool]:
        if isinstance(n.value, bool):
            return n.value
        self.p.add(n.line, key, f"expected true or false, got {_describe(n)}")
        return None

    def literal_or_defer(self, n: _Node, key: str, text: str, check: Any) -> None:
        """Run ``check(text)`` now unless the text has ``${VAR}`` (then resolve time does it)."""
        parts = _parse_template(text)
        if any(not isinstance(x, str) for x in parts):
            return
        err = check("".join(x for x in parts if isinstance(x, str)))
        if err:
            self.p.add(n.line, key, err)


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

    workspace: Optional[str] = None
    if "workspace" in top:
        n = top["workspace"]
        workspace = v.text(n, "workspace", template=True)

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

    targets: dict[str, TargetSpec] = {}
    if "targets" in top:
        tn = top["targets"]
        tmap = v.mapping(tn, "targets")
        if tmap is not None:
            for tname, t in tmap.items():
                spec = _load_target(v, tname, t, tn.key_lines[tname])
                if spec is not None:
                    targets[tname] = spec

    default: Optional[str] = None
    if "default_target" in top:
        n = top["default_target"]
        if not isinstance(n.value, str):
            probs.add(n.line, "default_target", f"expected the name of a target, got {_describe(n)}")
        elif n.value not in targets:
            have = ", ".join(targets) or "none"
            probs.add(n.line, "default_target", f'no target named "{n.value}" in targets (targets: {have})')
        else:
            default = n.value
    elif len(targets) == 1:
        default = next(iter(targets))

    if probs:
        raise ConfigError(probs.lines())
    return Config(cpath, version, workspace, build, default, targets, dict(v.lines))


def _load_target(v: _Validator, name: str, n: _Node, name_line: int) -> Optional[TargetSpec]:
    probs = v.p
    key = f"targets.{name}"
    v.lines[key] = name_line
    if not _TARGET_NAME.match(name):
        probs.add(name_line, key, f'invalid target name "{name}"; names match [a-z][a-z0-9_-]*')
    t = v.mapping(n, key)
    if t is None:
        return None
    v.keys(n, key, _TARGET_KEYS, target=True)
    before = len(probs._items)
    has_dir, has_url = "dir" in t, "url" in t
    if has_dir == has_url:
        what = "both" if has_dir else "neither"
        probs.add(name_line, key, f'expected exactly one of "dir" or "url", got {what}')
    dir_ = url = None
    if has_dir:
        dir_ = v.text(t["dir"], f"{key}.dir", template=True)
        if dir_ == "":
            probs.add(t["dir"].line, f"{key}.dir", "expected a folder, got empty text")
    if has_url:
        url = v.text(t["url"], f"{key}.url", template=True)
        if url is not None:
            v.literal_or_defer(t["url"], f"{key}.url", url, _check_url)
    path = ""
    if "path" in t:
        pt = v.text(t["path"], f"{key}.path", template=True)
        if pt is not None:
            path = pt
            v.literal_or_defer(t["path"], f"{key}.path", pt, lambda s: _check_path(s)[1])
    viewer: Optional[bool] = None
    if "viewer" in t:
        viewer = v.boolean(t["viewer"], f"{key}.viewer")
    timeout = DEFAULT_TIMEOUT
    if "timeout" in t:
        tm = t["timeout"]
        if has_dir and not has_url:
            probs.add(tm.line, f"{key}.timeout", 'only applies to targets with "url"')
        elif isinstance(tm.value, (int, float)) and not isinstance(tm.value, bool) and tm.value > 0:
            timeout = float(tm.value)
        else:
            probs.add(tm.line, f"{key}.timeout", f"expected a number of seconds above 0, got {_describe(tm)}")
    if len(probs._items) > before or has_dir == has_url:
        return None
    return TargetSpec(name, dir_, url, path, viewer, timeout)


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


def resolve_workspace(cfg: Config, env: Mapping[str, str]) -> Optional[Path]:
    """The ``workspace:`` file as an absolute path (relative to the config's folder).

    Returns:
        The path, or ``None`` when the file does not set ``workspace``.

    Raises:
        ConfigError: A ``${VAR}`` in it is unset or empty.
    """
    if cfg.workspace is None:
        return None
    r = _Resolver(cfg, env)
    text = r.expand("workspace", cfg.workspace)
    r.raise_if_any()
    if text == "":
        r.problem("workspace", "expected a file, got empty text")
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


def resolve_target(cfg: Config, name: Optional[str], env: Mapping[str, str]) -> ResolvedTarget:
    """Pick a target and expand ``${VAR}`` in it (and only in it).

    Args:
        cfg: The loaded config.
        name: Target name, or ``None`` for the default target.
        env: Variables for ``${VAR}``, normally ``os.environ``.

    Returns:
        The target with ``dir`` absolute, ``path`` normalised and ``viewer`` filled in.

    Raises:
        ConfigError: No such target, no default to fall back on, or a variable is
            unset or empty, or an expanded value is not valid (for example a
            ``path`` that becomes ``..``).
    """
    if name is None:
        name = cfg.default_target
        if name is None:
            raise ConfigError([f"buildzr: error: no target given and no default_target; {_target_list(cfg)}"])
    spec = cfg.targets.get(name)
    if spec is None:
        raise ConfigError([f'buildzr: error: no target named "{name}"; {_target_list(cfg)}'])
    key = f"targets.{name}"
    r = _Resolver(cfg, env)
    dir_: Optional[Path] = None
    url: Optional[str] = None
    if spec.dir is not None:
        d = r.expand(f"{key}.dir", spec.dir)
        if not r.errors:
            if d == "":
                r.problem(f"{key}.dir", "expected a folder, got empty text")
            else:
                dir_ = r.folder(d)
    if spec.url is not None:
        url = r.expand(f"{key}.url", spec.url)
        if not r.errors:
            err = _check_url(url)
            if err:
                r.problem(f"{key}.url", err)
    path_text = r.expand(f"{key}.path", spec.path)
    path = ""
    if not r.errors:
        path, perr = _check_path(path_text)
        if perr:
            r.problem(f"{key}.path", perr)
    r.raise_if_any()
    viewer = spec.viewer if spec.viewer is not None else cfg.build.viewer
    return ResolvedTarget(name, dir_, url, path, viewer, spec.timeout)


def _target_list(cfg: Config) -> str:
    if not cfg.targets:
        return f"no targets in {cfg.path}"
    names = ", ".join(n + (" (default)" if n == cfg.default_target else "") for n in cfg.targets)
    return f"targets in {cfg.path}: {names}"
