"""The site store: site path rules, layout, install, rollback, crash safety, routing table (no HTTP)."""

from __future__ import annotations

import hashlib
import json
import os
import shutil
from pathlib import Path
from typing import Any

import pytest

from buildzr.site.store import (
    RESERVED, STORE_FILE, SitePathError, Store, StoreError, normalise_site_path, site_key)
from tests.site.store_helpers import model_hash_of_variant, put, tree, variant
from tests.site.test_cli import WS_TEXT, build, make_static


@pytest.fixture(scope="module")
def base_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("storebase")
    (tmp / "workspace.py").write_text(WS_TEXT)
    build(str(tmp / "workspace.py"), tmp / "site", make_static(tmp / "static"))
    return tmp / "site"


@pytest.fixture
def variants(base_site: Path, tmp_path: Path) -> list[Path]:
    return [variant(base_site, tmp_path / f"v{n}", n) for n in range(1, 6)]


@pytest.fixture
def store(tmp_path: Path) -> Store:
    return Store.open(str(tmp_path / "store"), create=True)


class Crash(BaseException):
    """A kill: not an Exception, so the code under test cannot clean up after it."""


# --- site paths -----------------------------------------------------------------------------------------


@pytest.mark.parametrize("raw,canon", [("", ""), ("/", ""), ("pr/42", "pr/42"), ("/pr/42/", "pr/42"), ("a.b_c-d/x1", "a.b_c-d/x1"),
                                       ("a/b/c/d/e/f/g/h", "a/b/c/d/e/f/g/h")])
def test_site_paths_that_are_fine(raw: str, canon: str) -> None:
    assert normalise_site_path(raw) == canon


@pytest.mark.parametrize("raw,word", [
    ("pr//42", "empty"), ("pr/./42", "'.'"), ("../x", "'..'"), ("pr/..", "'..'"), ("a\\b", "backslash"),
    ("a\0b", "NUL"), ("PR/42", "must match"), ("pr/ 42", "must match"), (".hidden", "must match"),
    ("-x", "must match"), ("a/b/c/d/e/f/g/h/i", "segments"), ("a" * 129, "characters"), ("pr/é", "must match"),
    *[(f"pr/{r}", "reserved") for r in sorted(RESERVED)], *[(f"{r}/x", "reserved") for r in sorted(RESERVED)],
    ("data/x", "reserved"), ("a/api", "reserved")])
def test_site_paths_that_are_refused(raw: str, word: str) -> None:
    with pytest.raises(SitePathError) as e:
        normalise_site_path(raw)
    assert word in str(e.value)


def test_site_key_is_a_hash_of_the_path() -> None:
    assert site_key("pr/42") == hashlib.sha256(b"pr/42").hexdigest()[:16]
    assert len(site_key("")) == 16 and site_key("") != site_key("pr/42")


# --- opening --------------------------------------------------------------------------------------------


def test_open_refuses_a_folder_that_is_not_a_store(tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="not a buildzr store"):
        Store.open(str(tmp_path))
    with pytest.raises(StoreError, match="not a buildzr store"):
        Store.open(str(tmp_path / "missing"))


def test_create_makes_the_layout_and_refuses_a_folder_with_other_files(tmp_path: Path) -> None:
    s = Store.open(str(tmp_path / "s"), create=True)
    assert sorted(os.listdir(s.dir)) == ["buildzr-store.json", "incoming", "sites"]
    assert json.loads((tmp_path / "s" / STORE_FILE).read_text()) == {"sites": {}, "version": 1}
    (tmp_path / "other").mkdir()
    (tmp_path / "other" / "x.txt").write_text("hi")
    with pytest.raises(StoreError, match="not an empty folder"):
        Store.open(str(tmp_path / "other"), create=True)
    Store.open(str(tmp_path / "s"), create=True)  # an existing store opens as it is


# --- install and rollback -------------------------------------------------------------------------------


def test_install_layout_and_release_numbers(store: Store, variants: list[Path]) -> None:
    r1 = put(store, variants[0], "pr/42")
    assert (r1.release, r1.previous_model_hash) == ("r-0001", None)
    r2 = put(store, variants[1], "pr/42")
    assert (r2.release, r2.previous_model_hash) == ("r-0002", model_hash_of_variant(1))
    key = site_key("pr/42")
    assert (Path(store.dir) / "sites" / key / "r-0002" / "data" / "index.json").is_file()
    assert (Path(store.dir) / "sites" / key / "r-0001").is_dir()
    r3 = put(store, variants[2], "pr/42")
    assert r3.release == "r-0003"
    assert sorted(os.listdir(Path(store.dir) / "sites" / key)) == ["r-0002", "r-0003"]  # the oldest is gone
    assert os.listdir(Path(store.dir) / "incoming") == []
    route = store.table.route("pr/42")
    assert route and route.current.id == "r-0003" and route.previous and route.previous.id == "r-0002"
    assert route.current.model_hash == model_hash_of_variant(3)
    saved = json.loads((Path(store.dir) / STORE_FILE).read_text())
    assert saved["sites"]["pr/42"] == {"last": 3, "current": {"release": "r-0003", "modelHash": model_hash_of_variant(3)},
                                       "previous": {"release": "r-0002", "modelHash": model_hash_of_variant(2)}}
    assert "pr" not in tree(store.dir) and not any("pr" in p.split("/")[0] for p in tree(store.dir) if p.startswith("sites"))


def test_install_refuses_a_folder_outside_incoming(store: Store, variants: list[Path], tmp_path: Path) -> None:
    with pytest.raises(StoreError, match="under incoming/"):
        store.install(str(variants[0]), "x")
    inside = Path(store.dir) / "sites"
    inside.mkdir(exist_ok=True)
    with pytest.raises(StoreError, match="under incoming/"):
        store.install(str(inside), "x")
    with pytest.raises(StoreError, match="under incoming/"):
        store.install(os.path.join(store.dir, "incoming"), "x")
    link = Path(store.dir) / "incoming" / "link"
    link.symlink_to(variants[0])
    with pytest.raises(StoreError, match="under incoming/"):
        store.install(str(link), "x")
    assert variants[0].is_dir() and len(store.table) == 0


def test_install_refuses_bad_site_paths_and_sites_without_a_model_hash(store: Store, variants: list[Path]) -> None:
    with pytest.raises(SitePathError):
        put(store, variants[0], "data/x")
    inc = Path(store.dir) / "incoming" / "empty"
    inc.mkdir()
    with pytest.raises(StoreError, match="modelHash"):
        store.install(str(inc), "x")
    assert inc.is_dir()


def test_rollback_swaps_and_a_new_install_never_reuses_a_number(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "")
    with pytest.raises(StoreError, match="no previous"):
        store.rollback("")
    put(store, variants[1], "")
    back = store.rollback("")
    assert back.release == "r-0001" and back.model_hash == model_hash_of_variant(1)
    assert back.previous_model_hash == model_hash_of_variant(2)
    route = store.table.route("")
    assert route and (route.current.id, route.previous.id if route.previous else None) == ("r-0001", "r-0002")
    again = store.rollback("")
    assert again.release == "r-0002"
    store.rollback("")
    nxt = put(store, variants[2], "")  # current r-0001, previous r-0002: the new one is r-0003, r-0002 is kept
    assert nxt.release == "r-0003"
    assert sorted(os.listdir(Path(store.dir) / "sites" / site_key(""))) == ["r-0001", "r-0003"]
    with pytest.raises(StoreError, match="no site"):
        store.rollback("nothing/here")


def test_the_audit_log_has_one_line_per_operation(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "pr/1")
    put(store, variants[1], "pr/1")
    store.rollback("pr/1")
    put(store, variants[2], "pr/2")
    with pytest.raises(StoreError):
        store.rollback("pr/2")
    lines = [json.loads(x) for x in (Path(store.dir) / "deploys.log").read_text().splitlines()]
    assert [(x["action"], x["release"], x["result"]) for x in lines[:3]] == [
        ("install", "r-0001", "ok"), ("install", "r-0002", "ok"), ("rollback", "r-0001", "ok")]
    assert lines[1]["previousModelHash"] == model_hash_of_variant(1) and lines[1]["sitePath"] == "pr/1"
    assert lines[1]["modelHash"] == model_hash_of_variant(2) and "time" in lines[1]
    assert (lines[4]["action"], lines[4]["result"]) == ("rollback", "refused: no previous release")
    assert all(set(x) == {"time", "sitePath", "release", "modelHash", "previousModelHash", "action", "result"} for x in lines)


# --- the route table ------------------------------------------------------------------------------------


def test_lookup_is_longest_prefix_on_whole_segments(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "pr/42")
    put(store, variants[1], "pr")
    t = store.table
    pr42 = t.route("pr/42")
    assert pr42
    assert t.lookup("/pr/42/data/index.json") == ("pr/42", pr42.current.dir, "/data/index.json")
    assert t.lookup("/pr/42/") == ("pr/42", pr42.current.dir, "/")
    assert t.lookup("/pr/42") == ("pr/42", pr42.current.dir, "")
    other = t.lookup("/pr/420/")
    assert other is not None and other[0] == "pr" and other[2] == "/420/"  # not pr/42
    assert t.lookup("/pr/43/x") is not None and t.lookup("/pr/43/x")[0] == "pr"  # type: ignore[index]
    assert t.lookup("/nothing/") is None  # no root site
    assert t.lookup("") is None and t.lookup("pr/42") is None


def test_the_root_site_catches_what_no_other_site_claims(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "")
    put(store, variants[1], "pr/42")
    t = store.table
    root = t.route("")
    assert root
    assert t.lookup("/") == ("", root.current.dir, "/")
    assert t.lookup("/data/index.json") == ("", root.current.dir, "/data/index.json")
    assert t.lookup("/pr/") == ("", root.current.dir, "/pr/")
    got = t.lookup("/pr/420/x")
    assert got is not None and got[0] == ""
    got = t.lookup("/pr/42/x")
    assert got is not None and got[0] == "pr/42"


def test_readers_keep_the_snapshot_they_took(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "")
    before = store.table
    old = before.lookup("/")
    put(store, variants[1], "")
    assert before.lookup("/") == old
    assert store.table.lookup("/") != old


# --- crash safety ---------------------------------------------------------------------------------------

INSTALL_STEPS = ["renamed", "store-tmp-written", "store-replaced", "routed", "pruned", "logged"]
ROLLBACK_STEPS = ["store-tmp-written", "store-replaced", "routed", "logged"]


def _consistent(directory: str) -> tuple[Store, dict[str, Any]]:
    """Reopen the store; every listed release exists, nothing else is left, every route answers."""
    s = Store.open(directory)
    saved = json.loads((Path(directory) / STORE_FILE).read_text())
    listed = set()
    for sp, entry in saved["sites"].items():
        for part in ("current", "previous"):
            if entry[part]:
                listed.add((site_key(sp), entry[part]["release"]))
    on_disk = {(k, r) for k in os.listdir(Path(directory) / "sites") for r in os.listdir(Path(directory) / "sites" / k)}
    assert on_disk == listed
    assert os.listdir(Path(directory) / "incoming") == []
    assert not [n for n in os.listdir(directory) if n.endswith(".tmp")]
    for r in s.table.routes():
        assert os.path.isfile(os.path.join(r.current.dir, "data", "index.json"))
        assert saved["sites"][r.site_path]["current"]["release"] == r.current.id
    return s, saved


@pytest.mark.parametrize("step", INSTALL_STEPS)
def test_a_kill_at_every_install_step_leaves_a_consistent_store(step: str, store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "pr/42")
    put(store, variants[1], "pr/42")
    put(store, variants[2], "other")

    def hook(name: str) -> None:
        if name == step:
            raise Crash(name)
    store.hook = hook
    with pytest.raises(Crash):
        put(store, variants[3], "pr/42")
    s, saved = _consistent(store.dir)
    cur = saved["sites"]["pr/42"]["current"]["modelHash"]
    # before the new store file replaced the old one the old state stands; from then on the new one
    if step in ("renamed", "store-tmp-written"):
        assert cur == model_hash_of_variant(2) and saved["sites"]["pr/42"]["last"] == 2
    else:
        assert cur == model_hash_of_variant(4) and saved["sites"]["pr/42"]["last"] == 3
    assert saved["sites"]["other"]["current"]["modelHash"] == model_hash_of_variant(3)
    nxt = put(s, variants[4], "pr/42")  # and the store keeps working
    assert nxt.release == ("r-0003" if step in ("renamed", "store-tmp-written") else "r-0004")
    _consistent(s.dir)


@pytest.mark.parametrize("step", ROLLBACK_STEPS)
def test_a_kill_at_every_rollback_step_leaves_a_consistent_store(step: str, store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "")
    put(store, variants[1], "")

    def hook(name: str) -> None:
        if name == step:
            raise Crash(name)
    store.hook = hook
    with pytest.raises(Crash):
        store.rollback("")
    s, saved = _consistent(store.dir)
    expected = model_hash_of_variant(2) if step == "store-tmp-written" else model_hash_of_variant(1)
    assert saved["sites"][""]["current"]["modelHash"] == expected


def test_a_failing_write_rolls_the_rename_back(store: Store, variants: list[Path], monkeypatch: pytest.MonkeyPatch) -> None:
    put(store, variants[0], "")

    def hook(name: str) -> None:
        if name == "store-tmp-written":
            raise OSError("disk full")
    store.hook = hook
    with pytest.raises(OSError):
        put(store, variants[1], "")
    route = store.table.route("")
    assert route and route.current.id == "r-0001"
    assert os.listdir(Path(store.dir) / "sites" / site_key("")) == ["r-0001"]
    store.hook = None
    assert put(store, variants[1], "").release == "r-0002"


def test_restart_reads_the_store_and_cleans_up(store: Store, variants: list[Path]) -> None:
    put(store, variants[0], "pr/42")
    put(store, variants[1], "pr/42")
    put(store, variants[2], "")
    d = Path(store.dir)
    (d / "sites" / site_key("pr/42") / "r-0009").mkdir()  # an orphan release
    (d / "sites" / site_key("pr/42") / "r-0009" / "x").write_text("x")
    (d / "sites" / "0123456789abcdef").mkdir()  # an orphan site folder
    (d / "sites" / "stray-file").write_text("x")
    (d / "incoming" / "half-unpacked").mkdir()
    (d / "incoming" / "half-unpacked" / "f").write_text("x")
    (d / (STORE_FILE + ".abc.tmp")).write_text("{")
    s = Store.open(str(d))
    assert sorted(os.listdir(d / "sites")) == sorted([site_key("pr/42"), site_key("")])
    assert sorted(os.listdir(d / "sites" / site_key("pr/42"))) == ["r-0001", "r-0002"]
    assert os.listdir(d / "incoming") == [] and not (d / (STORE_FILE + ".abc.tmp")).exists()
    assert [r.site_path for r in s.table.routes()] == ["", "pr/42"]
    route = s.table.route("pr/42")
    assert route and route.current.id == "r-0002" and route.previous and route.previous.id == "r-0001"
    assert s.table.lookup("/pr/42/") is not None


# --- a damaged store file -------------------------------------------------------------------------------


def _store_with_file(tmp_path: Path, text: str, make_release: bool = True) -> str:
    d = tmp_path / "bad"
    (d / "sites" / site_key("x") / "r-0001").mkdir(parents=True)
    (d / "incoming").mkdir()
    (d / STORE_FILE).write_text(text)
    if not make_release:
        shutil.rmtree(d / "sites" / site_key("x") / "r-0001")
    return str(d)


def _entry(**over: Any) -> str:
    e: dict[str, Any] = {"last": 1, "current": {"release": "r-0001", "modelHash": "sha256:a"}, "previous": None}
    e.update(over)
    return json.dumps({"version": 1, "sites": {"x": e}})


@pytest.mark.parametrize("text,word", [
    ("", "not valid JSON"), ("{", "not valid JSON"), ("[]", "expected an object"), ("null", "expected an object"),
    ('{"version":1}', "expected an object"), ('{"version":2,"sites":{}}', "unknown version"),
    ('{"version":true,"sites":{}}', "unknown version"), ('{"version":1,"sites":[]}', "'sites' must be an object"),
    ('{"version":1,"sites":{"../x":{}}}', "'..'"), ('{"version":1,"sites":{"/x":{}}}', "canonical form"),
    ('{"version":1,"sites":{"data":{}}}', "reserved"), ('{"version":1,"sites":{"x":5}}', "expected 'last'"),
    (_entry(last=0), "'last'"), (_entry(last="1"), "'last'"), (_entry(current=None), "'current'"),
    (_entry(current={"release": "../../etc", "modelHash": "x"}), "not like r-0007"),
    (_entry(current={"release": "r-0001"}), "'current'"),
    (_entry(current={"release": "r-0001", "modelHash": 5}), "modelHash"),
    (_entry(previous={"release": "r-0001", "modelHash": "sha256:a"}), "same release"),
    (_entry(last=1, current={"release": "r-0002", "modelHash": "x"}), "newer than 'last'"),
])
def test_corrupt_store_files_are_errors_not_tracebacks(tmp_path: Path, text: str, word: str) -> None:
    d = _store_with_file(tmp_path, text)
    with pytest.raises(StoreError) as e:
        Store.open(d)
    assert word in str(e.value) and "\n" not in str(e.value) and STORE_FILE in str(e.value)


def test_a_listed_release_that_is_missing_is_an_error(tmp_path: Path) -> None:
    d = _store_with_file(tmp_path, _entry(), make_release=False)
    with pytest.raises(StoreError, match="listed but missing"):
        Store.open(d)


def test_a_release_that_resolves_outside_sites_is_an_error(tmp_path: Path) -> None:
    d = _store_with_file(tmp_path, _entry())
    release = Path(d) / "sites" / site_key("x") / "r-0001"
    release.rmdir()
    outside = tmp_path / "outside"
    outside.mkdir()
    release.symlink_to(outside)
    with pytest.raises(StoreError, match="outside sites/"):
        Store.open(d)
    assert outside.is_dir()
