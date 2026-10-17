"""The deploy listener of ``buildzr serve --store DIR --accept-deploys`` (see ``docs/deploy.md``).

A second HTTP listener, always bound to ``127.0.0.1``, next to the read-only store server. It answers three requests
and refuses everything else::

    PUT  /_buildzr/v1/deploy?path=pr/42      body: a gzip-compressed tar of a built site
    POST /_buildzr/v1/rollback?path=pr/42    current and previous release swap
    GET  /_buildzr/v1/status                 instance version, store, limits

Every request body is treated as hostile. The archive is never given to ``extractall``: :func:`unpack` reads it member
by member (only regular files and folders with safe names, limits checked while streaming), :func:`check_upload` runs the
site checker and the version and viewer checks, and only then :meth:`Store.install` makes it the current release. The
reading listener shares the same :class:`~buildzr.site.store.Store`, so readers see a deploy at once.
"""

from __future__ import annotations

import email.errors
import errno
import gzip
import hashlib
import html.parser
import http.server
import json
import os
import re
import secrets
import shutil
import socket
import subprocess
import sys
import tarfile
import threading
import time
import zlib
from datetime import datetime, timezone
from typing import Any, Callable, Optional
from urllib.parse import parse_qsl, quote

from buildzr.__about__ import VERSION
from buildzr.site.canonical import INDEX_SCHEMA, MODEL_SCHEMA, SCENE_SCHEMA
from buildzr.site.check import check_site
from buildzr.site.serve import Server, make_store_server
from buildzr.site.store import SitePathError, Store, StoreError, normalise_site_path

DEPLOY_ENDPOINT = "/_buildzr/v1/deploy"
ROLLBACK_ENDPOINT = "/_buildzr/v1/rollback"
STATUS_ENDPOINT = "/_buildzr/v1/status"
LOOPBACK = "127.0.0.1"
DEFAULT_DEPLOY_PORT = 8001
DEFAULT_MAX_UPLOAD_MB = 50
MAX_UNPACKED_BYTES = 200 * 1024 * 1024
MAX_FILES = 20_000
BODY_TIMEOUT = 60.0
CHECK_TIMEOUT = 60.0
MAX_ERRORS = 20
MAX_NAME = 255
MAX_DEPTH = 16
#: Each JSON file is parsed whole by the checker; these caps keep its memory bounded (it also runs in a child process).
MAX_INDEX_BYTES = 4 * 1024 * 1024
MAX_DATA_FILE_BYTES = 32 * 1024 * 1024
CHECK_MEMORY_BYTES = 1024 * 1024 * 1024
ASSET_EXTENSIONS = (".js", ".css", ".woff2", ".woff", ".txt")
#: A legitimate site compresses to about a tenth; past 16 MB unpacked, more than this ratio is a bomb.
MAX_RATIO = 250
RETRY_AFTER = 5
HEADER_TIMEOUT = 30.0
#: Connections the deploy listener serves at once; more are closed at once (only one deploy can run anyway).
MAX_CONNECTIONS = 16
TOP_FILES = frozenset({"index.html", "build.json"})
TOP_DIRS = frozenset({"assets", "data"})
FORWARDED = ("Forwarded", "X-Forwarded-For", "X-Forwarded-Host", "X-Real-IP")
PROBLEM = "urn:buildzr:problem:"

_NAME = re.compile(r"[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*")
#: Any port: through an SSH tunnel the client's port is not the listener's; the name is what stops DNS rebinding.
_HOST = re.compile(r"(127\.0\.0\.1|localhost|\[::1\])(:[0-9]{1,5})?")
_VERSION = re.compile(r"[0-9A-Za-z.+_-]{1,40}")
_SCHEMA = re.compile(r"buildzr\.(index|model|scene)/(\d+)")
_KINDS = {b"1": "a hard link", b"2": "a symbolic link", b"3": "a character device", b"4": "a block device",
          b"6": "a FIFO", b"7": "a contiguous file", b"x": "a pax extended header", b"g": "a pax global header",
          b"L": "a GNU long name", b"K": "a GNU long link name", b"S": "a GNU sparse file", b"V": "a volume label"}


class Rejected(Exception):
    """A request the listener refuses: HTTP ``status``, problem ``code`` and one line of ``detail`` (plus ``errors``)."""

    def __init__(self, status: int, code: str, title: str, detail: str, errors: Optional[list[str]] = None,
                 headers: Optional[dict[str, str]] = None, **extra: Any) -> None:
        super().__init__(detail)
        self.status, self.code, self.title, self.detail = status, code, title, detail
        self.errors = errors
        self.headers = headers or {}
        self.extra = extra

    def problem(self) -> dict[str, Any]:
        doc: dict[str, Any] = {"type": PROBLEM + self.code, "title": self.title, "status": self.status,
                               "code": self.code, "detail": self.detail}
        if self.errors is not None:
            doc["errors"] = self.errors[:MAX_ERRORS]
        doc.update(self.extra)
        return doc


def _invalid(errors: list[str]) -> Rejected:
    return Rejected(422, "invalid-site", "Invalid site", errors[0] if len(errors) == 1 else
                    f"{len(errors)} problems, the first: {errors[0]}", errors=errors)


def _disk_full(e: OSError) -> bool:
    return e.errno in (errno.ENOSPC, getattr(errno, "EDQUOT", errno.ENOSPC))


def _no_space() -> Rejected:
    return Rejected(507, "out-of-space", "Out of disk space", "the instance is out of disk space; nothing changed")


def _shown(name: str) -> str:
    """A member name as text that is safe to put in a message (escaped, at most 80 characters)."""
    r = repr(name)
    return r if len(r) <= 80 else r[:77] + "..."


# --- unpacking ---------------------------------------------------------------------------------------------


class _Refused(Exception):
    """Raised from inside the tar stream: stop reading at once."""


class _TarGuard:
    """The decompressed tar stream as ``tarfile`` reads it, with the archive's headers inspected first.

    ``tarfile`` acts on some members by itself before the caller sees them: it reads a pax or GNU long-name header
    whole into memory and applies it to the next member. The guard follows the 512-byte headers itself and stops the
    stream at any member type other than a regular file or a folder, so ``tarfile`` never processes one. It also stops
    once more than ``limit`` bytes were decompressed, or when the compression ratio is that of a bomb.
    """

    def __init__(self, raw: "gzip.GzipFile", compressed: int, limit: int) -> None:
        self.raw, self.compressed, self.limit = raw, max(compressed, 1), limit
        self.total = 0
        self.hdr = bytearray()
        self.skip = 0
        self.ended = False

    def read(self, size: int = -1) -> bytes:
        data = self.raw.read(size if size is not None and size >= 0 else 1 << 16)
        self.total += len(data)
        if self.total > self.limit:
            raise _Refused(f"the archive unpacks to more than {self.limit // (1024 * 1024)} MB")
        if self.total > 16 * 1024 * 1024 and self.total > MAX_RATIO * self.compressed:
            raise _Refused(f"the archive unpacks to more than {MAX_RATIO} times its size (a compression bomb)")
        if not self.ended:
            self._feed(data)
        return data

    def _feed(self, data: bytes) -> None:
        i, n = 0, len(data)
        while i < n and not self.ended:
            if self.skip:
                k = min(self.skip, n - i)
                self.skip -= k
                i += k
                continue
            k = min(512 - len(self.hdr), n - i)
            self.hdr += data[i:i + k]
            i += k
            if len(self.hdr) == 512:
                self.skip = self._header(bytes(self.hdr))
                self.hdr = bytearray()

    def _header(self, block: bytes) -> int:
        if block == bytes(512):
            self.ended = True  # tarfile stops at the first zero block
            return 0
        name = block[0:100].split(b"\0", 1)[0]
        prefix = block[345:500].split(b"\0", 1)[0]
        full = ((prefix + b"/" if prefix else b"") + name).decode("ascii", "replace")
        flag = block[156:157]
        if not block[257:262] == b"ustar":
            raise _Refused(f"member {_shown(full)}: not a ustar header (only plain ustar archives are accepted)")
        if flag in _KINDS or flag not in (b"0", b"\0", b"5"):
            kind = _KINDS.get(flag, f"member type {flag!r}")
            raise _Refused(f"member {_shown(full)} is {kind}; only regular files and folders are allowed")
        field = block[124:136]
        if field[:1] and field[0] & 0x80:
            raise _Refused(f"member {_shown(full)}: binary size field not accepted")
        digits = field.split(b"\0", 1)[0].strip()
        if not re.fullmatch(rb"[0-7]{1,12}", digits):
            raise _Refused(f"member {_shown(full)}: bad size field")
        size = int(digits, 8)
        is_dir = flag == b"5" or (flag == b"\0" and full.endswith("/"))
        if is_dir:
            if size:
                raise _Refused(f"member {_shown(full)}: a folder with data")
            return 0
        return (size + 511) // 512 * 512


class _WriteFailed(Exception):
    """Writing an unpacked file failed for a reason that is not the archive's fault."""


def _write(fn: Callable[[], None], where: str) -> None:
    """Run a write step; the disk being full is 507, a name the file system already has is the archive's fault (two
    names that this file system treats as one), anything else is the instance's problem (500)."""
    try:
        fn()
    except _Refused:
        raise
    except OSError as e:
        if _disk_full(e):
            raise _no_space() from None
        if e.errno in (errno.EEXIST, errno.ENOTDIR, errno.EISDIR):
            raise _Refused(f"{where}: this file system sees it as a name that is already there") from None
        raise _WriteFailed(f"cannot write {where}: {e.strerror or e}") from None


def _write_member(src: Any, path: str, size: int, where: str) -> None:
    os.makedirs(os.path.dirname(path), 0o755, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0), 0o644)
    written = 0
    with os.fdopen(fd, "wb") as out:
        while True:
            chunk = src.read(1 << 16)
            if not chunk:
                break
            written += len(chunk)
            if written > size:
                raise _Refused(f"{where}: more data than its header says")
            out.write(chunk)
    if written != size:
        raise _Refused(f"{where}: the archive ends inside this file")
    os.chmod(path, 0o644)


def unpack(archive: str, dest: str, max_unpacked: int = MAX_UNPACKED_BYTES, max_files: int = MAX_FILES
           ) -> tuple[int, int]:
    """Unpack the gzip-compressed tar ``archive`` into the new folder ``dest``; ``(files, bytes)``.

    Raises :class:`Rejected` (422 with up to 20 errors, 507 when the disk is full). Names match
    ``^[A-Za-z0-9._-]+(/[A-Za-z0-9._-]+)*$`` with no ``.``/``..`` segment, at most 255 characters; no duplicates (also
    not by case); only regular files and folders; only ``index.html``, ``assets/``, ``data/`` and ``build.json`` at the
    top. Files are written ``0644`` and folders ``0755`` whatever the archive says; owners and times are ignored.
    The caller removes ``dest`` on failure.
    """
    os.mkdir(dest, 0o755)
    errors: list[str] = []
    #: case-folded name -> (kind, name as written) of every file and folder so far, folders implied by a path included
    known: dict[str, tuple[str, str]] = {}
    given: set[str] = set()  # case-folded names that were members themselves
    count = total = folders = 0
    compressed = os.path.getsize(archive)

    def bad(msg: str) -> None:
        errors.append(msg)
        if len(errors) >= MAX_ERRORS:
            raise _Refused(msg)

    def fits(name: str, kind: str) -> bool:
        """``name`` is new, or is the very same folder (same case) already implied by an earlier path."""
        k = known.get(name.casefold())
        return k is None or k == (kind, name) == ("folder", name)

    try:
        with open(archive, "rb") as f, gzip.GzipFile(fileobj=f, mode="rb") as gz:
            guard = _TarGuard(gz, compressed, max_unpacked + 512 * (2 * max_files + 2) + 10240)
            with tarfile.open(fileobj=guard, mode="r|") as tf:  # type: ignore[call-overload]
                for m in tf:
                    name = m.name
                    where = f"member {_shown(name)}"
                    if m.pax_headers:
                        bad(f"{where}: pax headers are not accepted")
                        continue
                    if not (m.isreg() or m.isdir()):
                        bad(f"{where}: only regular files and folders are allowed")
                        continue
                    if len(name) > MAX_NAME:
                        bad(f"{where}: the name is longer than {MAX_NAME} characters")
                        continue
                    segs = name.split("/")
                    if not _NAME.fullmatch(name) or any(s in (".", "..") for s in segs):
                        bad(f"{where}: names use letters, digits, '.', '_', '-' and '/' only, with no '.' or '..' "
                            "segment and no leading '/'")
                        continue
                    if len(segs) > MAX_DEPTH:
                        bad(f"{where}: more than {MAX_DEPTH} levels of folders")
                        continue
                    top = segs[0]
                    if top not in TOP_FILES and top not in TOP_DIRS:
                        bad(f"{where}: only index.html, assets/, data/ and build.json may be at the top")
                        continue
                    if top in TOP_FILES and (len(segs) > 1 or not m.isreg()):
                        bad(f"{where}: {top} must be a file")
                        continue
                    if top in TOP_DIRS and len(segs) == 1 and not m.isdir():
                        bad(f"{where}: {top} must be a folder")
                        continue
                    if m.isreg() and top == "assets" and not name.lower().endswith(ASSET_EXTENSIONS):
                        bad(f"{where}: files in assets/ are {', '.join(ASSET_EXTENSIONS)} only")
                        continue
                    if m.isreg() and top == "data" and m.size > (MAX_INDEX_BYTES if name == "data/index.json"
                                                                 else MAX_DATA_FILE_BYTES):
                        bad(f"{where}: larger than {(MAX_INDEX_BYTES if name == 'data/index.json' else MAX_DATA_FILE_BYTES) // (1024 * 1024)} MB")
                        continue
                    kind = "folder" if m.isdir() else "file"
                    parents = ["/".join(segs[:i]) for i in range(1, len(segs))]
                    if name.casefold() in given or not fits(name, kind) or not all(fits(p, "folder") for p in parents):
                        bad(f"{where}: the name appears twice, or a file and a folder have the same name "
                            "(also when they differ only in upper and lower case)")
                        continue
                    given.add(name.casefold())
                    for p in parents + ([name] if kind == "folder" else []):
                        if p.casefold() not in known:
                            known[p.casefold()] = ("folder", p)
                            folders += 1
                    if folders > max_files:
                        raise _Refused(f"the archive has more than {max_files} folders")
                    if kind == "file":
                        known[name.casefold()] = ("file", name)
                    if kind == "folder":
                        if not errors:
                            _write(lambda: os.makedirs(os.path.join(dest, *segs), 0o755, exist_ok=True), where)
                        continue
                    count += 1
                    total += m.size
                    if count > max_files:
                        raise _Refused(f"the archive has more than {max_files} files")
                    if total > max_unpacked:
                        raise _Refused(f"the archive unpacks to more than {max_unpacked // (1024 * 1024)} MB")
                    if errors:
                        continue  # keep looking for problems; write nothing more
                    src = tf.extractfile(m)
                    assert src is not None
                    _write(lambda: _write_member(src, os.path.join(dest, *segs), m.size, where), where)
    except _Refused as e:
        if not errors or errors[-1] != str(e):
            errors.append(str(e))
    except _WriteFailed:
        raise
    except OSError as e:
        errors.append(f"the upload is not a complete gzip-compressed tar archive ({type(e).__name__}: {str(e)[:120]})")
    except (EOFError, zlib.error, tarfile.TarError) as e:
        if isinstance(e, tarfile.ReadError) and str(e) == "empty file":
            errors.append("the archive is empty")
        else:
            errors.append("the upload is not a complete gzip-compressed tar archive "
                          f"({type(e).__name__}: {str(e)[:120]})")
    if not errors and count == 0:
        errors.append("the archive has no files")
    if errors:
        raise _invalid(errors[:MAX_ERRORS])
    for d, subdirs, _ in os.walk(dest):
        for s in subdirs:
            os.chmod(os.path.join(d, s), 0o755)
    os.chmod(dest, 0o755)
    return count, total


# --- checks before install ---------------------------------------------------------------------------------


def _version_sentence(ours: str, theirs: str) -> str:
    m = _SCHEMA.fullmatch(theirs)
    newer = m is not None and int(m.group(2)) > int(ours.rsplit("/", 1)[1])
    fix = "upgrade the instance" if newer else "rebuild the site with the buildzr version of the instance"
    return f"this instance reads {ours}; the upload is {theirs}; {fix}"


def _read_small_json(path: str) -> Any:
    if os.path.islink(path) or not os.path.isfile(path) or os.path.getsize(path) > MAX_DATA_FILE_BYTES:
        return None
    try:
        with open(path, "rb") as f:
            return json.loads(f.read().decode("utf-8"))
    except (OSError, ValueError, RecursionError):
        return None


def _schema_problem(site: str) -> Optional[str]:
    """The 6.8 sentence when the upload uses a buildzr schema name other than this instance's, else ``None``."""
    data = os.path.join(site, "data")
    index = _read_small_json(os.path.join(data, "index.json"))
    if not isinstance(index, dict):
        return None

    def other(doc: Any, ours: str) -> Optional[str]:
        s = doc.get("schema") if isinstance(doc, dict) else None
        if isinstance(s, str) and s != ours and _SCHEMA.fullmatch(s) and s.split("/")[0] == ours.split("/")[0]:
            return _version_sentence(ours, s)
        return None

    found = other(index, INDEX_SCHEMA)
    if found or index.get("schema") != INDEX_SCHEMA:
        return found
    entries: list[tuple[Any, str]] = [(index.get("model"), MODEL_SCHEMA)]
    scenes = index.get("scenes")
    if isinstance(scenes, dict):
        entries += [(e, SCENE_SCHEMA) for e in scenes.values()]
    for entry, ours in entries:
        rel = entry.get("file") if isinstance(entry, dict) else None
        if not isinstance(rel, str) or not _NAME.fullmatch(rel) or any(s in (".", "..") for s in rel.split("/")):
            continue  # the checker reports it
        found = other(_read_small_json(os.path.join(data, *rel.split("/"))), ours)
        if found:
            return found
    return None


class _PageRefs(html.parser.HTMLParser):
    """What a viewer page refers to, and what it does that a built viewer page never does."""

    URL_ATTRS = ("src", "href", "srcset", "data", "action", "formaction", "poster", "background", "ping", "manifest")

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.refs: list[str] = []
        self.problems: list[str] = []
        self._in: Optional[str] = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, Optional[str]]]) -> None:
        a = {k.lower(): (v or "") for k, v in attrs}
        for k in a:
            if k.startswith("on") or k == "style":
                self.problems.append(f"index.html: <{tag} {k}=...> is not allowed (no inline script or style)")
        if tag in ("base", "iframe", "object", "embed", "form", "style"):
            self.problems.append(f"index.html: <{tag}> is not allowed in a viewer page")
        if tag == "meta" and a.get("http-equiv", "").lower() == "refresh":
            self.problems.append("index.html: <meta http-equiv=refresh> is not allowed")
        for k in self.URL_ATTRS:
            if k in a:
                values = [c.strip().split()[0] for c in a[k].split(",") if c.strip()] if k == "srcset" else [a[k]]
                self.refs.extend(values)
        self._in = tag if tag == "script" and "src" not in a else None

    def handle_data(self, data: str) -> None:
        if self._in == "script" and data.strip():
            self.problems.append("index.html: inline <script> is not allowed; scripts come from assets/")

    def handle_endtag(self, tag: str) -> None:
        self._in = None


def _viewer_problems(site: str) -> list[str]:
    """``index.html`` (when there is one) may refer only to files under ``assets/`` that exist, with no inline script.

    This is an integrity check of a built viewer page, not a sandbox: the deployer is trusted in v1 (``docs/deploy.md``).
    """
    page = os.path.join(site, "index.html")
    if not os.path.exists(page):
        return []
    if os.path.getsize(page) > 1024 * 1024:
        return ["index.html: larger than 1 MB"]
    try:
        with open(page, "rb") as f:
            text = f.read().decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return ["index.html: not UTF-8 text"]
    parser = _PageRefs()
    try:
        parser.feed(text)
        parser.close()
    except Exception as e:  # html.parser is lenient; be safe anyway
        return [f"index.html: cannot be read as HTML ({type(e).__name__})"]
    problems = parser.problems[:MAX_ERRORS]
    assets = os.path.realpath(os.path.join(site, "assets"))
    for ref in parser.refs:
        rel = ref[2:] if ref.startswith("./") else ref
        segs = rel.split("/")
        ok = (rel.startswith("assets/") and _NAME.fullmatch(rel) is not None
              and not any(s in (".", "..") for s in segs))
        if ok:
            full = os.path.realpath(os.path.join(site, *segs))
            ok = full.startswith(assets + os.sep) and os.path.isfile(full) and not os.path.islink(os.path.join(site, *segs))
        if not ok:
            problems.append(f"index.html: refers to {_shown(ref)}; only existing files under assets/ are allowed")
        if len(problems) >= MAX_ERRORS:
            break
    return problems


def _unlisted(site: str) -> list[str]:
    """Files in ``data/`` that ``data/index.json`` does not name (the checker would never look at them)."""
    index = _read_small_json(os.path.join(site, "data", "index.json"))
    if not isinstance(index, dict) or not isinstance(index.get("scenes"), dict) or not isinstance(index.get("model"), dict):
        return []  # the checker reports the index itself
    listed = {"index.json"}
    for e in [index["model"], *index["scenes"].values()]:
        if isinstance(e, dict) and isinstance(e.get("file"), str):
            listed.add(e["file"])
    out = []
    data = os.path.join(site, "data")
    for d, _dirs, names in os.walk(data):
        for n in names:
            rel = os.path.relpath(os.path.join(d, n), data).replace(os.sep, "/")
            if rel not in listed:
                out.append(f"data/{rel}: not listed in data/index.json; a site's data holds only listed files")
    return sorted(out)[:MAX_ERRORS]


def check_upload(site: str, check_timeout: Optional[float] = CHECK_TIMEOUT) -> None:
    """The checks between unpacking and installing; raises :class:`Rejected` (422) with the first 20 errors."""
    if not os.path.isfile(os.path.join(site, "data", "index.json")):
        raise _invalid(["the upload has no data/index.json (is it a built site?)"])
    sentence = _schema_problem(site)
    if sentence:
        raise Rejected(422, "unsupported-schema", "Unsupported schema", sentence, errors=[sentence])
    rep = check_site(os.path.join(site, "data"), timeout=check_timeout, require_build_json=True)
    errors = list(rep.errors[:MAX_ERRORS]) + _unlisted(site) + _viewer_problems(site)
    if errors:
        raise _invalid(errors[:MAX_ERRORS])


def _limit_memory(limit: int) -> None:  # pragma: no cover - runs in the child process
    try:
        import resource
        for name in ("RLIMIT_AS", "RLIMIT_DATA"):
            lim = getattr(resource, name, None)
            if lim is not None:
                resource.setrlimit(lim, (limit, limit))
    except (ImportError, ValueError, OSError):
        pass


def check_in_child(site: str, check_timeout: Optional[float] = CHECK_TIMEOUT, memory: int = CHECK_MEMORY_BYTES) -> None:
    """:func:`check_upload` in a child process with a memory limit and a wall-clock limit, so no upload can take the
    instance down with it; raises :class:`Rejected` like :func:`check_upload`."""
    limit = (check_timeout or CHECK_TIMEOUT) + 30
    try:
        r = subprocess.run([sys.executable, "-m", "buildzr.site.deploy", "--check", site,
                            str(check_timeout if check_timeout is not None else 0), str(memory)],
                           capture_output=True, timeout=limit)
    except subprocess.TimeoutExpired:
        raise _invalid([f"check exceeded {limit:g} s"]) from None
    try:
        doc = json.loads(r.stdout.decode("utf-8").strip().splitlines()[-1])
    except (ValueError, IndexError, UnicodeDecodeError):
        doc = None
    if r.returncode == 0 and isinstance(doc, dict) and doc.get("ok") is True:
        return
    if isinstance(doc, dict) and isinstance(doc.get("problem"), dict):
        p = doc["problem"]
        raise Rejected(int(p["status"]), str(p["code"]), str(p["title"]), str(p["detail"]),
                       errors=[str(e) for e in p.get("errors") or []][:MAX_ERRORS])
    if r.returncode in (-9, 137) or b"MemoryError" in r.stderr:
        raise _invalid([f"the check needed more than {memory // (1024 * 1024)} MB of memory"])
    raise _invalid([f"the check failed ({r.returncode}): {r.stderr.decode('utf-8', 'replace').strip()[-200:]}"])


def _child_main(argv: list[str]) -> int:  # pragma: no cover - runs in the child process
    site, timeout, memory = argv[1], float(argv[2]), int(argv[3])
    _limit_memory(memory)
    try:
        check_upload(site, timeout or None)
    except Rejected as r:
        print(json.dumps({"problem": r.problem()}))
        return 1
    except MemoryError:
        print(json.dumps({"problem": _invalid([f"the check needed more than "
                                               f"{memory // (1024 * 1024)} MB of memory"]).problem()}))
        return 1
    print(json.dumps({"ok": True}))
    return 0


def file_hashes(site: str) -> dict[str, str]:
    """``{relative path: sha256}`` of every file below ``site`` (used for "unchanged")."""
    out = {}
    for d, _dirs, names in os.walk(site):
        for n in names:
            full = os.path.join(d, n)
            h = hashlib.sha256()
            with open(full, "rb") as f:
                for chunk in iter(lambda: f.read(1 << 16), b""):
                    h.update(chunk)
            out[os.path.relpath(full, site).replace(os.sep, "/")] = h.hexdigest()
    return out


# --- the listener --------------------------------------------------------------------------------------------


class DeployHandler(http.server.BaseHTTPRequestHandler):
    """The deploy listener's requests. Set up by :func:`make_deploy_server`; nothing here serves files."""

    server_version = "buildzr-deploy"
    sys_version = ""
    protocol_version = "HTTP/1.0"  # one request per connection
    timeout = 30  # the request line and the headers must arrive within this (the body has its own limit)

    store: Store
    max_upload: int
    body_timeout: float
    check_timeout: Optional[float]
    reader_base: str
    public_url: Optional[str]
    busy: threading.Lock
    _raw_path: Optional[str] = None
    _gated = False
    _timer: Optional[threading.Timer] = None

    def setup(self) -> None:
        super().setup()
        # the request line and the headers must all arrive within HEADER_TIMEOUT, not just each piece of them
        self._timer = threading.Timer(HEADER_TIMEOUT, self._cut)
        self._timer.daemon = True
        self._timer.start()

    def _cut(self) -> None:
        try:
            self.connection.shutdown(socket.SHUT_RDWR)
        except OSError:
            pass

    def finish(self) -> None:
        if self._timer is not None:
            self._timer.cancel()
        super().finish()

    def log_message(self, format: str, *args: Any) -> None:
        pass

    # --- answers ----------------------------------------------------------------------------------

    def _json(self, status: int, doc: dict[str, Any], ctype: str = "application/json",
              headers: Optional[dict[str, str]] = None) -> None:
        body = json.dumps(doc, ensure_ascii=False, separators=(",", ":")).encode()
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Connection", "close")
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        if self.command != "HEAD":
            self.wfile.write(body)
        self.close_connection = True

    def _problem(self, r: Rejected) -> None:
        self._json(r.status, r.problem(), "application/problem+json", r.headers)

    def send_error(self, code: int, message: Optional[str] = None, explain: Optional[str] = None) -> None:
        """Every error is problem details; a method this listener does not have is 405 (never a CORS answer)."""
        if code == 501:
            self._problem(Rejected(405, "method-not-allowed", "Method not allowed",
                                   f"{self.command} is not answered here", headers={"Allow": "GET, PUT, POST"}))
            return
        self._problem(Rejected(code, "bad-request" if code < 500 else "error", message or "Error",
                               message or "the request could not be read"))

    def _linger(self) -> None:
        """After an early answer to a request with a body: let the client finish sending, so it reads the answer."""
        try:
            self.wfile.flush()
            self.connection.shutdown(socket.SHUT_WR)
            end = time.monotonic() + 2.0
            while time.monotonic() < end:
                self.connection.settimeout(max(0.05, end - time.monotonic()))
                if not self.connection.recv(1 << 16):
                    break
        except OSError:
            pass

    # --- the checks every request goes through ---------------------------------------------------

    def _gate(self) -> str:
        """The Host and forwarded-header checks; returns the request path (without the query)."""
        payload = self.headers.get_payload()
        if payload or any(isinstance(d, (email.errors.MissingHeaderBodySeparatorDefect, email.errors.HeaderDefect))
                          for d in self.headers.defects):
            raise Rejected(400, "bad-headers", "Bad headers", "the request headers could not be read cleanly")
        hosts = self.headers.get_all("Host") or []
        if len(hosts) != 1 or not _HOST.fullmatch(hosts[0].strip().lower()):
            raise Rejected(403, "wrong-host", "Wrong Host",
                           "the Host header must be 127.0.0.1:PORT or localhost:PORT (this machine)")
        for h in FORWARDED:
            if self.headers.get(h) is not None:
                raise Rejected(403, "forwarded", "Forwarded request",
                               f"the deploy listener refuses requests that carry {h} (it must never sit behind a proxy)")
        return self.path.split("?", 1)[0]

    def _site_path(self) -> str:
        query = self.path.split("?", 1)[1] if "?" in self.path else ""
        try:
            pairs = parse_qsl(query, keep_blank_values=True, strict_parsing=False, errors="strict", max_num_fields=4)
        except (ValueError, UnicodeDecodeError):
            raise Rejected(400, "bad-query", "Bad query", "the query must be ?path=<site path>") from None
        keys = [k for k, _ in pairs]
        if any(k != "path" for k in keys) or len(keys) > 1:
            raise Rejected(400, "bad-query", "Bad query", "the only parameter is path, at most once")
        raw = pairs[0][1] if pairs else ""
        self._raw_path = raw[:200]
        try:
            return normalise_site_path(raw)
        except SitePathError as e:
            raise Rejected(400, "bad-path", "Bad site path", str(e)) from None

    def _deploy_header(self) -> None:
        if (self.headers.get_all("X-Buildzr-Deploy") or []) != ["1"]:
            raise Rejected(400, "not-a-deploy", "Missing X-Buildzr-Deploy", "deploy requests carry X-Buildzr-Deploy: 1")
        self._gated = True  # from here on a rejection is a deploy's and goes into the audit log

    # --- routing ----------------------------------------------------------------------------------

    def do_GET(self) -> None:
        self._route("GET")

    def do_PUT(self) -> None:
        self._route("PUT")

    def do_POST(self) -> None:
        self._route("POST")

    def _route(self, method: str) -> None:
        if self._timer is not None:
            self._timer.cancel()
        self._started = time.monotonic()
        self._raw_path = None
        self._body_pending = method in ("PUT", "POST") and (self.headers.get("Content-Length", "0").strip() not in ("", "0")
                                                           or self.headers.get("Transfer-Encoding") is not None)
        endpoints = {DEPLOY_ENDPOINT: "PUT", ROLLBACK_ENDPOINT: "POST", STATUS_ENDPOINT: "GET"}
        action = {DEPLOY_ENDPOINT: "deploy", ROLLBACK_ENDPOINT: "rollback"}
        path = self.path.split("?", 1)[0]
        try:
            path = self._gate()
            if path not in endpoints:
                raise Rejected(404, "not-found", "Not found",
                               f"the deploy listener answers only {', '.join(sorted(endpoints))}")
            if endpoints[path] != method:
                raise Rejected(405, "method-not-allowed", "Method not allowed",
                               f"{path} takes {endpoints[path]}", headers={"Allow": endpoints[path]})
            if path == STATUS_ENDPOINT:
                self._status()
            elif path == DEPLOY_ENDPOINT:
                self._deploy()
            else:
                self._rollback()
        except Rejected as r:
            if path in action and self._gated:  # a request that never got past the gate is not a deploy
                self._audit({"action": action[path], "path": self._raw_path, "result": "rejected",
                             "status": r.status, "error": (r.errors[0] if r.errors else r.detail)[:300]})
            self._problem(r)
            if self._body_pending:
                self._linger()
        except Exception as e:  # never a traceback to the client
            if path in action and self._gated:
                self._audit({"action": action[path], "path": self._raw_path, "result": "rejected", "status": 500,
                             "error": f"internal error: {type(e).__name__}: {str(e)[:200]}"})
            self._problem(Rejected(500, "internal-error", "Internal error", "the deploy failed inside the instance"))

    # --- the three requests ----------------------------------------------------------------------

    def _status(self) -> None:
        self._json(200, {"apiVersion": "1", "instanceVersion": VERSION, "store": self.store.dir,
                         "sites": len(self.store.table), "accepting": True,
                         "limits": {"maxUploadBytes": self.max_upload, "maxUnpackedBytes": MAX_UNPACKED_BYTES,
                                    "maxFiles": MAX_FILES, "bodyTimeoutSeconds": self.body_timeout,
                                    "checkTimeoutSeconds": self.check_timeout}})

    def _sender(self) -> Optional[str]:
        v = self.headers.get("X-Buildzr-Version")
        return v if v is not None and _VERSION.fullmatch(v) else None

    def _urls(self, site_path: str) -> tuple[str, str]:
        base = (self.public_url or self.reader_base) + "/" + (quote(site_path, safe="/") + "/" if site_path else "")
        return base, base + "api/v1/"

    def _length(self) -> int:
        if self.headers.get("Transfer-Encoding") is not None:
            raise Rejected(411, "length-required", "Length required",
                           "send Content-Length; chunked uploads are not accepted")
        values = self.headers.get_all("Content-Length") or []
        if not values:
            raise Rejected(411, "length-required", "Length required", "Content-Length is required")
        if len(values) != 1 or not re.fullmatch(r"[0-9]{1,15}", values[0].strip()):
            raise Rejected(400, "bad-length", "Bad Content-Length", "Content-Length must be one whole number")
        n = int(values[0])
        if n <= 0:
            raise Rejected(411, "length-required", "Length required", "Content-Length must be above 0")
        if n > self.max_upload:
            raise Rejected(413, "too-large", "Upload too large",
                           f"the upload is {n} bytes; this instance accepts {self.max_upload} bytes (--max-upload-mb)",
                           limitBytes=self.max_upload, uploadBytes=n)
        return n

    def _receive(self, n: int, dest: str) -> None:
        """Read exactly ``n`` body bytes into ``dest`` within the body time limit."""
        deadline = time.monotonic() + self.body_timeout
        got = 0
        try:
            with open(dest, "xb") as out:
                while got < n:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        raise socket.timeout()
                    self.connection.settimeout(left)
                    chunk = self.rfile.read1(min(1 << 16, n - got))
                    if not chunk:
                        break
                    out.write(chunk)
                    got += len(chunk)
        except (socket.timeout, TimeoutError):
            self._body_pending = False
            raise Rejected(408, "upload-too-slow", "Upload too slow",
                           f"the upload did not arrive within {self.body_timeout:g} s; nothing changed") from None
        except OSError as e:
            if _disk_full(e):
                raise _no_space() from None
            self._body_pending = False
            raise Rejected(400, "upload-incomplete", "Upload incomplete",
                           f"upload incomplete: the connection failed after {got} of {n} bytes; nothing changed") from None
        if got < n:
            self._body_pending = False
            raise Rejected(400, "upload-incomplete", "Upload incomplete",
                           f"upload incomplete: {got} of {n} bytes arrived; nothing changed")

    def _deploy(self) -> None:
        self._deploy_header()
        ctype = (self.headers.get("Content-Type") or "").split(";", 1)[0].strip().lower()
        if ctype != "application/gzip":
            raise Rejected(415, "unsupported-media-type", "Unsupported media type",
                           "the body must be Content-Type: application/gzip (a .tar.gz of the site)")
        n = self._length()
        site_path = self._site_path()
        if not self.busy.acquire(blocking=False):
            raise Rejected(409, "busy", "Busy", "another deploy or rollback is running; try again",
                           headers={"Retry-After": str(RETRY_AFTER)})
        work = os.path.join(self.store.dir, "incoming", secrets.token_hex(8))
        try:
            os.mkdir(work, 0o700)
            archive = os.path.join(work, "upload.tar.gz")
            self._receive(n, archive)
            self._body_pending = False
            site = os.path.join(work, "site")
            files, size = unpack(archive, site)
            check_in_child(site, self.check_timeout)
            route = self.store.table.route(site_path)
            sender = self._sender()
            viewer, api = self._urls(site_path)
            if route is not None and file_hashes(site) == file_hashes(route.current.dir):
                answer = {"ok": True, "path": site_path, "release": route.current.id,
                          "modelHash": route.current.model_hash, "previousModelHash": route.current.model_hash,
                          "unchanged": True}
            else:
                try:
                    done = self.store.install(site, site_path, log=False)
                except OSError as e:
                    if _disk_full(e):
                        raise _no_space() from None
                    raise
                answer = {"ok": True, "path": site_path, "release": done.release, "modelHash": done.model_hash,
                          "previousModelHash": done.previous_model_hash, "unchanged": False}
            answer.update({"files": files, "bytes": size, "senderVersion": sender, "instanceVersion": VERSION,
                           "viewerUrl": viewer, "apiUrl": api})
        except OSError as e:
            if _disk_full(e):
                raise _no_space() from None
            raise
        finally:
            shutil.rmtree(work, ignore_errors=True)
            self.busy.release()
        self._audit({"action": "deploy", "path": site_path, "result": "unchanged" if answer["unchanged"] else "ok",
                     "release": answer["release"], "modelHash": answer["modelHash"],
                     "previous": answer["previousModelHash"], "files": files, "bytes": size})
        self._json(200, answer)

    def _rollback(self) -> None:
        self._deploy_header()
        if self.headers.get("Transfer-Encoding") is not None or \
                (self.headers.get("Content-Length") or "0").strip() != "0":
            raise Rejected(400, "unexpected-body", "Unexpected body", "a rollback request has no body")
        site_path = self._site_path()
        if not self.busy.acquire(blocking=False):
            raise Rejected(409, "busy", "Busy", "another deploy or rollback is running; try again",
                           headers={"Retry-After": str(RETRY_AFTER)})
        try:
            route = self.store.table.route(site_path)
            if route is None:
                raise Rejected(404, "no-site", "No such site", f"there is no site at {site_path or '/'}")
            if route.previous is None:
                raise Rejected(409, "no-previous-release", "No previous release",
                               f"{site_path or '/'} has no previous release to roll back to")
            try:
                done = self.store.rollback(site_path, log=False)
            except StoreError as e:
                raise Rejected(409, "no-previous-release", "No previous release", str(e)) from None
        finally:
            self.busy.release()
        viewer, api = self._urls(site_path)
        self._audit({"action": "rollback", "path": site_path, "result": "ok", "release": done.release,
                     "modelHash": done.model_hash, "previous": done.previous_model_hash})
        self._json(200, {"ok": True, "path": site_path, "release": done.release, "modelHash": done.model_hash,
                         "previousModelHash": done.previous_model_hash, "rolledBack": True,
                         "instanceVersion": VERSION, "viewerUrl": viewer, "apiUrl": api})

    def _audit(self, fields: dict[str, Any]) -> None:
        """One line of 6.7 in ``deploys.log`` and on stderr. Only these fields; never a body or another header."""
        line: dict[str, Any] = {"time": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        line.update(fields)
        line["senderVersion"] = self._sender()
        line["client"] = self.client_address[0]
        line["ms"] = int((time.monotonic() - self._started) * 1000)
        try:
            self.store.audit(line)
        except OSError:
            pass
        print(json.dumps(line, separators=(",", ":"), ensure_ascii=True), file=sys.stderr, flush=True)


def make_deploy_server(store: Store, port: int = DEFAULT_DEPLOY_PORT, max_upload_bytes: int = DEFAULT_MAX_UPLOAD_MB
                       * 1024 * 1024, reader_base: str = "http://127.0.0.1:8000", public_url: Optional[str] = None,
                       body_timeout: float = BODY_TIMEOUT, check_timeout: Optional[float] = CHECK_TIMEOUT) -> "DeployServer":
    """The deploy listener for ``store``, bound to ``127.0.0.1:port`` (there is no way to bind it elsewhere)."""
    handler = type("StoreDeployHandler", (DeployHandler,), {
        "store": store, "max_upload": max_upload_bytes, "body_timeout": body_timeout, "check_timeout": check_timeout,
        "reader_base": reader_base.rstrip("/"), "public_url": public_url, "busy": threading.Lock()})
    return DeployServer((LOOPBACK, port), handler)


class DeployServer(Server):
    """The deploy listener's server: at most :data:`MAX_CONNECTIONS` connections are served at once."""

    def __init__(self, *args: Any, **kw: Any) -> None:
        self.slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
        super().__init__(*args, **kw)

    def process_request(self, request: Any, client_address: Any) -> None:
        if not self.slots.acquire(blocking=False):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except BaseException:
            self.slots.release()
            raise

    def process_request_thread(self, request: Any, client_address: Any) -> None:
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.slots.release()


def _reader_base(host: str, port: int) -> str:
    """The reading listener's address for links; an unspecified address is shown as this machine's loopback."""
    if host in ("", "0.0.0.0"):
        host = "127.0.0.1"
    elif host == "::":
        host = "::1"
    return f"http://[{host}]:{port}" if ":" in host else f"http://{host}:{port}"


def run_instance(store: Store, host: str = "127.0.0.1", port: int = 8000, deploy_port: int = DEFAULT_DEPLOY_PORT,
                 max_upload_mb: int = DEFAULT_MAX_UPLOAD_MB, public_url: Optional[str] = None,
                 cors_origins: tuple[str, ...] = ()) -> None:
    """Serve ``store`` read only on ``host:port`` and accept deploys on ``127.0.0.1:deploy_port`` until interrupted."""
    reader = make_store_server(store, host, port, public_url, cors_origins)
    try:
        deployer = make_deploy_server(store, deploy_port, max_upload_mb * 1024 * 1024,
                                      _reader_base(host, reader.server_address[1]), public_url)
    except OSError:
        reader.server_close()
        raise
    n = len(store.table)
    print(f"Serving store {store.dir} ({n} site{'' if n == 1 else 's'}) at "
          f"http://{host}:{reader.server_address[1]}/ (read only)")
    print(f"Accepting deploys at http://{LOOPBACK}:{deployer.server_address[1]}/ (this machine only; no authentication)",
          flush=True)
    t = threading.Thread(target=deployer.serve_forever, name="buildzr-deploy", daemon=True)
    t.start()
    try:
        reader.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        deployer.shutdown()
        deployer.server_close()
        reader.server_close()


if __name__ == "__main__":  # pragma: no cover - the checker's child process
    if len(sys.argv) == 5 and sys.argv[1] == "--check":
        sys.exit(_child_main(sys.argv[1:]))
    sys.exit(2)
