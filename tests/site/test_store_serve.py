"""``serve --store``: several sites on one instance, routing, previous-release fallback, per-site API, read only."""

from __future__ import annotations

import http.client
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator, Optional

import pytest

import buildzr.site.cli as cli
from buildzr.site.build import build_site
from buildzr.site.serve import StoreHandler, make_server, make_store_server, normalise_url_path
from buildzr.site.store import Store, site_key
from tests.site.store_helpers import model_hash_of_variant, put, tree, variant
from tests.site.test_cli import ROOT, WS_TEXT, build, make_static, needs_node  # noqa: F401

EXAMPLE_PY = os.path.join(ROOT, "examples", "buildzr_models_example.py")
Json = dict[str, Any]


@pytest.fixture(scope="module")
def base_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    tmp = tmp_path_factory.mktemp("storeservebase")
    (tmp / "workspace.py").write_text(WS_TEXT)
    build(str(tmp / "workspace.py"), tmp / "site", make_static(tmp / "static"))
    return tmp / "site"


def call(port: int, method: str, path: str, headers: Optional[dict[str, str]] = None, body: Optional[bytes] = None
         ) -> tuple[int, dict[str, str], bytes]:
    """One request on a new connection. A connect that stalls (seen in the devcontainer under 8 busy readers: the server
    idles in select while the client waits for the handshake) is tried again; an answer is never retried."""
    for attempt in range(8):
        conn = http.client.HTTPConnection("127.0.0.1", port, timeout=2)
        try:
            conn.connect()
        except OSError:
            conn.close()
            if attempt == 7:
                raise
            continue
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()
    raise AssertionError("unreachable")


def get(port: int, path: str, headers: Optional[dict[str, str]] = None) -> tuple[int, dict[str, str], bytes]:
    return call(port, "GET", path, headers)


def jget(port: int, path: str) -> Json:
    status, _, body = get(port, path)
    assert status == 200, (path, status, body[:200])
    out: Json = json.loads(body)
    return out


class Env:
    def __init__(self, store: Store, port: int, srv: Any) -> None:
        self.store, self.port, self.srv = store, port, srv


def start_store(store: Store, **kw: Any) -> Env:
    srv = make_store_server(store, port=0, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return Env(store, srv.server_address[1], srv)


@pytest.fixture
def two(base_site: Path, tmp_path: Path) -> Iterator[Env]:
    """A store with a root site and ``pr/42``; the root has two releases, ``pr/42`` one."""
    store = Store.open(str(tmp_path / "store"), create=True)
    put(store, variant(base_site, tmp_path / "v1", 1, extra=True), "")
    put(store, variant(base_site, tmp_path / "v2", 2), "")
    put(store, variant(base_site, tmp_path / "v3", 3), "pr/42")
    env = start_store(store)
    yield env
    env.srv.shutdown()
    env.srv.server_close()


def index_of(port: int, prefix: str) -> Json:
    return jget(port, prefix + "data/index.json")


# --- routing --------------------------------------------------------------------------------------------


def test_two_sites_are_served_side_by_side(two: Env) -> None:
    root = index_of(two.port, "/")
    pr = index_of(two.port, "/pr/42/")
    assert root["modelHash"] == model_hash_of_variant(2)
    assert pr["modelHash"] == model_hash_of_variant(3)
    for prefix, idx in (("/", root), ("/pr/42/", pr)):
        status, hdr, body = get(two.port, prefix)
        assert status == 200 and b"viewer.js" in body and hdr["content-type"].startswith("text/html")
        model = jget(two.port, prefix + "data/" + idx["model"]["file"])
        assert model["modelHash"] == idx["modelHash"]
        scene_file = idx["scenes"]["landscape"]["file"]
        assert get(two.port, prefix + "data/" + scene_file)[0] == 200
        assert get(two.port, prefix + "build.json")[0] == 200
        assert get(two.port, prefix + "assets/viewer.js")[0] == 200


def test_a_site_path_that_only_shares_a_prefix_does_not_match(two: Env) -> None:
    # "/pr/420/" is not "pr/42": the root site gets it and has nothing there
    assert get(two.port, "/pr/420/")[0] == 404
    assert get(two.port, "/pr/420/data/index.json")[0] == 404
    assert get(two.port, "/pr/4/")[0] == 404
    assert get(two.port, "/pr/")[0] == 404


def test_a_site_path_without_the_slash_redirects_and_keeps_the_query(two: Env) -> None:
    status, hdr, _ = get(two.port, "/pr/42")
    assert (status, hdr["location"]) == (308, "/pr/42/")
    status, hdr, _ = get(two.port, "/pr/42?a=1&b=%20x")
    assert (status, hdr["location"]) == (308, "/pr/42/?a=1&b=%20x")
    status, hdr, _ = call(two.port, "HEAD", "/pr/42")
    assert (status, hdr["location"]) == (308, "/pr/42/")
    assert get(two.port, "/pr/42/")[0] == 200


def test_a_folder_inside_a_release_redirects_with_the_site_path(two: Env) -> None:
    status, hdr, _ = get(two.port, "/pr/42/data")
    assert (status, hdr["location"]) == (308, "/pr/42/data/")
    status, hdr, _ = get(two.port, "/assets")
    assert (status, hdr["location"]) == (308, "/assets/")
    assert get(two.port, "/pr/42/data/")[0] == 404  # no listings


def test_reserved_segments_never_hide_a_file_of_the_site_above(two: Env) -> None:
    # a request below a real site always goes to that site, whatever the next segment is called
    for seg in ("data", "assets", "api", "_buildzr", "build.json"):
        assert get(two.port, f"/pr/42/{seg}/nothing")[0] == 404
    assert get(two.port, "/pr/42/build.json")[0] == 200


@pytest.mark.parametrize("path", [
    "/pr/42/%2e%2e/%2e%2e/etc/passwd", "/%2e%2e/%2e%2e/etc/passwd", "/pr/42/%2E%2E%2fx", "/pr/42/..%2f..%2fx",
    "/pr/42/%252e%252e/x", "/%252e%252e/x", "/pr/42/%2e%2e", "/pr/42/%2e/data/index.json", "/./x", "/pr/42/./x",
    "/pr/42/a\\b", "/pr/42/a%5cb", "/pr%5c42/", "/pr/42/a%00b", "/pr/42/%00", "/pr//42/", "/pr/42//data/index.json",
    "/pr/42/%c3%28", "/pr/42/%0d%0aX", "/pr/42/data/..%5c..%5cbuildzr-store.json"])
def test_hostile_paths_are_404_and_never_read_outside(two: Env, path: str, monkeypatch: pytest.MonkeyPatch) -> None:
    opened: list[str] = []
    real_open = open

    def spy(file: Any, *a: Any, **kw: Any) -> Any:
        if isinstance(file, (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(file))
        return real_open(file, *a, **kw)
    monkeypatch.setattr("builtins.open", spy)
    status, _, body = get(two.port, path)
    monkeypatch.undo()
    assert status == 404, (path, status)
    store_dir = os.path.realpath(two.store.dir)
    for f in opened:
        assert not f.endswith("buildzr-store.json") and "/etc/passwd" not in f, f
    assert b"buildzr-store" not in body


def test_percent_decoding_happens_once() -> None:
    assert normalise_url_path("/a%2fb") == "/a/b"  # one decode...
    assert normalise_url_path("/%252e%252e/x") == "/%2e%2e/x"  # ...and the result is not decoded again
    assert normalise_url_path("/a/") == "/a/" and normalise_url_path("/") == "/"
    assert normalise_url_path("a") is None and normalise_url_path("/a//b") is None
    assert normalise_url_path("/a/%2e%2e/b") is None and normalise_url_path("/a/b%5c") is None
    assert normalise_url_path("/a%00") is None and normalise_url_path("/%ff") is None


def test_a_symlink_inside_a_release_cannot_leave_it(two: Env, tmp_path: Path) -> None:
    secret = tmp_path / "secret.txt"
    secret.write_text("SECRET")
    route = two.store.table.route("pr/42")
    assert route
    os.symlink(secret, os.path.join(route.current.dir, "link.txt"))
    assert get(two.port, "/pr/42/link.txt")[0] == 404


def test_the_encoded_form_of_a_nested_site_path_works(two: Env) -> None:
    assert get(two.port, "/pr%2f42/data/index.json")[0] == 200  # one decode: the same site


# --- previous release -----------------------------------------------------------------------------------


def test_a_hashed_file_only_the_previous_release_has_is_still_served(two: Env) -> None:
    # variant 1 (previous at the root) has data/scene/e/only-here.deadbeef.json; variant 2 (current) does not
    status, _, body = get(two.port, "/data/scene/e/only-here.deadbeef.json")
    assert (status, body) == (200, b'{"only":"here"}\n')
    route = two.store.table.route("")
    assert route and route.previous
    prev_model = json.loads((Path(route.previous.dir) / "data" / "index.json").read_text())["model"]["file"]
    cur_model = index_of(two.port, "/")["model"]["file"]
    assert prev_model != cur_model
    status, _, body = get(two.port, "/data/" + prev_model)
    assert status == 200 and json.loads(body)["modelHash"] == model_hash_of_variant(1)


def test_index_json_and_friends_never_come_from_the_previous_release(two: Env, tmp_path: Path, base_site: Path) -> None:
    route = two.store.table.route("")
    assert route and route.previous
    cur = Path(route.current.dir)
    # make the current release lack every non-hashed file; the previous release still has them
    for name in ("data/index.json", "index.html", "build.json"):
        (cur / name).unlink()
        assert (Path(route.previous.dir) / name).is_file()
        assert get(two.port, "/" + name)[0] == 404, name
    assert get(two.port, "/llms.txt")[0] in (404, 503)
    (cur / "data" / "index.json").write_text("{}")
    assert get(two.port, "/data/index.json")[1]["content-type"].startswith("application/json")
    assert get(two.port, "/data/index.json")[2] == b"{}"


def test_a_missing_hashed_file_that_neither_release_has_is_404(two: Env) -> None:
    assert get(two.port, "/data/scene/e/nothing.abcdef12.json")[0] == 404
    assert get(two.port, "/data/model.abcdef12.json")[0] == 404
    assert get(two.port, "/pr/42/data/model.abcdef12.json")[0] == 404  # pr/42 has no previous release


def test_the_fallback_stays_inside_the_same_site(two: Env) -> None:
    # only-here.deadbeef.json belongs to the root site's previous release, not to pr/42
    assert get(two.port, "/pr/42/data/scene/e/only-here.deadbeef.json")[0] == 404


def test_rollback_restores_the_previous_release_and_routing(two: Env) -> None:
    assert index_of(two.port, "/")["modelHash"] == model_hash_of_variant(2)
    two.store.rollback("")
    assert index_of(two.port, "/")["modelHash"] == model_hash_of_variant(1)
    assert jget(two.port, "/api/v1/")["modelHash"] == model_hash_of_variant(1)
    assert get(two.port, "/data/scene/e/only-here.deadbeef.json")[0] == 200  # now in the current release
    assert index_of(two.port, "/pr/42/")["modelHash"] == model_hash_of_variant(3)


# --- the API of each site -------------------------------------------------------------------------------


def test_each_site_has_its_own_api_and_viewer_urls(two: Env) -> None:
    root = jget(two.port, "/api/v1/")
    pr = jget(two.port, "/pr/42/api/v1/")
    assert root["modelHash"] == model_hash_of_variant(2) and pr["modelHash"] == model_hash_of_variant(3)
    assert root["name"] == "Small v2" and pr["name"] == "Small v3"
    assert root["viewerUrl"] == "/" and pr["viewerUrl"] == "/pr/42/"
    assert pr["endpoints"]["element"].startswith("/pr/42/api/v1/element")
    assert root["endpoints"]["element"].startswith("/api/v1/element")
    el = jget(two.port, "/pr/42/api/v1/element?id=billing")["element"]
    assert el["viewerUrl"].startswith("/pr/42/#/m/billing")
    assert jget(two.port, "/api/v1/element?id=billing")["element"]["viewerUrl"].startswith("/#/m/billing")
    elements = jget(two.port, "/pr/42/api/v1/elements?limit=50")
    assert elements["items"] and all(i["viewerUrl"] is None or i["viewerUrl"].startswith("/pr/42/#/") for i in elements["items"])
    if "next" in elements and elements["next"]:
        assert elements["next"].startswith("/pr/42/api/v1/")


def test_llms_txt_per_site_and_the_api_redirect(two: Env) -> None:
    status, hdr, body = get(two.port, "/pr/42/llms.txt")
    assert status == 200 and hdr["content-type"].startswith("text/plain")
    assert b"/pr/42/api/v1/" in body and b"Small v3" in body
    assert b"/pr/42/" not in get(two.port, "/llms.txt")[2]
    status, hdr, _ = get(two.port, "/pr/42/api/v1?x=1")
    assert (status, hdr["location"]) == (301, "/pr/42/api/v1/?x=1")
    status, hdr, body = get(two.port, "/pr/42/api/v1/nothing")
    assert status == 404 and hdr["content-type"].startswith("application/problem+json")
    etag = get(two.port, "/pr/42/api/v1/")[1]["etag"]
    assert etag == f'"{model_hash_of_variant(3)}"'
    assert get(two.port, "/pr/42/api/v1/", {"If-None-Match": etag})[0] == 304


def test_public_url_is_the_base_of_every_site(base_site: Path, tmp_path: Path) -> None:
    store = Store.open(str(tmp_path / "s"), create=True)
    put(store, variant(base_site, tmp_path / "a", 1), "")
    put(store, variant(base_site, tmp_path / "b", 2), "pr/42")
    env = start_store(store, public_url="https://models.example.com")
    try:
        assert jget(env.port, "/api/v1/")["viewerUrl"] == "https://models.example.com/"
        assert jget(env.port, "/pr/42/api/v1/")["viewerUrl"] == "https://models.example.com/pr/42/"
        el = jget(env.port, "/pr/42/api/v1/element?id=billing")["element"]
        assert el["viewerUrl"].startswith("https://models.example.com/pr/42/#/m/billing")
        sites = jget(env.port, "/_buildzr/v1/sites")["sites"]
        assert [s["viewerUrl"] for s in sites] == ["https://models.example.com/", "https://models.example.com/pr/42/"]
        assert sites[1]["apiUrl"] == "https://models.example.com/pr/42/api/v1/"
    finally:
        env.srv.shutdown()
        env.srv.server_close()


def test_a_broken_release_is_a_problem_not_a_traceback(two: Env) -> None:
    route = two.store.table.route("pr/42")
    assert route
    (Path(route.current.dir) / "data" / "index.json").write_text("{not json")
    status, hdr, body = get(two.port, "/pr/42/api/v1/")
    assert status == 503 and json.loads(body)["code"] == "model-unavailable"
    assert get(two.port, "/_buildzr/v1/sites")[0] == 200  # the list still answers, with null counts
    broken = [s for s in jget(two.port, "/_buildzr/v1/sites")["sites"] if s["sitePath"] == "pr/42"][0]
    assert broken["elements"] is None and broken["relationships"] is None


# --- the list of sites ----------------------------------------------------------------------------------


def test_sites_endpoint_shape_and_etag(two: Env) -> None:
    status, hdr, body = get(two.port, "/_buildzr/v1/sites")
    assert status == 200 and hdr["content-type"].startswith("application/json")
    doc = json.loads(body)
    assert doc["apiVersion"] == "1"
    root, pr = doc["sites"]
    assert root == {"sitePath": "", "currentRelease": "r-0002", "modelHash": model_hash_of_variant(2),
                    "previousModelHash": model_hash_of_variant(1), "elements": root["elements"],
                    "relationships": root["relationships"], "viewerUrl": "/", "apiUrl": "/api/v1/"}
    assert root["elements"] > 5 and root["relationships"] > 3
    assert pr["sitePath"] == "pr/42" and pr["previousModelHash"] is None and pr["apiUrl"] == "/pr/42/api/v1/"
    etag = hdr["etag"]
    assert get(two.port, "/_buildzr/v1/sites", {"If-None-Match": etag})[0] == 304
    assert "access-control-allow-origin" not in hdr
    two.store.rollback("")
    assert get(two.port, "/_buildzr/v1/sites")[1]["etag"] != etag  # the store state changed
    assert call(two.port, "HEAD", "/_buildzr/v1/sites")[0] == 200


def test_everything_else_under_buildzr_is_404(two: Env) -> None:
    for p in ("/_buildzr", "/_buildzr/", "/_buildzr/v1", "/_buildzr/v1/", "/_buildzr/v2/sites", "/_buildzr/v1/sites/x",
              "/_buildzr/deploy", "/pr/42/_buildzr/v1/sites"):
        status, hdr, _ = get(two.port, p)
        assert status == 404, p
    status, hdr, _ = get(two.port, "/_buildzr/v1/nothing")
    assert hdr["content-type"].startswith("application/problem+json")


def test_cors_is_off_unless_configured(base_site: Path, tmp_path: Path) -> None:
    store = Store.open(str(tmp_path / "s"), create=True)
    put(store, variant(base_site, tmp_path / "a", 1), "")
    env = start_store(store, cors_origins=["http://ok.example"])
    try:
        assert get(env.port, "/_buildzr/v1/sites", {"Origin": "http://ok.example"})[1]["access-control-allow-origin"] == "http://ok.example"
        assert "access-control-allow-origin" not in get(env.port, "/_buildzr/v1/sites", {"Origin": "http://evil.example"})[1]
        assert get(env.port, "/api/v1/", {"Origin": "http://ok.example"})[1]["access-control-allow-origin"] == "http://ok.example"
    finally:
        env.srv.shutdown()
        env.srv.server_close()


def test_a_store_without_a_root_site_lists_its_sites_at_the_root(base_site: Path, tmp_path: Path) -> None:
    store = Store.open(str(tmp_path / "s"), create=True)
    env = start_store(store)
    try:
        status, hdr, body = get(env.port, "/")
        assert status == 200 and hdr["content-type"].startswith("text/html") and b"no sites yet" in body
        put(store, variant(base_site, tmp_path / "a", 1), "pr/42")
        put(store, variant(base_site, tmp_path / "b", 2), "x.y")
        body = get(env.port, "/")[2]
        assert b'href="/pr/42/"' in body and b'href="/x.y/"' in body
        assert get(env.port, "/index.html")[0] == 404 and get(env.port, "/nothing")[0] == 404
        status, hdr, _ = get(env.port, "/api/v1/")
        assert status == 404 and hdr["content-type"].startswith("application/problem+json")
        assert get(env.port, "/nothing/api/v1/element?id=x")[1]["content-type"].startswith("application/problem+json")
        assert get(env.port, "/nothing/")[1]["content-type"].startswith("text/html")  # the plain 404 page
    finally:
        env.srv.shutdown()
        env.srv.server_close()


def test_the_root_listing_escapes_site_paths(base_site: Path, tmp_path: Path) -> None:
    # site paths are [a-z0-9._-] only, so nothing can inject markup; the page is still built with html.escape
    store = Store.open(str(tmp_path / "s"), create=True)
    put(store, variant(base_site, tmp_path / "a", 1), "a.b-c_d")
    env = start_store(store)
    try:
        body = get(env.port, "/")[2].decode()
        assert "<li><a href=\"/a.b-c_d/\">a.b-c_d</a></li>" in body and "<script" not in body
    finally:
        env.srv.shutdown()
        env.srv.server_close()


# --- read only ------------------------------------------------------------------------------------------


def snapshot(root: str) -> dict[str, tuple[int, str]]:
    import hashlib
    out = {}
    for p in tree(root):
        full = os.path.join(root, p)
        if os.path.isfile(full):
            with open(full, "rb") as f:
                out[p] = (os.path.getsize(full), hashlib.sha256(f.read()).hexdigest())
    return out


@pytest.mark.parametrize("method", ["POST", "PUT", "DELETE", "PATCH", "OPTIONS", "TRACE"])
def test_nothing_but_get_and_head_is_answered_and_nothing_is_written(two: Env, method: str) -> None:
    before = snapshot(two.store.dir)
    paths = ["/", "/pr/42/", "/pr/42", "/pr/42/data/index.json", "/pr/42/api/v1/", "/pr/42/api/v1/element?id=billing",
             "/api/v1/", "/_buildzr/v1/sites", "/_buildzr/v1/deploy", "/_buildzr/", "/nothing", "/pr/42/llms.txt",
             "/sites/x/", "/incoming/x"]
    for p in paths:
        status, hdr, body = call(two.port, method, p, body=b"{}" if method in ("POST", "PUT", "PATCH") else None,
                                 headers={"Content-Type": "application/json"})
        if method == "OPTIONS":
            assert status == 501, (p, status)
        else:
            assert status in (405, 501), (method, p, status)
            if "/api/v1" in p or p.startswith("/_buildzr"):
                assert status == 405 and hdr["content-type"].startswith("application/problem+json") and hdr["allow"] == "GET, HEAD"
    assert snapshot(two.store.dir) == before
    assert {n for n in dir(StoreHandler) if n.startswith("do_")} == {"do_GET", "do_HEAD"}


def test_the_store_files_are_not_served(two: Env) -> None:
    for p in ("/buildzr-store.json", "/deploys.log", "/sites/", f"/sites/{site_key('')}/r-0002/index.html",
              "/incoming/", "/pr/42/buildzr-store.json"):
        assert get(two.port, p)[0] == 404, p


# --- plain serve is unchanged ---------------------------------------------------------------------------


def test_plain_serve_is_unchanged(base_site: Path) -> None:
    srv = make_server(str(base_site), port=0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    port = srv.server_address[1]
    try:
        assert get(port, "/")[0] == 200
        assert get(port, "/_buildzr/v1/sites")[0] == 404  # no store routes on a single site
        assert jget(port, "/api/v1/")["viewerUrl"] == "/"
        assert get(port, "/data")[0] == 301  # the standard handler's redirect, as before
        assert call(port, "POST", "/")[0] == 501
        assert get(port, "/pr/42/")[0] == 404
    finally:
        srv.shutdown()
        srv.server_close()


# --- the command line -----------------------------------------------------------------------------------


def test_cli_store_option(tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch) -> None:
    called: list[tuple[Any, ...]] = []
    monkeypatch.setattr(cli, "serve_store", lambda *a: called.append(a))
    assert cli.main(["serve", "--store", str(tmp_path)]) == 1
    assert "not a buildzr store" in capsys.readouterr().err and called == []
    Store.open(str(tmp_path / "s"), create=True)
    assert cli.main(["serve", "--store", str(tmp_path / "s"), "-p", "0", "--public-url", "https://x.example/",
                     "--cors-origin", "http://o.example"]) == 0
    assert called == [(str(tmp_path / "s"), "127.0.0.1", 0, "https://x.example", ["http://o.example"])]
    assert cli.main(["serve", "--store", str(tmp_path / "s"), str(tmp_path)]) == 2
    assert "cannot be used together" in capsys.readouterr().err
    bad = tmp_path / "s" / "buildzr-store.json"
    bad.write_text("{")
    assert cli.main(["serve", "--store", str(tmp_path / "s")]) == 1
    assert "not valid JSON" in capsys.readouterr().err


# --- concurrency ----------------------------------------------------------------------------------------


@pytest.mark.parametrize("grace", [5.0, 0.0])
def test_readers_never_see_an_error_or_a_mixed_release_while_sites_are_installed(
        base_site: Path, tmp_path: Path, grace: float) -> None:
    """8 readers, 3200 GETs, 20 installs and 5 rollbacks. A reader fetches index.json, the model file it names and a
    scene it lists. Every answer is 200 and from one release, or falls back to the previous release. The only miss
    allowed is a file of a release that two newer installs have pushed out (older than the previous one)."""
    store = Store.open(str(tmp_path / "store"), create=True, grace=grace)
    variants = [variant(base_site, tmp_path / f"v{n}", n) for n in range(1, 7)]
    known = {model_hash_of_variant(n) for n in range(1, 7)}
    put(store, variants[0], "")
    put(store, variants[1], "")
    put(store, variants[2], "pr/42")  # a quiet neighbour
    env = start_store(store)
    problems: list[str] = []
    counts = {"requests": 0, "sequences": 0, "misses": 0, "started": 0, "done": 0}
    lock = threading.Lock()

    def miss(what: str, done_before: int) -> None:
        """A 404 is fine only when at least two installs started since this reader's index.json."""
        with lock:
            if counts["started"] - done_before >= 2:
                counts["misses"] += 1
            else:
                problems.append(f"{what} missing though fewer than two installs happened ({counts['started'] - done_before})")

    def reader(n_sequences: int) -> None:
        for _ in range(n_sequences):
            try:
                seen = 0
                with lock:
                    done_before = counts["done"]
                s, _, body = get(env.port, "/data/index.json")
                seen += 1
                if s != 200:
                    miss(f"index.json ({s})", done_before)
                    continue
                idx = json.loads(body)
                mfile = idx["model"]["file"]
                s, _, body = get(env.port, "/data/" + mfile)
                seen += 1
                if s != 200:
                    miss(mfile, done_before)
                elif json.loads(body)["modelHash"] != idx["modelHash"]:
                    problems.append(f"model {mfile} has another modelHash than its index")
                scene = idx["scenes"]["landscape"]["file"]
                s, _, body = get(env.port, "/data/" + scene)
                seen += 1
                if s != 200:
                    miss(scene, done_before)
                elif json.loads(body)["variant"] != [n for n in range(1, 7) if model_hash_of_variant(n) == idx["modelHash"]][0]:
                    problems.append(f"scene {scene} belongs to another release than its index")
                s, hdr, body = get(env.port, "/api/v1/")
                seen += 1
                if s != 200:
                    problems.append(f"api {s}: {body[:100]!r}")
                else:
                    api = json.loads(body)
                    if api["modelHash"] not in known or hdr["etag"] != f'"{api["modelHash"]}"':
                        problems.append(f"api hash {api['modelHash']} etag {hdr['etag']}")
                    elif api["name"] != "Small v" + str([n for n in range(1, 7) if model_hash_of_variant(n) == api["modelHash"]][0]):
                        problems.append("api name does not belong to its modelHash")
                s, _, body = get(env.port, "/pr/42/data/index.json")
                seen += 1
                if s != 200 or json.loads(body)["modelHash"] != model_hash_of_variant(3):
                    problems.append(f"neighbour site disturbed: {s}")
                with lock:
                    counts["requests"] += seen
                    counts["sequences"] += 1
            except Exception as e:  # a refused or reset connection is an error too
                problems.append(f"{type(e).__name__}: {e}")

    threads = [threading.Thread(target=reader, args=(80,)) for _ in range(8)]  # 8 x 80 x 5 = 3200 GETs
    for t in threads:
        t.start()
    installs = rollbacks = 0
    try:
        for i in range(20):
            with lock:
                counts["started"] += 1
            put(store, variants[i % 6], "")
            with lock:
                counts["done"] += 1
            installs += 1
            if i % 4 == 3:
                store.rollback("")
                rollbacks += 1
    finally:
        for t in threads:
            t.join(120)
        env.srv.shutdown()
        env.srv.server_close()
    assert not any(t.is_alive() for t in threads)
    assert problems == [], problems[:10]
    assert counts["requests"] >= 2000 and installs == 20 and rollbacks == 5
    # a miss is allowed only for a release older than the previous one; the readers are fast, so there are few
    assert counts["misses"] <= counts["sequences"] // 4
    print(f"concurrency (grace {grace}): {counts['requests']} GETs in {counts['sequences']} sequences, {installs} installs, "
          f"{rollbacks} rollbacks, {counts['misses']} allowed misses, {len(problems)} problems")
    saved = json.loads((Path(store.dir) / "buildzr-store.json").read_text())
    assert saved["sites"][""]["last"] == 22
    if grace == 0:
        assert len(os.listdir(Path(store.dir) / "sites" / site_key(""))) == 2
