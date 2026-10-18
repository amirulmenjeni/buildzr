"""check_built on untrusted input: containment, no exceptions, build.json and the time limit."""

from __future__ import annotations

import builtins
import copy
import hashlib
import json
import os
import shutil
import sys
from pathlib import Path
from typing import Any, Callable, Iterator

import pytest

from buildzr.site import canonical
from buildzr.site.canonical import dumps
from buildzr.site.check import _FILE_RE, check_built, main

SMALL = Path(__file__).parent / "fixtures" / "small"
SCHEMA = Path(__file__).parents[2] / "buildzr" / "site" / "schema" / "index.schema.json"


@pytest.fixture(params=["with-jsonschema", "without-jsonschema"])
def schema_mode(request: pytest.FixtureRequest, monkeypatch: pytest.MonkeyPatch) -> str:
    """Run a test with and without ``jsonschema`` importable (the checker skips the schema step then)."""
    if request.param == "without-jsonschema":
        monkeypatch.setitem(sys.modules, "jsonschema", None)  # `import jsonschema` raises ImportError
    return str(request.param)


def _site(tmp_path: Path) -> Path:
    d = tmp_path / "site" / "data"
    shutil.copytree(SMALL, d)
    return d


def _rehash(d: Path, rel: str) -> None:
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    for e in [idx["model"], *idx["scenes"].values()]:
        if e["file"] == rel:
            e["hash"] = "sha256:" + hashlib.sha256((d / rel).read_bytes()).hexdigest()
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")


class _Opened:
    """Records the real path of every file ``open()`` is called on."""

    def __init__(self) -> None:
        self.paths: list[str] = []


@pytest.fixture
def opened(monkeypatch: pytest.MonkeyPatch) -> Iterator[_Opened]:
    rec = _Opened()
    real_open = builtins.open

    def spy(file: Any, *a: Any, **kw: Any) -> Any:
        if isinstance(file, (str, bytes, os.PathLike)):
            rec.paths.append(os.path.realpath(os.fsdecode(file)))
        return real_open(file, *a, **kw)

    monkeypatch.setattr(builtins, "open", spy)
    yield rec


# --- containment ---------------------------------------------------------------


def test_file_pattern_in_schema_matches_the_code() -> None:
    import re

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    pat = re.compile(schema["$defs"]["file"]["properties"]["file"]["pattern"])
    for good in ["model.json", "scene/e/billing.3f2a9c1b.json", "a/b/c.d-e_f", ".hidden", "a..b/c"]:
        assert pat.search(good) and _FILE_RE.fullmatch(good), good
    for bad in ["", "/etc/passwd", "../x", "a/../x", "sub/../../x", "a/..", "..", ".", "./a", "a/./b", "a//b",
                "a/", "C:/x", "C:\\x", "a\\b", "a\x00b", "a b", "é"]:
        assert not pat.search(bad), bad
        assert not (_FILE_RE.fullmatch(bad) and "." not in bad.split("/") and ".." not in bad.split("/")), bad
    assert not _FILE_RE.fullmatch("a\n")  # Python's `$` alone would accept this


def test_schema_rejects_bad_file_entries() -> None:
    import jsonschema  # type: ignore[import-untyped]

    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    idx = json.loads((SMALL / "index.json").read_text(encoding="utf-8"))
    v = jsonschema.Draft202012Validator(schema)
    assert not list(v.iter_errors(idx))
    for bad in ["../../etc/passwd", "/etc/passwd", "sub/../../x", "a/./b"]:
        t = copy.deepcopy(idx)
        t["model"]["file"] = bad
        assert list(v.iter_errors(t)), bad


@pytest.mark.parametrize("bad", ["../../etc/passwd", "/etc/passwd", "sub/../../x", "..", "a/./b", "C:/x",
                                 "a\\..\\b", "a\x00b", "", 5, None, ["model.json"]])
def test_escaping_file_entries_are_errors(tmp_path: Path, schema_mode: str, opened: _Opened, bad: Any) -> None:
    d = _site(tmp_path)
    secret = tmp_path / "secret.json"
    secret.write_text("{}", encoding="utf-8")
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    idx["model"]["file"] = bad
    idx["scenes"]["landscape"]["file"] = os.path.relpath(secret, d).replace(os.sep, "/")  # ../../secret.json
    idx["scenes"]["e/billing"]["file"] = str(secret)  # absolute
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")
    opened.paths.clear()  # only what the checker opens counts
    rep = check_built(str(d))
    assert any(e.startswith("model.json") or "['model', 'file']" in e for e in rep.errors), rep.errors
    if isinstance(bad, str):
        assert any(e.startswith("model.json") and "inside data/" in e for e in rep.errors), rep.errors
    assert any(e.startswith("scene landscape") and "inside data/" in e for e in rep.errors)
    assert any(e.startswith("scene e/billing") and "inside data/" in e for e in rep.errors)
    root = os.path.realpath(d)
    schema_dir = os.path.realpath(str(SCHEMA.parent))
    for p in opened.paths:
        assert os.path.commonpath([root, p]) == root or os.path.commonpath([schema_dir, p]) == schema_dir, p
    assert os.path.realpath(secret) not in opened.paths


def test_symlink_escape_is_an_error(tmp_path: Path, schema_mode: str, opened: _Opened) -> None:
    d = _site(tmp_path)
    secret = tmp_path / "secret.json"
    secret.write_text("{}", encoding="utf-8")
    os.symlink(secret, d / "link.json")
    os.symlink(tmp_path, d / "linkdir")
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    idx["model"]["file"] = "link.json"
    idx["scenes"]["landscape"]["file"] = "linkdir/secret.json"
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")
    opened.paths.clear()
    rep = check_built(str(d))
    assert sum("inside data/" in e for e in rep.errors) == 2, rep.errors
    assert os.path.realpath(secret) not in opened.paths


def test_symlink_inside_data_is_fine(tmp_path: Path) -> None:
    d = _site(tmp_path)
    os.symlink(d / "model.json", d / "alias.json")
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    idx["model"]["file"] = "alias.json"
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")
    assert check_built(str(d)).errors == []


def test_index_json_symlink_out_of_data(tmp_path: Path, opened: _Opened) -> None:
    d = _site(tmp_path)
    outside = tmp_path / "outside.json"
    shutil.move(d / "index.json", outside)
    os.symlink(outside, d / "index.json")
    opened.paths.clear()
    rep = check_built(str(d))
    assert rep.errors and "inside the data directory" in rep.errors[0]
    assert os.path.realpath(outside) not in opened.paths


def test_directory_and_fifo_entries_do_not_crash_or_hang(tmp_path: Path, schema_mode: str) -> None:
    d = _site(tmp_path)
    os.mkdir(d / "adir")
    os.mkfifo(d / "fifo")
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    idx["model"]["file"] = "adir"
    idx["scenes"]["landscape"]["file"] = "fifo"
    (d / "index.json").write_text(dumps(idx), encoding="utf-8")
    rep = check_built(str(d))
    assert sum("not a regular file" in e for e in rep.errors) == 2, rep.errors


# --- exceptions are errors -----------------------------------------------------


def _files(d: Path) -> list[str]:
    return ["index.json"] + sorted(str(p.relative_to(d)).replace(os.sep, "/")
                                   for p in d.rglob("*.json") if p.name not in ("index.json", "levels.json"))


def _write(d: Path, rel: str, data: bytes) -> None:
    (d / rel).write_bytes(data)
    if rel != "index.json":
        _rehash(d, rel)


def _mutations(d: Path) -> list[tuple[str, Callable[[Path], None]]]:
    out: list[tuple[str, Callable[[Path], None]]] = []
    for rel in _files(d):
        raw = (d / rel).read_bytes()
        obj = json.loads(raw)

        def put(r: str, b: bytes) -> Callable[[Path], None]:
            return lambda dd: _write(dd, r, b)

        out.append((f"{rel}: empty", put(rel, b"")))
        out.append((f"{rel}: truncated", put(rel, raw[: len(raw) // 2])))
        out.append((f"{rel}: not utf-8", put(rel, b"\xff\xfe\x00{")))
        out.append((f"{rel}: top-level list", put(rel, dumps([obj]).encode())))
        out.append((f"{rel}: top-level string", put(rel, dumps("x").encode())))
        out.append((f"{rel}: deeply nested", put(rel, b"[" * 100000 + b"]" * 100000)))
        for k in sorted(obj):
            if k == "schema":
                continue  # a wrong schema name stops that file's checks by design; covered below
            dele = copy.deepcopy(obj)
            del dele[k]
            out.append((f"{rel}: delete {k}", put(rel, dumps(dele).encode())))
            for name, val in (("int", 0), ("str", "x"), ("null", None), ("list", [])):
                if obj[k] == val:
                    continue  # not a mutation
                sw = copy.deepcopy(obj)
                sw[k] = val
                out.append((f"{rel}: {k} -> {name}", put(rel, dumps(sw).encode())))
    return out


def test_mutated_sites_never_raise_and_are_reported(tmp_path: Path, schema_mode: str) -> None:
    base = _site(tmp_path / "base")
    muts = _mutations(base)
    assert len(muts) >= 30
    missed = []
    for i, (name, fn) in enumerate(muts):
        d = tmp_path / "m" / str(i) / "data"
        shutil.copytree(base, d)
        fn(d)
        rep = check_built(str(d))  # must not raise
        if not rep.errors:
            missed.append(name)
        shutil.rmtree(d.parent)
    # Still valid sites: a title is any string, and an authored view may have no edges.
    missed = [m for m in missed if not m.endswith(": title -> str")
              and not (m.startswith("scene/v/") and m.endswith(": edges -> list"))]
    if schema_mode == "with-jsonschema":
        assert missed == [], missed
    else:
        # Without jsonschema only the checker's own rules apply: a key it never reads (title, layout, ...)
        # can change unnoticed. Damage to the files themselves must still be reported.
        assert [m for m in missed if ": delete " not in m and " -> " not in m] == [], missed


@pytest.mark.parametrize("raw", [b"not json", b"", b"[", b"\xff", b"{}", b"[]", b"null", b'{"schema":"buildzr.index/2"}',
                                 b'{"schema":"buildzr.index/2","modelHash":1,"model":[],"scenes":[]}'])
def test_bad_index_json(tmp_path: Path, schema_mode: str, raw: bytes) -> None:
    d = _site(tmp_path)
    (d / "index.json").write_bytes(raw)
    assert check_built(str(d)).errors


def test_missing_data_dir_and_index(tmp_path: Path) -> None:
    assert check_built(str(tmp_path / "nope")).errors
    assert check_built(str(tmp_path)).errors


def test_parent_cycles_do_not_hang(tmp_path: Path, schema_mode: str) -> None:
    d = _site(tmp_path)
    m = json.loads((d / "model.json").read_text(encoding="utf-8"))
    a, b = m["elements"][0], m["elements"][1]
    a["parent"], b["parent"] = b["id"], a["id"]
    m["modelHash"] = canonical.model_hash(m)
    (d / "model.json").write_text(dumps(m), encoding="utf-8")
    _rehash(d, "model.json")
    s = json.loads((d / "scene/landscape.json").read_text(encoding="utf-8"))
    n0, n1 = s["nodes"][0], s["nodes"][1]
    n0["parent"], n1["parent"] = n1["id"], n0["id"]
    (d / "scene/landscape.json").write_text(dumps(s), encoding="utf-8")
    _rehash(d, "scene/landscape.json")
    assert check_built(str(d), timeout=20).errors


# --- build.json ------------------------------------------------------------------


def test_build_json_checks(tmp_path: Path) -> None:
    site = tmp_path / "site"
    d = site / "data"
    shutil.copytree(SMALL, d)
    idx = json.loads((d / "index.json").read_text(encoding="utf-8"))
    assert check_built(str(d)).errors == []  # not present: fine unless required
    assert check_built(str(d), require_build_json=True).errors == ["build.json: missing"]
    canonical.write(str(site / "build.json"), {"modelHash": idx["modelHash"], "k": 4})
    assert check_built(str(d), require_build_json=True).errors == []
    canonical.write(str(site / "build.json"), {"modelHash": "sha256:" + "0" * 64})
    assert any("modelHash" in e for e in check_built(str(d)).errors)
    (site / "build.json").write_text("{", encoding="utf-8")
    assert any(e.startswith("build.json") for e in check_built(str(d)).errors)
    canonical.write(str(site / "build.json"), [1])
    assert any(e.startswith("build.json") for e in check_built(str(d)).errors)
    (site / "build.json").unlink()
    os.symlink(tmp_path / "elsewhere.json", site / "build.json")
    assert any("symlink" in e for e in check_built(str(d)).errors)


# --- time limit ------------------------------------------------------------------


def test_tiny_timeout_stops_cleanly() -> None:
    rep = check_built(str(SMALL), timeout=1e-9)
    assert rep.errors == ["check: check exceeded 1e-09 s"]
    rep = check_built(str(SMALL), timeout=0)
    assert rep.errors == ["check: check exceeded 0 s"]


def test_timeout_inside_the_loops(monkeypatch: pytest.MonkeyPatch) -> None:
    """Expire the clock after the first phases: the pair loops themselves must notice."""
    import buildzr.site.check as c

    calls = {"n": 0}
    real = c._Deadline.check

    def check(self: Any) -> None:
        calls["n"] += 1
        if calls["n"] > 6:
            raise c._Timeout()
        real(self)

    monkeypatch.setattr(c._Deadline, "check", check)
    rep = check_built(str(SMALL))
    assert rep.errors == ["check: check exceeded 60 s"]
    assert calls["n"] > 6


def test_default_and_no_limit_give_the_same_result() -> None:
    a = check_built(str(SMALL))
    b = check_built(str(SMALL), timeout=None)
    c = check_built(str(SMALL), timeout=1000)
    assert a.errors == b.errors == c.errors == []
    assert a.metrics == b.metrics == c.metrics


def test_cli_timeout_flag(capsys: pytest.CaptureFixture[str]) -> None:
    assert main([str(SMALL)]) == 0
    assert main(["--timeout", "0", str(SMALL)]) == 0  # 0 means no limit
    assert main(["--timeout", "1e-9", str(SMALL)]) == 1
    assert "check exceeded" in capsys.readouterr().out
