"""The read-only Model API of ``buildzr serve`` (``<site>/api/v1/``): answers, limits, HTTP behaviour, safety."""

from __future__ import annotations

import builtins
import hashlib
import http.client
import json
import os
import shutil
import threading
from pathlib import Path
from typing import Any, Iterator, Optional
from urllib.parse import quote, urlsplit

import pytest

import buildzr.site.cli as cli
from buildzr.site.build import build_workspace
from buildzr.site.api import Api, ApiError, Query, Source, normalise_origin, normalise_public_url
from buildzr.site.model import rollup
from buildzr.site.serve import make_workspace_server
from tests.site.test_cli import ROOT, WS_TEXT, build, make_static, needs_node

HAS_NODE = bool(shutil.which("node") or os.environ.get("BUILDZR_NODE"))
SMALL_DIR = os.path.join(ROOT, "tests", "site", "fixtures", "small")
EXAMPLE_PY = os.path.join(ROOT, "examples", "buildzr_models_example.py")

Json = dict[str, Any]


# --- sites and servers ----------------------------------------------------------------------------------


def _load(path: str) -> Json:
    with open(path, encoding="utf-8") as f:
        data: Json = json.load(f)
    return data


@pytest.fixture(scope="module")
def small_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The small workspace, built with the stub layout (it copies the hand-made scenes of the small fixture)."""
    tmp = tmp_path_factory.mktemp("small")
    ws = tmp / "workspace.py"
    ws.write_text(WS_TEXT)
    build(str(ws), tmp / "site", make_static(tmp / "static"))
    return tmp / "site"


@pytest.fixture(scope="module")
def example_site(tmp_path_factory: pytest.TempPathFactory) -> Path:
    """The buildzr models example. Real layout when Node is there (scenes match the model), else the stub."""
    tmp = tmp_path_factory.mktemp("example")
    static = make_static(tmp / "static")
    if shutil.which("node") or os.environ.get("BUILDZR_NODE"):
        build_workspace(EXAMPLE_PY, str(tmp / "site"), static_dir=str(static))
    else:
        build(EXAMPLE_PY, tmp / "site", static)  # the stub layout: scenes are not the example's
    return tmp / "site"


def start(site: Path, **kw: Any) -> tuple[Any, int]:
    srv = make_workspace_server(str(site), port=0, **kw)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


class Client:
    def __init__(self, port: int) -> None:
        self.port = port

    def call(self, method: str, path: str, headers: Optional[dict[str, str]] = None, body: Optional[bytes] = None
             ) -> tuple[int, dict[str, str], bytes]:
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        try:
            conn.request(method, path, body=body, headers=headers or {})
            r = conn.getresponse()
            return r.status, {k.lower(): v for k, v in r.getheaders()}, r.read()
        finally:
            conn.close()

    def get(self, path: str, headers: Optional[dict[str, str]] = None) -> tuple[int, dict[str, str], Json]:
        st, h, b = self.call("GET", path, headers)
        return st, h, (json.loads(b) if b else {})

    def ok(self, path: str) -> Json:
        st, _h, body = self.get(path)
        assert st == 200, (path, st, body)
        return body


@pytest.fixture(scope="module")
def small(small_site: Path) -> Iterator[Client]:
    srv, port = start(small_site)
    yield Client(port)
    srv.shutdown()
    srv.server_close()


@pytest.fixture(scope="module")
def example(example_site: Path) -> Iterator[Client]:
    srv, port = start(example_site)
    yield Client(port)
    srv.shutdown()
    srv.server_close()


def ids(items: list[Json], key: str = "id") -> list[str]:
    return [i[key] for i in items]


def model_of(site: Path) -> Json:
    return _load(str(site / "data" / _load(str(site / "data" / "index.json"))["model"]["file"]))


# --- the orientation document ---------------------------------------------------------------------------


def test_orientation_document(small: Client, small_site: Path) -> None:
    m = model_of(small_site)
    doc = small.ok("/api/v1/")
    assert doc["apiVersion"] == "1" and doc["modelHash"] == m["modelHash"]
    assert doc["name"] == "Small fixture"
    assert doc["counts"]["elements"] == 11 and doc["counts"]["relationships"] == 11 and doc["counts"]["views"] == 2
    assert doc["counts"]["byType"] == {"Component": 3, "Container": 3, "Person": 2, "SoftwareSystem": 3}
    assert doc["topLevel"] == ["customer", "support-agent", "billing", "crm", "email"]
    assert "PCI" in doc["tags"] and doc["tags"] == sorted(doc["tags"])
    assert doc["viewerUrl"] == "/" and doc["publicUrlConfigured"] is False
    assert set(doc["endpoints"]) == {"element", "search", "tree", "neighbours", "path", "relationships", "views", "view"}
    assert doc["endpoints"]["element"] == "/api/v1/element?id={id}"
    assert doc["limits"]["maxDepth"] == 4 and doc["limits"]["maxHops"] == 8 and doc["limits"]["elements"]["max"] == 200
    assert doc["builtWith"]["k"] == 4 and doc["notes"] == []
    assert small.get("/api/v1/?x=1")[0] == 400


# --- the 15 questions of table 7.2 ----------------------------------------------------------------------


def test_q01_top_level(small: Client) -> None:
    doc = small.ok("/api/v1/")
    tree = small.ok("/api/v1/tree")
    assert ids(tree["items"]) == doc["topLevel"] and tree["truncated"] is False
    assert all(n["children"] is None or n["children"] == [] for n in tree["items"])  # depth 1 shows no children
    assert {n["id"]: n["childCount"] for n in tree["items"]}["billing"] == 3


def test_q02_what_is_the_system_made_of(small: Client) -> None:
    t = small.ok("/api/v1/tree?id=billing&depth=2")
    (billing,) = t["items"]
    assert billing["id"] == "billing" and ids(billing["children"]) == ["billing/web", "billing/api", "billing/db"]
    api = billing["children"][1]
    assert ids(api["children"]) == ["billing/api/invoicer", "billing/api/payments", "billing/api/ledger-repo"]
    assert all(c["children"] in (None, []) for c in api["children"])
    d1 = small.ok("/api/v1/tree?id=billing")["items"][0]
    assert ids(d1["children"]) == ["billing/web", "billing/api", "billing/db"] and d1["children"][1]["children"] is None


def test_tree_cut_by_limit_never_shows_a_node_with_children_as_a_leaf(small: Client) -> None:
    for limit in range(1, 12):
        t = small.ok(f"/api/v1/tree?depth=4&limit={limit}")
        count = [0]

        def walk(n: Json) -> None:
            count[0] += 1
            if n["children"] == []:
                assert n["childCount"] == 0, (limit, n["id"])
            elif n["children"] is not None:
                assert len(n["children"]) <= n["childCount"]
                for c in n["children"]:
                    walk(c)
        for n in t["items"]:
            walk(n)
        assert count[0] == min(limit, 11) and t["truncated"] is (limit < 11), limit


def test_q03_depends_on_directly_and_through_others(small: Client) -> None:
    n = small.ok("/api/v1/neighbours?id=billing/web&direction=out&depth=3")
    by_hop: dict[int, set[str]] = {}
    for i in n["items"]:
        by_hop.setdefault(i["hop"], set()).add(i["element"]["id"])
    assert by_hop[1] == {"billing/api", "billing/api/payments"}
    assert by_hop[2] == {"crm", "email", "billing/db"}  # through the API container and its components (rollup)
    assert by_hop[3] == {"billing/api"}  # crm -> billing/api closes a loop; shown, not expanded again
    assert n["truncated"] is False and all(i["direction"] == "out" for i in n["items"])
    one = small.ok("/api/v1/neighbours?id=billing/web&direction=out")
    assert {i["element"]["id"] for i in one["items"]} == by_hop[1] and {i["hop"] for i in one["items"]} == {1}


def test_q04_who_talks_to_the_database(small: Client) -> None:
    n = small.ok("/api/v1/neighbours?id=billing/db&direction=in")
    assert sorted(ids(n["items"], "near")) == ["billing/db", "billing/db"]
    assert sorted(i["element"]["id"] for i in n["items"]) == ["billing/api/ledger-repo", "billing/api/payments"]


def test_q05_shortest_chain(small: Client) -> None:
    p = small.ok("/api/v1/path?from=billing/api/invoicer&to=billing/db")
    assert p["hops"] == 2 and len(p["chains"]) == 1 and p["truncated"] is False
    assert [(s["from"], s["to"]) for s in p["chains"][0]] == [("billing/api/invoicer", "billing/api/payments"),
                                                              ("billing/api/payments", "billing/db")]
    assert [s["rel"] for s in p["chains"][0]] == ["billing/api/invoicer->billing/api/payments",
                                                  "billing/api/payments->billing/db"]


def test_q06_relationships_behind_an_arrow(small: Client) -> None:
    r = small.ok("/api/v1/relationships?from=billing&to=crm")
    assert ids(r["items"]) == ["billing/api/invoicer->crm"] and r["truncated"] is False and r["next"] is None
    assert ids(small.ok("/api/v1/relationships?from=crm&to=billing")["items"]) == ["crm->billing/api"]


def test_q07_tagged(small: Client) -> None:
    r = small.ok("/api/v1/elements?tag=PCI")
    assert ids(r["items"]) == ["billing/api/payments"] and r["total"] == 1
    assert ids(small.ok("/api/v1/elements?tag=pci&tag=Component")["items"]) == ["billing/api/payments"]  # all tags must match
    assert small.ok("/api/v1/elements?tag=PCI&tag=Database")["items"] == []


def test_q08_where_is_it_shown(small: Client) -> None:
    e = small.ok("/api/v1/element?id=billing/web")["element"]
    assert e["views"] == ["billing-containers"]
    assert small.ok("/api/v1/element?id=customer")["element"]["views"] == ["landscape", "billing-containers"]


def test_q09_link_for_a_person(small: Client) -> None:
    g = lambda i: small.ok(f"/api/v1/element?id={i}")["element"]["viewerUrl"]  # noqa: E731
    assert g("billing/api") == "/#/m/billing/api?sel=billing/api"  # has children: opens expanded
    assert g("billing/web") == "/#/m/billing?sel=billing/web"  # a leaf opens at its parent
    assert g("customer") == "/#/m?sel=customer"  # a top-level leaf
    assert g("billing") == "/#/m/billing?sel=billing"
    assert g("billing/api/payments") == "/#/m/billing/api?sel=billing/api/payments"


def test_q10_changed_since(small: Client) -> None:
    st, h, body = small.get("/api/v1/")
    etag = h["etag"]
    assert etag == f'"{body["modelHash"]}"'
    st, h, raw = small.call("GET", "/api/v1/", {"If-None-Match": etag})
    assert (st, raw) == (304, b"") and h["etag"] == etag and h["cache-control"] == "no-cache"
    st, _h, raw = small.call("GET", "/api/v1/", {"If-None-Match": '"sha256:old"'})
    assert st == 200 and raw


def test_q11_who_uses_it(small: Client) -> None:
    n = small.ok("/api/v1/neighbours?id=billing&direction=in&type=Person")
    assert {i["element"]["id"] for i in n["items"]} == {"customer"}
    assert sorted(i["relationship"]["id"] for i in n["items"]) == ["customer->billing/web:pays", "customer->billing/web:uses"]
    assert {i["element"]["type"] for i in n["items"]} == {"Person"}


def test_q12_what_uses_postgres(small: Client) -> None:
    r = small.ok("/api/v1/elements?q=postgres")
    assert ids(r["items"]) == ["billing/db"] and r["items"][0]["matched"] == "technology"
    assert small.ok("/api/v1/elements?q=POSTGRES")["items"] == r["items"]  # case-insensitive


def test_q13_what_it_does_and_who_owns_it(small: Client) -> None:
    e = small.ok("/api/v1/element?id=billing")["element"]
    assert e["description"] == "Invoices customers and takes payments." and e["properties"] == {"owner": "payments-team"}
    w = small.ok("/api/v1/element?id=billing/web")["element"]
    assert w["technology"] == "TypeScript, React" and w["name"] == "Web" and w["type"] == "Container"
    assert w["parent"] == "billing" and w["children"] == [] and w["childCount"] == 0
    assert w["relationships"] == {"own": {"in": 2, "out": 2}, "withDescendants": {"in": 2, "out": 2}}
    b = small.ok("/api/v1/element?id=billing")["element"]
    assert b["relationships"]["withDescendants"] == {"in": 3, "out": 2}  # crossing the boundary
    assert b["relationships"]["own"] == {"in": 0, "out": 0}


def test_q14_views(small: Client, small_site: Path) -> None:
    vs = small.ok("/api/v1/views")["items"]
    assert ids(vs, "key") == ["landscape", "billing-containers"]
    assert vs[1]["scope"] == "billing" and vs[1]["viewerUrl"] == "/#/v/billing-containers"
    assert ids(small.ok("/api/v1/views?scope=billing")["items"], "key") == ["billing-containers"]
    v = small.ok("/api/v1/view?key=billing-containers")["view"]
    scene = _load(str(small_site / "data" / _load(str(small_site / "data" / "index.json"))["scenes"]["v/billing-containers"]["file"]))
    assert v["relationships"] == sorted({r for e in scene["edges"] for r in e["rels"]}) and v["relationships"]
    assert ids(v["elements"]) == ["customer", "billing", "billing/web", "billing/api", "billing/db", "crm"]


def test_q15_what_is_this_arrow(small: Client, small_site: Path) -> None:
    index = _load(str(small_site / "data" / "index.json"))
    checked = 0
    for key, entry in index["scenes"].items():
        if key.startswith("v/"):
            continue  # a view draws a chosen subset of the rollup
        scene = _load(str(small_site / "data" / entry["file"]))
        for edge in scene["edges"]:
            r = small.ok(f"/api/v1/relationships?edge={quote(edge['id'], safe='')}")
            assert ids(r["items"]) == edge["rels"], edge["id"]
            checked += 1
    assert checked >= 8 and any("port:" in e["id"] for k, en in index["scenes"].items() if not k.startswith("v/")
                                for e in _load(str(small_site / "data" / en["file"]))["edges"])
    one = small.ok(f"/api/v1/relationships?edge={quote('customer->billing/web:pays', safe='')}")
    assert ids(one["items"]) == ["customer->billing/web:pays"]  # an explicit relationship id works too
    assert small.get("/api/v1/relationships?edge=nonsense")[0] == 400
    assert small.get("/api/v1/relationships?edge=a-%3Eb")[0] == 404


# --- the same questions on the buildzr models example ---------------------------------------------------


def test_example_site_answers(example: Client, example_site: Path) -> None:
    m = model_of(example_site)
    doc = example.ok("/api/v1/")
    assert doc["counts"]["elements"] == 13 and doc["counts"]["relationships"] == 6 and doc["counts"]["views"] == 1
    assert doc["topLevel"] == ["customer", "administrator", "e-commerce-system", "payment-provider"]
    assert doc["modelHash"] == m["modelHash"]
    # q2/q3: what is the system made of; what does the web app depend on through others
    t = example.ok("/api/v1/tree?id=e-commerce-system&depth=2")["items"][0]
    assert ids(t["children"]) == ["e-commerce-system/web-app", "e-commerce-system/api-gateway",
                                  "e-commerce-system/order-service", "e-commerce-system/inventory-service",
                                  "e-commerce-system/database"]
    n = example.ok("/api/v1/neighbours?id=e-commerce-system/web-app&direction=out&depth=3")
    assert [(i["hop"], i["element"]["id"]) for i in n["items"]] == [
        (1, "e-commerce-system/api-gateway"), (2, "e-commerce-system/inventory-service")]
    # q4/q11: who talks to the database; who are the people using the system (rolled up from the web app)
    d = example.ok("/api/v1/neighbours?id=e-commerce-system/database&direction=in")
    assert ids(d["items"], "near") == ["e-commerce-system/database"]
    assert [i["element"]["id"] for i in d["items"]] == ["e-commerce-system/order-service"]
    p = example.ok("/api/v1/neighbours?id=e-commerce-system&direction=in&type=Person")
    assert {i["element"]["id"] for i in p["items"]} == {"customer", "administrator"}
    # q5: the chain from the customer to the payment provider
    c = example.ok("/api/v1/path?from=customer&to=payment-provider&maxHops=8")
    assert c["hops"] is None and c["chains"] == []  # the web app reaches the gateway, which only reaches inventory
    ch = example.ok("/api/v1/path?from=customer&to=e-commerce-system/database")
    assert ch["chains"] == [] and ch["hops"] is None  # no explicit chain reaches the database from the customer
    w = example.ok("/api/v1/path?from=e-commerce-system/web-app&to=e-commerce-system/inventory-service")
    assert w["hops"] == 2 and [s["to"] for s in w["chains"][0]] == ["e-commerce-system/api-gateway",
                                                                    "e-commerce-system/inventory-service"]
    # q6: the arrow between the people and the system; q9 links
    r = example.ok("/api/v1/relationships?from=administrator&to=e-commerce-system")
    assert ids(r["items"]) == ["administrator->e-commerce-system/web-app"]
    e = example.ok("/api/v1/element?id=e-commerce-system/web-app")["element"]
    assert e["viewerUrl"] == "/#/m/e-commerce-system?sel=e-commerce-system/web-app" and e["technology"] == "React"
    assert example.ok("/api/v1/element?id=e-commerce-system/order-service")["element"]["viewerUrl"] == \
        "/#/m/e-commerce-system/order-service?sel=e-commerce-system/order-service"
    # q7/q12/q14
    assert ids(example.ok("/api/v1/elements?q=mongo")["items"]) == ["e-commerce-system/database"]
    assert example.ok("/api/v1/elements?tag=NoSuchTag")["items"] == []
    v = example.ok("/api/v1/view?key=system-context-view-ecommerce")["view"]
    assert v["scope"] == "e-commerce-system" and "customer" in ids(v["elements"])
    if HAS_NODE:  # the scene only matches the model with the real layout
        assert v["relationships"] == ["administrator->e-commerce-system/web-app", "customer->e-commerce-system/web-app",
                                      "e-commerce-system/order-service->payment-provider"]


@needs_node
def test_every_scene_edge_of_the_example_is_explained(example: Client, example_site: Path) -> None:
    index = _load(str(example_site / "data" / "index.json"))
    n = 0
    for key, entry in index["scenes"].items():
        if key.startswith("v/"):
            continue
        for edge in _load(str(example_site / "data" / entry["file"]))["edges"]:
            assert ids(example.ok(f"/api/v1/relationships?edge={quote(edge['id'], safe='')}")["items"]) == edge["rels"]
            n += 1
    assert n >= 5


# --- rollup semantics: exactly the viewer's ------------------------------------------------------------


@pytest.mark.parametrize("which", ["small", "example"])
def test_relationships_between_any_two_elements_match_model_rollup(which: str, small_site: Path, example_site: Path) -> None:
    model = model_of(small_site if which == "small" else example_site)
    api = Api(model)
    paths = [e["id"] for e in model["elements"]]
    nonempty = 0
    for a in paths:
        for b in paths:
            got = ids(api.answer("relationships", f"from={a}&to={b}&limit=200")["items"])
            assert got == rollup(model, a, b), (a, b)
            nonempty += bool(got)
    assert nonempty > 10


@pytest.mark.parametrize("which", ["small", "example"])
def test_neighbours_and_one_sided_relationships_follow_the_rollup(which: str, small_site: Path, example_site: Path) -> None:
    model = model_of(small_site if which == "small" else example_site)
    api = Api(model)

    def inside(x: str, root: str) -> bool:
        return x == root or x.startswith(root + "/")
    for e in model["elements"]:
        p = e["id"]
        want_out = [r["id"] for r in model["relationships"] if inside(r["source"], p)]
        want_in = [r["id"] for r in model["relationships"] if inside(r["destination"], p)]
        assert ids(api.answer("relationships", f"from={p}&limit=200")["items"]) == want_out
        assert ids(api.answer("relationships", f"to={p}&limit=200")["items"]) == want_in
        n_out = api.answer("neighbours", f"id={p}&direction=out&limit=1000")
        assert sorted(i["relationship"]["id"] for i in n_out["items"]) == \
            sorted(r["id"] for r in model["relationships"] if inside(r["source"], p) and not inside(r["destination"], p))
        n_in = api.answer("neighbours", f"id={p}&direction=in&limit=1000")
        assert sorted(i["relationship"]["id"] for i in n_in["items"]) == \
            sorted(r["id"] for r in model["relationships"] if inside(r["destination"], p) and not inside(r["source"], p))
        both = api.answer("neighbours", f"id={p}&limit=1000")
        assert len(both["items"]) == len(n_out["items"]) + len(n_in["items"])


# --- paths: shortest chains and maxHops ------------------------------------------------------------------


def test_path_all_shortest_chains_and_limits(small: Client) -> None:
    p = small.ok("/api/v1/path?from=customer&to=billing/db")
    assert p["hops"] == 3 and len(p["chains"]) == 2 and p["truncated"] is False
    assert sorted(c[0]["rel"] for c in p["chains"]) == ["customer->billing/web:pays", "customer->billing/web:uses"]
    for c in p["chains"]:
        assert [s["to"] for s in c] == ["billing/web", "billing/api/payments", "billing/db"]
        assert all(a["to"] == b["from"] for a, b in zip(c, c[1:]))
    one = small.ok("/api/v1/path?from=customer&to=billing/db&limit=1")
    assert len(one["chains"]) == 1 and one["truncated"] is True
    short = small.ok("/api/v1/path?from=customer&to=billing/db&maxHops=2")
    assert short["hops"] is None and short["chains"] == [] and short["truncated"] is False
    assert small.ok("/api/v1/path?from=customer&to=billing/db&maxHops=3")["hops"] == 3
    # from/to include descendants: the whole billing system reaches crm in one hop
    sys_ = small.ok("/api/v1/path?from=billing&to=crm")
    assert sys_["hops"] == 1 and sys_["chains"][0][0]["rel"] == "billing/api/invoicer->crm"
    assert small.ok("/api/v1/path?from=email&to=customer")["chains"] == []  # direction matters


def test_path_is_shortest_on_a_branching_graph() -> None:
    def el(i: str) -> Json:
        return {"id": i, "modelId": i, "type": "SoftwareSystem", "parent": None, "children": [], "name": i,
                "description": None, "technology": None, "tags": [], "properties": {}, "url": None, "group": None, "views": []}

    def rel(a: str, b: str) -> Json:
        return {"id": f"{a}->{b}", "modelId": f"{a}{b}", "source": a, "destination": b, "description": None,
                "technology": None, "tags": [], "properties": {}}
    pairs = [("a", "b"), ("b", "e"), ("a", "c"), ("c", "d"), ("d", "e"), ("a", "e2"), ("e2", "e")]
    model = {"schema": "buildzr.model/2", "modelHash": "sha256:" + "0" * 64, "workspace": {"name": "g", "description": None},
             "elements": [el(i) for i in ["a", "b", "c", "d", "e", "e2"]],
             "relationships": sorted((rel(*p) for p in pairs), key=lambda r: r["id"]), "views": [], "deployment": {"environments": []}}
    api = Api(model)
    p = api.answer("path", "from=a&to=e&limit=5")
    assert p["hops"] == 2 and sorted("/".join(s["to"] for s in c) for c in p["chains"]) == ["b/e", "e2/e"]
    assert api.answer("path", "from=a&to=d")["hops"] == 2


# --- paging, limits, errors ----------------------------------------------------------------------------


def test_paging_covers_everything_once_and_in_order(example: Client) -> None:
    everything = example.ok("/api/v1/elements?limit=200")
    assert everything["total"] == 13 and everything["truncated"] is False and everything["next"] is None
    seen: list[str] = []
    url: Optional[str] = "/api/v1/elements?limit=4"
    pages = 0
    while url:
        page = example.ok(url)
        assert len(page["items"]) <= 4 and page["total"] == 13
        seen += ids(page["items"])
        assert page["truncated"] is (page["next"] is not None)
        url = page["next"]
        pages += 1
    assert pages == 4 and seen == ids(everything["items"])
    rel_pages: list[str] = []
    url = "/api/v1/relationships?limit=4"
    while url:
        page = example.ok(url)
        rel_pages += ids(page["items"])
        url = page["next"]
    assert rel_pages == sorted(rel_pages) and len(rel_pages) == 6


def test_cursor_is_bound_to_the_model_and_opaque(example: Client, small: Client) -> None:
    nxt = example.ok("/api/v1/elements?limit=2")["next"]
    cursor = nxt.split("cursor=")[1]
    st, _h, body = small.get(f"/api/v1/elements?limit=2&cursor={cursor}")  # from another model
    assert st == 409 and body["code"] == "cursor-stale" and body["status"] == 409
    st, _h, body = example.get("/api/v1/elements?cursor=not-a-cursor")
    assert st == 400 and body["code"] == "bad-parameter"


def test_ranking_of_search_results(example: Client) -> None:
    r = example.ok("/api/v1/elements?q=order")["items"]
    assert ids(r)[:3] == ["e-commerce-system/order-service", "e-commerce-system/order-service/order-controller",
                          "e-commerce-system/order-service/order-repository"]
    assert [i["matched"] for i in r][:3] == ["name"] * 3
    assert ids(example.ok("/api/v1/elements?q=customer&type=Person")["items"]) == ["customer"]
    inside = example.ok("/api/v1/elements?within=e-commerce-system/order-service")["items"]
    assert ids(inside) == ["e-commerce-system/order-service/order-controller", "e-commerce-system/order-service/order-repository"]
    r2 = example.ok("/api/v1/elements?q=a")  # name-start before name-contains before the other fields
    rank = {"name": 0, "description": 1, "technology": 2, "tags": 3, "properties": 4}
    starts = [i["name"].lower().startswith("a") for i in r2["items"] if i["matched"] == "name"]
    assert starts == sorted(starts, reverse=True) and starts[0] is True  # name-start before name-contains
    assert [rank[i["matched"]] for i in r2["items"]] == sorted(rank[i["matched"]] for i in r2["items"])


@pytest.mark.parametrize("query,param,code", [
    ("elements?limit=201", "limit", "limit-exceeded"), ("elements?limit=0", "limit", "limit-exceeded"),
    ("tree?depth=5", "depth", "limit-exceeded"), ("tree?depth=0", "depth", "limit-exceeded"),
    ("tree?limit=1001", "limit", "limit-exceeded"), ("neighbours?id=customer&depth=5", "depth", "limit-exceeded"),
    ("neighbours?id=customer&limit=1001", "limit", "limit-exceeded"),
    ("path?from=customer&to=crm&maxHops=9", "maxHops", "limit-exceeded"),
    ("path?from=customer&to=crm&limit=6", "limit", "limit-exceeded"),
    ("relationships?limit=201", "limit", "limit-exceeded"),
    ("elements?limit=ten", "limit", "bad-parameter"), ("tree?depth=1.5", "depth", "bad-parameter"),
    ("elements?q=" + "x" * 201, "q", "bad-parameter"), ("element?id=" + "x" * 501, "id", "bad-parameter"),
    ("element", "id", "bad-parameter"), ("path?from=customer", "to", "bad-parameter"),
    ("neighbours?id=customer&direction=up", "direction", "bad-parameter"),
    ("elements?type=Server", "type", "bad-parameter"), ("view", "key", "bad-parameter"),
    ("elements?colour=red", "colour", "bad-parameter"), ("element?id=a&id=b", "id", "bad-parameter"),
    ("relationships?edge=a-%3Eb&from=customer", "edge", "bad-parameter"),
])
def test_bad_parameters_are_400_and_name_the_parameter(small: Client, query: str, param: str, code: str) -> None:
    st, h, body = small.get("/api/v1/" + query)
    assert st == 400 and h["content-type"] == "application/problem+json", body
    assert body["code"] == code and body["status"] == 400 and param in body["detail"] + body.get("parameter", "")
    assert body["parameter"] == param if "parameter" in body else True


def test_limit_errors_name_the_limit(small: Client) -> None:
    body = small.get("/api/v1/elements?limit=500")[2]
    assert body["maximum"] == 200 and body["minimum"] == 1 and "200" in body["detail"]
    assert "4" in small.get("/api/v1/tree?depth=9")[2]["detail"]


def test_problem_details_shape_and_candidates(small: Client) -> None:
    st, h, body = small.get("/api/v1/element?id=billing/wep")
    assert st == 404 and h["content-type"] == "application/problem+json"
    assert {"type", "title", "status", "detail", "instance"} <= set(body)
    assert body["status"] == 404 and body["instance"] == "/api/v1/element?id=billing/wep"
    assert body["type"].startswith("urn:buildzr:problem:") and body["code"] == "element-not-found"
    assert "billing/web" in body["candidates"] and len(body["candidates"]) <= 5 and body["nearest"] == "billing"
    assert body["modelHash"].startswith("sha256:") and "etag" not in h
    st, _h, v = small.get("/api/v1/view?key=billing-container")
    assert st == 404 and v["code"] == "view-not-found" and v["candidates"] == ["billing-containers"]
    st, _h, e = small.get("/api/v1/nothing")
    assert st == 404 and e["code"] == "unknown-endpoint" and "element" in e["endpoints"]
    assert small.get("/api/v1/element/?id=customer")[0] == 404  # no trailing slash variants
    assert small.get("/api/v1/neighbours?id=zzzz-nothing-like-it")[2]["candidates"] == []
    many = Api(model_of_small())
    with pytest.raises(ApiError) as ei:
        many.answer("element", "id=billing/a")
    assert len(ei.value.extra["candidates"]) <= 5


def model_of_small() -> Json:
    return _load(os.path.join(SMALL_DIR, "model.json"))


def test_api_path_without_slash_redirects(small: Client) -> None:
    st, h, _b = small.call("GET", "/api/v1")
    assert st == 301 and h["location"] == "/api/v1/"


# --- HTTP behaviour: ETag, 304, headers -----------------------------------------------------------------


@pytest.mark.parametrize("path", ["/api/v1/", "/api/v1/element?id=customer", "/api/v1/elements?q=a", "/api/v1/tree",
                                  "/api/v1/neighbours?id=billing", "/api/v1/path?from=customer&to=crm",
                                  "/api/v1/relationships", "/api/v1/views", "/api/v1/view?key=landscape"])
def test_every_answer_has_a_strong_etag_and_304s(small: Client, path: str) -> None:
    st, h, body = small.get(path)
    assert st == 200 and h["content-type"] == "application/json"
    assert body["apiVersion"] == "1" and body["modelHash"].startswith("sha256:")
    etag = h["etag"]
    assert etag == f'"{body["modelHash"]}"' and not etag.startswith("W/")
    assert h["cache-control"] == "no-cache" and int(h["content-length"]) == len(json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode())
    for inm in (etag, f"W/{etag}", f'"x", {etag}', "*"):
        st, h2, raw = small.call("GET", path, {"If-None-Match": inm})
        assert (st, raw) == (304, b""), inm
        assert h2["etag"] == etag
    assert small.call("GET", path, {"If-None-Match": '"other"'})[0] == 200
    st, h3, raw = small.call("HEAD", path)
    assert st == 200 and raw == b"" and h3["etag"] == etag and h3["content-length"] == h["content-length"]


def test_a_bad_request_is_not_hidden_by_if_none_match(small: Client) -> None:
    etag = small.get("/api/v1/")[1]["etag"]
    assert small.call("GET", "/api/v1/element?id=nope", {"If-None-Match": etag})[0] == 404


def test_every_element_in_every_answer_has_a_viewer_url(small: Client) -> None:
    for e in small.ok("/api/v1/elements?limit=200")["items"]:
        assert e["viewerUrl"] and e["viewerUrl"].startswith("/#/m")
    for n in small.ok("/api/v1/neighbours?id=billing&depth=2")["items"]:
        assert n["element"]["viewerUrl"]
    for node in small.ok("/api/v1/tree?depth=4")["items"]:
        assert node["viewerUrl"]
    for v in small.ok("/api/v1/views")["items"]:
        assert v["viewerUrl"].startswith("/#/v/")
    assert all(i["viewerUrl"] for i in small.ok("/api/v1/view?key=billing-containers")["view"]["elements"])


def test_llms_txt(small: Client, small_site: Path) -> None:
    st, h, raw = small.call("GET", "/llms.txt")
    text = raw.decode()
    assert st == 200 and h["content-type"].startswith("text/plain") and len(raw) < 2048
    assert text.startswith("# Small fixture") and "/api/v1/" in text and "/api/v1/neighbours?id={id}" in text
    assert h["etag"] == small.get("/api/v1/")[1]["etag"]
    assert small.call("GET", "/llms.txt", {"If-None-Match": h["etag"]})[0] == 304
    assert not (small_site / "llms.txt").exists()  # generated, not a file


# --- read-only ------------------------------------------------------------------------------------------


def snapshot(root: Path) -> dict[str, str]:
    out = {}
    for d, _dirs, files in os.walk(root):
        for f in files:
            p = os.path.join(d, f)
            with open(p, "rb") as fh:
                out[os.path.relpath(p, root)] = hashlib.sha256(fh.read()).hexdigest()
    return out


def test_write_methods_are_405_under_the_api_and_501_elsewhere(small: Client, small_site: Path) -> None:
    before = snapshot(small_site)
    for method in ("POST", "PUT", "DELETE", "PATCH"):
        for path in ("/api/v1/", "/api/v1/element?id=customer", "/api/v1/elements", "/api/v1/nothing"):
            st, h, raw = small.call(method, path, {"Content-Type": "application/json"}, b"{}")
            body = json.loads(raw)
            assert st == 405 and h["content-type"] == "application/problem+json" and h["allow"] == "GET, HEAD", (method, path)
            assert body["status"] == 405 and body["code"] == "method-not-allowed" and body["instance"] == path
        assert small.call(method, "/data/index.json", body=b"{}")[0] == 501  # static files: unchanged
        assert small.call(method, "/llms.txt", body=b"{}")[0] == 501
    assert small.call("OPTIONS", "/api/v1/element")[0] == 501  # not handled
    assert snapshot(small_site) == before


def test_nothing_outside_the_site_can_be_read_through_the_api(small_site: Path, tmp_path: Path) -> None:
    secret = tmp_path / "secret.json"
    secret.write_text("{}")
    opened: list[str] = []
    real_open = builtins.open

    def spy(file: Any, *a: Any, **kw: Any) -> Any:
        if isinstance(file, (str, os.PathLike)):
            opened.append(os.fspath(file))
        return real_open(file, *a, **kw)
    srv, port = start(small_site)
    c = Client(port)
    builtins.open = spy
    try:
        hostile = ["../../etc/passwd", "..%2f..%2fetc%2fpasswd", "%2e%2e/%2e%2e/etc/passwd", "/etc/passwd", "C:%5Cwindows",
                   "a%00b", "billing%00/../../../etc/passwd", str(secret), "....//....//etc/passwd", "billing/../../x"]
        for h in hostile:
            for ep in ("element?id=", "tree?id=", "neighbours?id=", "elements?within=", "relationships?from=", "path?from=customer&to=",
                       "view?key=", "views?scope=", "relationships?edge="):
                st, _hd, raw = c.call("GET", f"/api/v1/{ep}{h}")
                assert st in (400, 404), (ep, h, st)
                assert json.loads(raw)["status"] == st
        for raw_path in ("//example.com/api/v1/element?id=customer", "/api/v1/../data/index.json", "/api/v1/%2e%2e/data/index.json", "/api/v1/..%2fdata%2findex.json",
                         "/api/v1//etc/passwd", "/api/v1/element/../../../etc/passwd"):
            st, hd, _raw = c.call("GET", raw_path)
            assert st in (301, 400, 404) and hd.get("content-type", "").startswith(("application/problem+json", "text/html", "text/plain"))
        st, _h, raw = c.call("GET", "/api/v1/element?id=a%00b")
        assert st == 400 and json.loads(raw)["code"] == "bad-parameter"
    finally:
        builtins.open = real_open
        srv.shutdown()
        srv.server_close()
    assert [p for p in opened if os.path.basename(p) in ("passwd", "secret.json")] == []
    root = os.path.realpath(small_site)
    assert any(os.path.realpath(p).startswith(root + os.sep) for p in opened)  # the spy did see the server read the model
    assert [p for p in opened if os.path.realpath(p).startswith(str(tmp_path)) and
            not os.path.realpath(p).startswith(root + os.sep)] == []  # nothing else under the temp folder was opened


def test_index_json_cannot_point_the_model_outside_the_site(small_site: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(small_site, site)
    (tmp_path / "evil.json").write_text(json.dumps(model_of(small_site)))
    cases = ["../../evil.json", "/" + str(tmp_path / "evil.json"), "scene/../../../evil.json", "a\0b", "..\\..\\evil.json", ""]
    index = _load(str(site / "data" / "index.json"))
    for bad in cases:
        index["model"]["file"] = bad
        (site / "data" / "index.json").write_text(json.dumps(index))
        with pytest.raises(ApiError) as ei:
            Source(str(site)).current()
        assert ei.value.status == 503 and ei.value.code == "model-unavailable"
    index["model"]["file"] = "link.json"  # a symlink to a file outside
    os.symlink(tmp_path / "evil.json", site / "data" / "link.json")
    (site / "data" / "index.json").write_text(json.dumps(index))
    with pytest.raises(ApiError) as ei:
        Source(str(site)).current()
    assert ei.value.status == 503


def test_a_scene_path_in_index_json_cannot_escape_either(small_site: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(small_site, site)
    (tmp_path / "scene.json").write_text(json.dumps({"edges": [{"rels": ["leaked"]}]}))
    index = _load(str(site / "data" / "index.json"))
    index["scenes"]["v/billing-containers"]["file"] = "../../scene.json"
    (site / "data" / "index.json").write_text(json.dumps(index))
    srv, port = start(site)
    try:
        v = Client(port).ok("/api/v1/view?key=billing-containers")["view"]
        assert v["relationships"] is None  # unreadable scene: the answer says so and leaks nothing
    finally:
        srv.shutdown()
        srv.server_close()


# --- missing, broken, rebuilt ---------------------------------------------------------------------------


def test_no_model_is_a_problem_and_not_a_hang(tmp_path: Path) -> None:
    (tmp_path / "index.html").write_text("<html></html>")
    srv, port = start(tmp_path)
    try:
        c = Client(port)
        st, h, body = c.get("/api/v1/")
        assert st == 503 and h["content-type"] == "application/problem+json" and body["code"] == "model-unavailable"
        assert str(tmp_path) not in json.dumps(body)  # no file system paths in answers
        assert c.call("GET", "/llms.txt")[0] == 503
        assert c.call("GET", "/index.html")[0] == 200
        (tmp_path / "data").mkdir()
        (tmp_path / "data" / "index.json").write_text("{not json")
        assert c.get("/api/v1/")[0] == 503
        (tmp_path / "data" / "index.json").write_text(json.dumps({"model": {"file": "model.json"}}))
        assert c.get("/api/v1/element?id=x")[2]["code"] == "model-unavailable"  # model file missing
        (tmp_path / "data" / "model.json").write_text(json.dumps({"schema": "buildzr.model/9"}))
        assert "buildzr.model/2" in c.get("/api/v1/")[2]["detail"]
        (tmp_path / "data" / "model.json").write_text(json.dumps({"schema": "buildzr.model/2", "elements": 1}))
        assert c.get("/api/v1/")[0] in (500, 503)  # shape errors never become a traceback
    finally:
        srv.shutdown()
        srv.server_close()


def test_a_rebuilt_site_is_picked_up_without_a_restart(small_site: Path, example_site: Path, tmp_path: Path) -> None:
    site = tmp_path / "site"
    shutil.copytree(small_site, site)
    srv, port = start(site)
    try:
        c = Client(port)
        first = c.get("/api/v1/")
        assert first[2]["name"] == "Small fixture"
        etag = first[1]["etag"]
        shutil.rmtree(site)
        shutil.copytree(example_site, site)  # what build does: the whole folder is replaced
        second = c.get("/api/v1/", {"If-None-Match": etag})
        assert second[0] == 200 and second[2]["name"] != "Small fixture" and second[1]["etag"] != etag
        assert c.get("/api/v1/element?id=customer")[2]["element"]["name"] == "Customer"
    finally:
        srv.shutdown()
        srv.server_close()


# --- CORS and public URL --------------------------------------------------------------------------------


def test_no_cors_headers_by_default(small: Client) -> None:
    for path in ("/api/v1/", "/api/v1/element?id=nope", "/data/index.json"):
        _st, h, _b = small.call("GET", path, {"Origin": "https://tool.example.com"})
        assert not any(k.startswith("access-control") for k in h) and "vary" not in h, path


def test_cors_only_for_listed_origins(small_site: Path) -> None:
    srv, port = start(small_site, cors_origins=["https://tool.example.com", "http://localhost:3000"])
    c = Client(port)
    try:
        for path in ("/api/v1/", "/api/v1/element?id=customer", "/api/v1/element?id=nope", "/api/v1/nothing"):
            for origin in ("https://tool.example.com", "http://localhost:3000"):
                _st, h, _b = c.call("GET", path, {"Origin": origin})
                assert h["access-control-allow-origin"] == origin and h["vary"] == "Origin", (path, origin)
            for origin in ("https://evil.example.com", "https://tool.example.com.evil.com", "null", "*", "HTTPS://TOOL.EXAMPLE.COM"):
                _st, h, _b = c.call("GET", path, {"Origin": origin})
                assert "access-control-allow-origin" not in h and "vary" not in h, (path, origin)
            assert "access-control-allow-origin" not in c.call("GET", path)[1]
        etag = c.get("/api/v1/")[1]["etag"]
        st, h, _b = c.call("GET", "/api/v1/", {"Origin": "https://tool.example.com", "If-None-Match": etag})
        assert st == 304 and h["access-control-allow-origin"] == "https://tool.example.com"
        assert c.call("POST", "/api/v1/", {"Origin": "https://tool.example.com"})[1]["access-control-allow-origin"] == "https://tool.example.com"
        assert c.call("OPTIONS", "/api/v1/", {"Origin": "https://tool.example.com"})[0] == 501
    finally:
        srv.shutdown()
        srv.server_close()


def test_option_values_are_validated() -> None:
    assert normalise_public_url("https://models.example.com/") == "https://models.example.com"
    assert normalise_public_url("http://127.0.0.1:8000//") == "http://127.0.0.1:8000"
    assert normalise_public_url("https://x.example.com/pr/42/") == "https://x.example.com/pr/42"
    for bad in ("ftp://x", "models.example.com", "https://", "https://x?a=1", "https://x#f", "javascript:alert(1)", "//x", "", "https:// x"):
        with pytest.raises(ValueError):
            normalise_public_url(bad)
    assert normalise_origin("https://tool.example.com") == "https://tool.example.com"
    for bad in ("*", "https://*.example.com", "https://x/path", "https://x/", "tool.example.com", "ftp://x", "", "https://"):
        with pytest.raises(ValueError):
            normalise_origin(bad)


def test_serve_command_validates_and_passes_the_new_flags(tmp_path: Path, monkeypatch: pytest.MonkeyPatch,
                                                           capsys: pytest.CaptureFixture[str]) -> None:
    calls: list[tuple[Any, ...]] = []
    monkeypatch.setattr(cli, "serve", lambda *a, **kw: calls.append(a))
    site = tmp_path / "built"
    (site / "data").mkdir(parents=True)
    (site / "data" / "index.json").write_text("{}")
    (site / "build.json").write_text('{"modelHash": "sha256:00"}')
    monkeypatch.chdir(tmp_path)
    assert cli.main(["serve", str(site), "--public-url", "https://m.example.com/", "--cors-origin", "https://a.example.com",
                     "--cors-origin", "https://a.example.com", "--cors-origin", "http://b.example.com:8080"]) == 0
    assert calls == [(str(site), "127.0.0.1", 8000, "https://m.example.com", ["https://a.example.com", "http://b.example.com:8080"])]
    capsys.readouterr()
    assert cli.main(["serve", str(site)]) == 0 and calls[-1][3:] == (None, [])
    for argv, text in ((["--public-url", "ftp://x"], "--public-url:"), (["--public-url", "x.example.com"], "--public-url:"),
                       (["--cors-origin", "*"], "--cors-origin:"), (["--cors-origin", "https://x/y"], "--cors-origin:")):
        n = len(calls)
        assert cli.main(["serve", str(site), *argv]) == 2
        assert text in capsys.readouterr().err and len(calls) == n


def test_public_url_makes_absolute_links(small_site: Path) -> None:
    srv, port = start(small_site, public_url="https://models.example.com/pr/42")
    c = Client(port)
    try:
        doc = c.ok("/api/v1/")
        assert doc["viewerUrl"] == "https://models.example.com/pr/42/" and doc["publicUrlConfigured"] is True
        assert doc["endpoints"]["element"] == "https://models.example.com/pr/42/api/v1/element?id={id}"
        e = c.ok("/api/v1/element?id=billing/web")["element"]
        assert e["viewerUrl"] == "https://models.example.com/pr/42/#/m/billing?sel=billing/web"
        assert c.ok("/api/v1/views")["items"][1]["viewerUrl"] == "https://models.example.com/pr/42/#/v/billing-containers"
        nxt = c.ok("/api/v1/elements?limit=2")["next"]
        assert nxt.startswith("https://models.example.com/pr/42/api/v1/elements?limit=2&cursor=")
        assert "https://models.example.com/pr/42/api/v1/" in c.call("GET", "/llms.txt")[2].decode()
    finally:
        srv.shutdown()
        srv.server_close()


def test_data_only_site_still_serves_the_api(small_site: Path, tmp_path: Path) -> None:
    site = tmp_path / "data-only"
    shutil.copytree(small_site, site)
    os.remove(site / "index.html")
    shutil.rmtree(site / "assets")
    srv, port = start(site)
    srv2, port2 = start(site, public_url="https://viewer.example.com")
    try:
        c = Client(port)
        doc = c.ok("/api/v1/")
        assert doc["viewerUrl"] is None and any("viewerUrl is null" in n for n in doc["notes"])
        assert c.ok("/api/v1/element?id=billing/web")["element"]["viewerUrl"] is None
        assert c.ok("/api/v1/views")["items"][0]["viewerUrl"] is None
        assert all(i["viewerUrl"] is None for i in c.ok("/api/v1/elements")["items"])
        assert c.ok("/api/v1/path?from=customer&to=billing/db")["hops"] == 3
        assert c.call("GET", "/")[0] == 404 and c.call("GET", "/llms.txt")[0] == 200
        assert "Viewer for people" not in c.call("GET", "/llms.txt")[2].decode()
        d2 = Client(port2)
        # with --public-url there is still no viewer on this site, so there is still no viewer link
        doc2 = d2.ok("/api/v1/")
        assert doc2["viewerUrl"] is None and doc2["publicUrlConfigured"] is True and doc2["notes"] == doc["notes"]
        assert d2.ok("/api/v1/element?id=customer")["element"]["viewerUrl"] is None
        assert d2.ok("/api/v1/views")["items"][0]["viewerUrl"] is None
        assert all(i["viewerUrl"] is None for i in d2.ok("/api/v1/elements")["items"])
        assert "Viewer for people" not in d2.call("GET", "/llms.txt")[2].decode()
        assert doc2["endpoints"] and all(u.startswith("https://viewer.example.com/api/v1/") for u in doc2["endpoints"].values())
    finally:
        for s in (srv, srv2):
            s.shutdown()
            s.server_close()


# --- viewerUrl follows the hash grammar -----------------------------------------------------------------


def parse_hash(url: str) -> tuple[str, str, Optional[str]]:
    """``(route, path, sel)`` of a viewerUrl, by the grammar of docs/viewer-hash-routes.md."""
    frag = urlsplit(url).fragment
    assert frag.startswith("/"), url
    route, _, query = frag.partition("?")
    kind, _, rest = route[1:].partition("/")
    sel = None
    for part in query.split("&") if query else []:
        k, _, v = part.partition("=")
        assert k == "sel", url
        sel = v
    assert kind in ("m", "v")
    return kind, rest, sel


@pytest.mark.parametrize("which", ["small", "example"])
def test_viewer_urls_follow_the_grammar_for_every_element(which: str, small_site: Path, example_site: Path) -> None:
    model = model_of(small_site if which == "small" else example_site)
    api = Api(model)
    by_id = {e["id"]: e for e in model["elements"]}
    for e in model["elements"]:
        kind, path, sel = parse_hash(api.viewer_url(e["id"]) or "")
        assert kind == "m" and sel == e["id"] and quote(e["id"], safe="/") == e["id"]
        if e["children"]:
            assert path == e["id"]  # opens expanded
        else:
            assert path == (e["parent"] or "")  # opens at its parent with itself selected
            assert path == "" or by_id[path]["children"]
    for v in model["views"]:
        assert parse_hash(api.view_url(v["key"]) or "") == ("v", v["key"], None)


def test_urls_are_percent_encoded_and_custom_elements_have_none() -> None:
    model = model_of_small()
    odd = {**model["elements"][0], "id": "café x/y?z#w", "parent": None, "children": []}
    custom = {**model["elements"][0], "id": "gadget", "type": "Element", "parent": None, "children": []}
    model = {**model, "elements": [*model["elements"], odd, custom]}
    api = Api(model, public_url="https://x.example.com")
    assert api.viewer_url("café x/y?z#w") == "https://x.example.com/#/m?sel=caf%C3%A9%20x/y%3Fz%23w"
    assert api.viewer_url("gadget") is None
    assert api.brief("gadget")["viewerUrl"] is None


# --- structure of Query / Api, direct ---------------------------------------------------------------------


def test_query_rejects_control_characters_and_overlong_text() -> None:
    for raw in ("id=a%00b", "id=a%0Ab", "id=a%7Fb"):
        with pytest.raises(ApiError) as ei:
            Query("element", raw)
        assert ei.value.status == 400
    with pytest.raises(ApiError):
        Query("element", "&".join(f"a{i}=1" for i in range(60)))


def test_answers_stay_below_one_megabyte() -> None:
    model = model_of_small()
    big = "x" * 40_000
    els = [{**model["elements"][2], "id": f"s{i}", "name": f"S{i}", "parent": None, "children": [], "description": big, "views": []}
           for i in range(100)]
    api = Api({**model, "elements": els, "relationships": [], "views": []})
    a = api.answer("elements", "limit=200")
    assert len(json.dumps(a)) < 1_000_000 and a["truncated"] is True and a["next"] and 0 < len(a["items"]) < 100
    seen = len(a["items"])
    nxt = a["next"].split("?", 1)[1]
    a2 = api.answer("elements", nxt)
    assert a2["items"][0]["id"] == f"s{seen}"
