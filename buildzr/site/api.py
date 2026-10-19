"""The read-only Model API of a built workspace (``/<name>/api/v1/``), as pure functions over a loaded model.

:class:`Api` takes a ``buildzr.model/2`` object and answers the eight endpoints as plain dicts; it knows nothing
about HTTP. :class:`Source` finds the model through ``data/index.json`` and reloads it when the workspace is rebuilt.
``serve.py`` does the HTTP part (routing, ETag, problem details, CORS).

Relationships are the explicit ones in ``model.json``. A relationship of a descendant counts for its ancestors,
the same rule as the viewer's rollup (:func:`buildzr.site.model.rollup`); here it is read from indexes built once
per model, so each request is a lookup and not a scan of every relationship.
"""

from __future__ import annotations

import base64
import difflib
import json
import os
import threading
from typing import Any, Iterator, Optional
from urllib.parse import parse_qs, quote, urlencode

from buildzr.site.model import DEPLOYMENT_TYPES, DRAWN_TYPES, ModelIndex

Json = dict[str, Any]

API_VERSION = "1"
MODEL_SCHEMA = "buildzr.model/2"
PROBLEM_TYPE = "urn:buildzr:problem:"

#: Parameters each endpoint accepts. Anything else is a 400 that names the allowed ones.
PARAMS: dict[str, tuple[str, ...]] = {
    "element": ("id",),
    "elements": ("q", "type", "tag", "within", "limit", "cursor"),
    "tree": ("id", "depth", "limit"),
    "neighbours": ("id", "direction", "depth", "type", "limit"),
    "path": ("from", "to", "maxHops", "limit"),
    "relationships": ("from", "to", "edge", "tag", "limit", "cursor"),
    "views": ("scope", "environment"),
    "view": ("key",),
}
REPEATABLE = {"tag"}

#: (default, maximum) of ``limit`` per endpoint.
LIMITS: dict[str, tuple[int, int]] = {
    "elements": (50, 200), "relationships": (50, 200), "neighbours": (200, 1000), "tree": (500, 1000),
    "path": (3, 5),
}
DEPTH_MAX = 4
HOPS_DEFAULT, HOPS_MAX = 6, 8
Q_MAX = 200
ID_MAX = 500
ANSWER_BUDGET = 900_000  # bytes of items in one answer; the 1 MB cap leaves room for the envelope
TYPES = ("Person", "SoftwareSystem", "Container", "Component", "Element") + DEPLOYMENT_TYPES
DIRECTIONS = ("out", "in", "both")
MAX_QUERY_FIELDS = 40


class ApiError(Exception):
    """An error answer: RFC 9457 problem details (``status``, ``code``, ``title``, ``detail`` and extra members)."""

    def __init__(self, status: int, code: str, title: str, detail: str, **extra: Any) -> None:
        super().__init__(detail)
        self.status, self.code, self.title, self.detail, self.extra = status, code, title, detail, extra

    def problem(self, instance: str, model_hash: Optional[str] = None) -> Json:
        out: Json = {"type": PROBLEM_TYPE + self.code, "title": self.title, "status": self.status,
                     "detail": self.detail, "instance": instance, "code": self.code}
        out.update(self.extra)
        if model_hash:
            out["modelHash"] = model_hash
        return out


def _bad(detail: str, **extra: Any) -> ApiError:
    return ApiError(400, "bad-parameter", "Bad parameter", detail, **extra)


def _limit_error(name: str, value: int, low: int, high: int) -> ApiError:
    return ApiError(400, "limit-exceeded", "Limit exceeded",
                    f"{name} is {value}; it must be between {low} and {high}", parameter=name, minimum=low, maximum=high)


def normalise_public_url(url: str) -> str:
    """``url`` without trailing slashes; it must be an ``http(s)://`` URL without query or fragment."""
    u = url.strip()
    rest = u.split("://", 1)[1] if u.startswith(("http://", "https://")) else ""
    if not rest or rest.startswith("/") or any(c in u for c in "?# \t\n") or "\\" in u:
        raise ValueError(f"expected an http:// or https:// URL without query or fragment, got {url!r}")
    return u.rstrip("/")


def normalise_origin(origin: str) -> str:
    """A CORS origin (``scheme://host[:port]``, no path); ``*`` is refused."""
    o = origin.strip()
    rest = o.split("://", 1)[1] if o.startswith(("http://", "https://")) else ""
    if not rest or "/" in rest or any(c in o for c in "?# \t\n*") or rest.startswith(":"):
        raise ValueError(f"expected an origin like https://tool.example.com (no path, no '*'), got {origin!r}")
    return o


class Query:
    """The validated query string of one request."""

    def __init__(self, endpoint: str, raw: str) -> None:
        try:
            self.values = parse_qs(raw, keep_blank_values=True, max_num_fields=MAX_QUERY_FIELDS)
        except ValueError:
            raise _bad(f"the query string has more than {MAX_QUERY_FIELDS} fields") from None
        allowed = PARAMS[endpoint]
        for k, v in self.values.items():
            if k not in allowed:
                raise _bad(f"unknown parameter {k!r} for {endpoint}; allowed: {', '.join(allowed) or 'none'}",
                           parameter=k)
            if len(v) > 1 and k not in REPEATABLE:
                raise _bad(f"parameter {k!r} was given {len(v)} times; it can be given once", parameter=k)
            for item in v:
                if any(ord(c) < 32 or ord(c) == 127 for c in item):
                    raise _bad(f"parameter {k!r} contains a control character", parameter=k)
                if len(item) > (Q_MAX if k == "q" else ID_MAX):
                    raise _bad(f"parameter {k!r} is longer than {Q_MAX if k == 'q' else ID_MAX} characters",
                               parameter=k, maximum=Q_MAX if k == "q" else ID_MAX)
        self.endpoint = endpoint

    def get(self, name: str) -> Optional[str]:
        v = self.values.get(name)
        return v[0] if v else None

    def all(self, name: str) -> list[str]:
        return self.values.get(name, [])

    def require(self, name: str) -> str:
        v = self.get(name)
        if not v:
            raise _bad(f"parameter {name!r} is required", parameter=name)
        return v

    def integer(self, name: str, default: int, low: int, high: int) -> int:
        v = self.get(name)
        if v is None:
            return default
        try:
            n = int(v)
        except ValueError:
            raise _bad(f"{name} must be a whole number, got {v!r}", parameter=name) from None
        if not low <= n <= high:
            raise _limit_error(name, n, low, high)
        return n

    def limit(self) -> int:
        d, m = LIMITS[self.endpoint]
        return self.integer("limit", d, 1, m)

    def choice(self, name: str, allowed: tuple[str, ...], default: Optional[str] = None) -> Optional[str]:
        v = self.get(name)
        if v is None:
            return default
        if v not in allowed:
            raise _bad(f"{name} must be one of {', '.join(allowed)}; got {v!r}", parameter=name, allowed=list(allowed))
        return v

    def without_cursor(self) -> list[tuple[str, str]]:
        return [(k, i) for k, v in self.values.items() if k != "cursor" for i in v]


def _compact(obj: Any) -> int:
    return len(json.dumps(obj, ensure_ascii=False, separators=(",", ":")))


class _Budget:
    """Keeps one answer under the size cap: ``take(item)`` is false once the items would not fit."""

    def __init__(self) -> None:
        self.used = 0

    def take(self, item: Any) -> bool:
        n = _compact(item) + 1
        if self.used + n > ANSWER_BUDGET:
            return False
        self.used += n
        return True


class Api:
    """The eight endpoints over one loaded model.

    Args:
        model: A ``buildzr.model/2`` object.
        public_url: ``http(s)://`` base for links (no trailing slash), or ``None`` for root-relative links.
        viewer: Whether a viewer is served next to the API (``index.html`` exists).
        views_scene: Returns the scene object of a view key, or ``None`` when it cannot be read.
        built_with: The ``build.json`` object, if there is one.
        base_path: Where the workspace sits on the server, as ``/shop`` (``""`` for the root); the links carry it.
    """

    def __init__(self, model: Json, public_url: Optional[str] = None, viewer: bool = True,
                 views_scene: Any = None, built_with: Optional[Json] = None, base_path: str = "") -> None:
        self.model = model
        self.hash: str = model["modelHash"]
        self.public_url = public_url
        self.viewer = viewer
        self._scene = views_scene
        self.built_with = built_with
        self.base = (public_url or "") + base_path + "/"
        self.api_base = self.base + "api/v1/"
        mi = ModelIndex(model)
        self.el = mi.el
        self.rel = mi.rel
        self.order = {e["id"]: i for i, e in enumerate(model["elements"])}
        self.anc: dict[str, tuple[str, ...]] = {e["id"]: tuple(mi.ancestors_or_self(e["id"])) for e in model["elements"]}
        self.subtree: dict[str, list[str]] = {e["id"]: [] for e in model["elements"]}
        for e in model["elements"]:
            for a in self.anc[e["id"]]:
                self.subtree[a].append(e["id"])  # pre-order, because the elements are
        self.out_own: dict[str, list[Json]] = {p: [] for p in self.el}
        self.out_sub: dict[str, list[Json]] = {p: [] for p in self.el}
        self.in_sub: dict[str, list[Json]] = {p: [] for p in self.el}
        self.in_own: dict[str, list[Json]] = {p: [] for p in self.el}
        for r in model["relationships"]:  # sorted by id in the model
            self.out_own[r["source"]].append(r)
            self.in_own[r["destination"]].append(r)
            for a in self.anc[r["source"]]:
                self.out_sub[a].append(r)
            for a in self.anc[r["destination"]]:
                self.in_sub[a].append(r)
        self.by_tag: dict[str, list[str]] = {}
        for e in model["elements"]:
            for t in e["tags"]:
                self.by_tag.setdefault(t.casefold(), []).append(e["id"])
        self.views = {v["key"]: v for v in model["views"]}
        self.environments: list[Json] = (model.get("deployment") or {}).get("environments") or []
        self.text: dict[str, tuple[str, str, str, str, str]] = {}
        for e in model["elements"]:
            self.text[e["id"]] = (
                e["name"].casefold(), (e["description"] or "").casefold(), (e["technology"] or "").casefold(),
                " ".join(e["tags"]).casefold(), " ".join(f"{k} {v}" for k, v in e["properties"].items()).casefold())
        self.rel_tags = {r["id"]: {t.casefold() for t in r["tags"]} for r in model["relationships"]}
        self._etype: dict[str, int] = {}

    # --- links ----------------------------------------------------------------------------------

    @property
    def links_to_viewer(self) -> bool:
        return self.viewer

    def viewer_url(self, path: str) -> Optional[str]:
        """The link that opens the viewer at element ``path`` (``docs/viewer-hash-routes.md``), or ``None``."""
        if not self.links_to_viewer:
            return None
        e = self.el[path]
        if e["type"] in DEPLOYMENT_TYPES:  # drawn only in deployment views: the first one that shows it
            if not e["views"]:
                return None
            return f"{self.base}#/v/{quote(e['views'][0], safe='/')}?sel={quote(path, safe='/')}"
        if e["type"] not in DRAWN_TYPES:
            return None
        if e["children"]:
            return f"{self.base}#/m/{quote(path, safe='/')}?sel={quote(path, safe='/')}"
        parent = e["parent"]
        where = f"/{quote(parent, safe='/')}" if parent else ""
        return f"{self.base}#/m{where}?sel={quote(path, safe='/')}"

    def view_url(self, key: str) -> Optional[str]:
        return f"{self.base}#/v/{quote(key, safe='/')}" if self.links_to_viewer else None

    def workspace_url(self) -> Optional[str]:
        return self.base if self.links_to_viewer else None

    # --- shapes ---------------------------------------------------------------------------------

    def summary(self, path: str) -> Json:
        e = self.el[path]
        return {"id": path, "name": e["name"], "type": e["type"], "parent": e["parent"],
                "description": e["description"], "technology": e["technology"], "tags": e["tags"],
                "childCount": len(e["children"]), "viewerUrl": self.viewer_url(path)}

    def brief(self, path: str) -> Json:
        e = self.el[path]
        return {"id": path, "name": e["name"], "type": e["type"], "childCount": len(e["children"]),
                "viewerUrl": self.viewer_url(path)}

    @staticmethod
    def relationship(r: Json) -> Json:
        return {"id": r["id"], "source": r["source"], "destination": r["destination"],
                "description": r["description"], "technology": r["technology"], "tags": r["tags"],
                "properties": r["properties"]}

    def envelope(self, **members: Any) -> Json:
        return {"apiVersion": API_VERSION, "modelHash": self.hash, **members}

    def _find(self, name: str, value: str) -> str:
        if value in self.el:
            return value
        cands = difflib.get_close_matches(value, list(self.el), n=5, cutoff=0.5)
        nearest = value
        while "/" in nearest:
            nearest = nearest.rsplit("/", 1)[0]
            if nearest in self.el:
                break
        else:
            nearest = ""
        detail = f"No element {value!r}."
        extra: Json = {"parameter": name, "candidates": cands}
        if nearest in self.el:
            detail += f" Nearest existing ancestor: {nearest!r}."
            extra["nearest"] = nearest
        if cands:
            detail += " Did you mean: " + ", ".join(repr(c) for c in cands) + "?"
        raise ApiError(404, "element-not-found", "Element not found", detail, **extra)

    # --- paging ---------------------------------------------------------------------------------

    def _cursor(self, offset: int) -> str:
        raw = json.dumps({"o": offset, "h": self.hash.split(":")[-1][:12]}, separators=(",", ":"))
        return base64.urlsafe_b64encode(raw.encode()).decode().rstrip("=")

    def _offset(self, q: Query) -> int:
        c = q.get("cursor")
        if c is None:
            return 0
        try:
            d = json.loads(base64.urlsafe_b64decode(c + "=" * (-len(c) % 4)))
            off, h = d["o"], d["h"]
            if not isinstance(off, int) or off < 0 or not isinstance(h, str):
                raise ValueError
        except (ValueError, KeyError, TypeError):
            raise _bad("cursor is not a cursor this API issued", parameter="cursor") from None
        if h != self.hash.split(":")[-1][:12]:
            raise ApiError(409, "cursor-stale", "Cursor is stale",
                           "the model changed since this cursor was issued; start again without a cursor",
                           parameter="cursor")
        return off

    def _page(self, endpoint: str, q: Query, rows: list[Any], render: Any) -> tuple[list[Json], Optional[str], bool]:
        """One page of ``rows``: the rendered items, the ``next`` URL and ``truncated``."""
        limit, off = q.limit(), self._offset(q)
        budget = _Budget()
        items: list[Json] = []
        i = off
        while i < len(rows) and len(items) < limit:
            item = render(rows[i])
            if items and not budget.take(item):
                break
            if not items:
                budget.take(item)
            items.append(item)
            i += 1
        if i >= len(rows):
            return items, None, False
        params = q.without_cursor() + [("cursor", self._cursor(i))]
        return items, f"{self.api_base}{endpoint}?{urlencode(params)}", True

    # --- endpoints ------------------------------------------------------------------------------

    def answer(self, endpoint: str, raw_query: str) -> Json:
        """The answer of ``endpoint`` for a query string; raises :class:`ApiError`."""
        if endpoint == "":
            if raw_query:
                raise _bad("the orientation document takes no parameters")
            return self.orientation()
        q = Query(endpoint, raw_query)
        fn = {"element": self.element, "elements": self.elements, "tree": self.tree,
              "neighbours": self.neighbours, "path": self.path, "relationships": self.relationships,
              "views": self.views_answer, "view": self.view}[endpoint]
        out: Json = fn(q)
        return out

    def orientation(self) -> Json:
        by_type: dict[str, int] = {}
        for e in self.model["elements"]:
            by_type[e["type"]] = by_type.get(e["type"], 0) + 1
        tags = sorted({t for e in self.model["elements"] for t in e["tags"]})
        ws = self.model["workspace"]
        bw = self.built_with or {}
        b = self.api_base
        sample = next((e["id"] for e in self.model["elements"] if e["parent"]), None) or \
            (self.model["elements"][0]["id"] if self.model["elements"] else "name")
        notes = []
        if not self.viewer:
            notes.append("This workspace has no viewer, so viewerUrl is null everywhere.")
        broken = bw.get("status") == "broken"
        if broken:
            notes.append(f"This workspace is broken: building it failed at the {bw.get('stage')} step. The answers "
                         "come from data that failed its checks and may be wrong; see errors.")
        state: Json = {"status": "broken", "stage": bw.get("stage"), "errors": broken_errors(bw)} if broken else \
            {"status": "ok"}
        out = self.envelope(
            name=ws["name"], description=ws["description"], **state,
            builtWith={"buildzr": bw.get("buildzr"), "k": bw.get("k")} if bw else None,
            counts={"elements": len(self.model["elements"]), "relationships": len(self.model["relationships"]),
                    "views": len(self.model["views"]), "byType": dict(sorted(by_type.items()))},
            tags=tags, topLevel=[e["id"] for e in self.model["elements"] if e["parent"] is None],
            environments=[{"key": e["key"], "name": e["name"], "nodes": e["nodes"], "views": e["views"]}
                          for e in self.environments],
            viewerUrl=self.workspace_url(), publicUrlConfigured=self.public_url is not None,
            howToAsk=(f"Element ids are slug paths such as {sample!r}; give them in query parameters. "
                      "Relationships are the explicit ones in the model. A relationship of a descendant counts for "
                      "its ancestors, so an arrow between two systems is the union of the relationships between "
                      "their contents. Deployment nodes, infrastructure nodes and instances are elements too, with "
                      "ids under deploy/<environment>/ (see environments); an instance names its container or "
                      "system in instanceOf. Lists are paged: follow 'next' while 'truncated' is true."),
            endpoints={
                "element": f"{b}element?id={{id}}",
                "search": f"{b}elements{{?q,type,tag,within,limit,cursor}}",
                "tree": f"{b}tree{{?id,depth,limit}}",
                "neighbours": f"{b}neighbours?id={{id}}{{&direction,depth,type,limit}}",
                "path": f"{b}path?from={{from}}&to={{to}}{{&maxHops,limit}}",
                "relationships": f"{b}relationships{{?from,to,edge,tag,limit,cursor}}",
                "views": f"{b}views{{?scope,environment}}",
                "view": f"{b}view?key={{key}}",
            },
            limits={"elements": {"default": LIMITS["elements"][0], "max": LIMITS["elements"][1]},
                    "relationships": {"default": LIMITS["relationships"][0], "max": LIMITS["relationships"][1]},
                    "neighbours": {"default": LIMITS["neighbours"][0], "max": LIMITS["neighbours"][1]},
                    "tree": {"default": LIMITS["tree"][0], "max": LIMITS["tree"][1]},
                    "pathChains": {"default": LIMITS["path"][0], "max": LIMITS["path"][1]},
                    "maxDepth": DEPTH_MAX, "maxHops": HOPS_MAX, "maxQueryLength": Q_MAX},
            notes=notes)
        return out

    def element(self, q: Query) -> Json:
        path = self._find("id", q.require("id"))
        e = self.el[path]
        crossing_out = sum(1 for r in self.out_sub[path] if path not in self.anc[r["destination"]])
        crossing_in = sum(1 for r in self.in_sub[path] if path not in self.anc[r["source"]])
        el = {"id": path, "modelId": e["modelId"], "type": e["type"], "parent": e["parent"], "children": e["children"],
              "name": e["name"], "description": e["description"], "technology": e["technology"], "tags": e["tags"],
              "properties": e["properties"], "url": e["url"], "group": e["group"], "views": e["views"],
              "childCount": len(e["children"]),
              "relationships": {"own": {"in": len(self.in_own[path]), "out": len(self.out_own[path])},
                                "withDescendants": {"in": crossing_in, "out": crossing_out}},
              "viewerUrl": self.viewer_url(path)}
        for k in ("environment", "instanceOf", "instances", "healthChecks"):
            if k in e:
                el[k] = e[k]
        return self.envelope(element=el)

    def elements(self, q: Query) -> Json:
        text = q.get("q")
        typ = q.choice("type", TYPES)
        tags = [t.casefold() for t in q.all("tag")]
        within = self._find("within", q.get("within") or "") if q.get("within") else None
        pool: list[str] = [p for p in (self.subtree[within] if within else self.el) if p != within]
        for t in tags:
            have = set(self.by_tag.get(t, ()))
            pool = [p for p in pool if p in have]
        if typ:
            pool = [p for p in pool if self.el[p]["type"] == typ]
        matched: dict[str, str] = {}
        if text:
            needle = text.casefold()
            ranked: list[tuple[int, int, str]] = []
            for p in pool:
                name, desc, tech, tg, props = self.text[p]
                if name == needle:
                    rank, field = 0, "name"
                elif name.startswith(needle):
                    rank, field = 1, "name"
                elif needle in name:
                    rank, field = 2, "name"
                elif needle in desc:
                    rank, field = 3, "description"
                elif needle in tech:
                    rank, field = 4, "technology"
                elif needle in tg:
                    rank, field = 5, "tags"
                elif needle in props:
                    rank, field = 6, "properties"
                else:
                    continue
                ranked.append((rank, self.order[p], p))
                matched[p] = field
            ranked.sort()
            pool = [p for _r, _o, p in ranked]

        def render(p: str) -> Json:
            s = self.summary(p)
            if p in matched:
                s["matched"] = matched[p]
            return s
        items, nxt, trunc = self._page("elements", q, pool, render)
        return self.envelope(total=len(pool), items=items, next=nxt, truncated=trunc)

    def tree(self, q: Query) -> Json:
        depth = q.integer("depth", 1, 1, DEPTH_MAX)
        limit = q.limit()
        root = self._find("id", q.get("id") or "") if q.get("id") else None
        budget, count, cut = _Budget(), [0], [False]

        def node(path: str, left: int) -> Optional[Json]:
            if count[0] >= limit:
                cut[0] = True
                return None
            n = self.brief(path)
            if not budget.take(n):
                cut[0] = True
                return None
            count[0] += 1
            kids = self.el[path]["children"]
            if left == 0:
                n["children"] = None if kids else []
                return n
            out: list[Json] = []
            for k in kids:
                c = node(k, left - 1)
                if c is None:
                    break
                out.append(c)
            n["children"] = out if out or not kids else None  # fewer than childCount: the walk was cut here
            return n

        items: list[Json] = []
        if root is None:
            for p in (e["id"] for e in self.model["elements"] if e["parent"] is None):
                n = node(p, depth - 1)
                if n is None:
                    break
                items.append(n)
        else:
            n = node(root, depth)
            if n is not None:
                items.append(n)
        return self.envelope(id=root, depth=depth, items=items, next=None, truncated=cut[0])

    def neighbours(self, q: Query) -> Json:
        start = self._find("id", q.require("id"))
        direction = q.choice("direction", DIRECTIONS, "both")
        depth = q.integer("depth", 1, 1, DEPTH_MAX)
        typ = q.choice("type", TYPES)
        limit = q.limit()
        dirs = ("out", "in") if direction == "both" else (direction,)
        frontier, visited, seen = [start], {start}, set()
        items: list[Json] = []
        budget, truncated = _Budget(), False
        for hop in range(1, depth + 1):
            nxt: list[str] = []
            for f in frontier:
                for d in dirs:
                    for r in (self.out_sub if d == "out" else self.in_sub)[f]:
                        near, far = (r["source"], r["destination"]) if d == "out" else (r["destination"], r["source"])
                        if f in self.anc[far] or r["id"] in seen:
                            continue  # inside the element itself, or reached already
                        seen.add(r["id"])
                        if far not in visited:
                            visited.add(far)
                            nxt.append(far)
                        if typ and self.el[far]["type"] != typ:
                            continue
                        item = {"hop": hop, "direction": d, "near": near, "relationship": self.relationship(r),
                                "element": self.brief(far)}
                        if len(items) >= limit or not budget.take(item):
                            truncated = True
                            break
                        items.append(item)
                    if truncated:
                        break
                if truncated:
                    break
            if truncated:
                break
            frontier = nxt
        return self.envelope(id=start, direction=direction, depth=depth, items=items, next=None, truncated=truncated)

    def path(self, q: Query) -> Json:
        src, dst = self._find("from", q.require("from")), self._find("to", q.require("to"))
        max_hops = q.integer("maxHops", HOPS_DEFAULT, 1, HOPS_MAX)
        limit = q.limit()
        targets = set(self.subtree[dst])
        dist: dict[str, int] = {p: 0 for p in self.subtree[src]}
        preds: dict[str, list[tuple[str, Json]]] = {}
        layer = list(dist)
        found: list[str] = []
        hops: Optional[int] = None
        for hop in range(1, max_hops + 1):
            new: dict[str, None] = {}
            for u in layer:
                for r in self.out_own[u]:
                    v = r["destination"]
                    if v in dist and dist[v] < hop:
                        continue
                    dist[v] = hop
                    preds.setdefault(v, []).append((u, r))
                    new[v] = None
            found = sorted((v for v in new if v in targets), key=self.order.__getitem__)
            if found:
                hops = hop
                break
            layer = list(new)
        chains: list[list[Json]] = []

        def walk(node: str, tail: list[Json]) -> Iterator[list[Json]]:
            if dist[node] == 0:
                yield tail
                return
            for u, r in preds[node]:
                step = {"rel": r["id"], "from": u, "to": node, "description": r["description"],
                        "technology": r["technology"]}
                yield from walk(u, [step] + tail)

        for t in found:
            for c in walk(t, []):
                chains.append(c)
                if len(chains) > limit:
                    break
            if len(chains) > limit:
                break
        truncated = len(chains) > limit
        return self.envelope(**{"from": src, "to": dst}, maxHops=max_hops, hops=hops, chains=chains[:limit],
                             next=None, truncated=truncated)

    def _edge_rels(self, edge: str) -> list[Json]:
        """The explicit relationships a scene edge id stands for.

        ``a->b`` is the rollup between two nodes of a level. In an element's scene an arrow that continues
        outside is drawn to a port: ``port:<outer edge id>-><child>`` or ``<child>->port:<outer edge id>``;
        it carries the outer edge's relationships whose inner end is inside ``child``. A dynamic view's step
        ``a->b#2`` is its pair. A relationship id that is not a pair of elements (``a->b:pays``) names that one.
        """
        e = edge.split("#", 1)[0]
        if e.startswith("port:"):
            outer, sep, child = e[5:].rpartition("->")
            if not sep:
                raise _bad(f"edge {edge!r} is not a scene edge id such as 'a->b'", parameter="edge")
            inner = self._edge_rels(outer)
            c = self._find("edge", child)
            return [r for r in inner if c in self.anc[r["destination"]]]
        if "->port:" in e:
            child, _, outer = e.partition("->port:")
            inner = self._edge_rels(outer)
            c = self._find("edge", child)
            return [r for r in inner if c in self.anc[r["source"]]]
        if "->" not in e:
            raise _bad(f"edge {edge!r} is not a scene edge id such as 'a->b'", parameter="edge")
        a, b = e.split("->", 1)
        if e in self.rel and not (a in self.el and b in self.el):
            return [self.rel[e]]  # 'a->b:description' names one relationship; 'a->b' is the rollup (which contains it)
        return self._rollup(self._find("edge", a), self._find("edge", b))

    def relationships(self, q: Query) -> Json:
        frm, to, edge = q.get("from"), q.get("to"), q.get("edge")
        tags = [t.casefold() for t in q.all("tag")]
        if edge is not None:
            if frm or to:
                raise _bad("edge cannot be combined with from or to", parameter="edge")
            rows = self._edge_rels(edge)
        elif frm and to:
            rows = self._rollup(self._find("from", frm), self._find("to", to))
        elif frm:
            a = self._find("from", frm)
            rows = self.out_sub[a]
        elif to:
            b = self._find("to", to)
            rows = self.in_sub[b]
        else:
            rows = self.model["relationships"]
        if tags:
            rows = [r for r in rows if all(t in self.rel_tags[r["id"]] for t in tags)]
        items, nxt, trunc = self._page("relationships", q, list(rows), self.relationship)
        return self.envelope(**{"from": frm, "to": to}, edge=edge, total=len(rows), items=items, next=nxt,
                             truncated=trunc)

    def _rollup(self, a: str, b: str) -> list[Json]:
        """Explicit relationships from the subtree of ``a`` to the subtree of ``b`` (``model.rollup``'s definition)."""
        return [r for r in self.out_sub[a] if b in self.anc[r["destination"]]]

    def views_answer(self, q: Query) -> Json:
        scope = self._find("scope", q.get("scope") or "") if q.get("scope") else None
        env = q.get("environment")
        if env is not None and env not in {e["key"] for e in self.environments}:
            keys = [e["key"] for e in self.environments]
            raise _bad(f"no environment {env!r}; environments: {', '.join(keys) or 'none'}", parameter="environment",
                       allowed=keys)
        items = [self._view_summary(v) for v in self.model["views"]
                 if (scope is None or v["scope"] == scope) and (env is None or v.get("environment") == env)]
        return self.envelope(items=items, next=None, truncated=False)

    def _view_summary(self, v: Json) -> Json:
        return {"key": v["key"], "viewKey": v["viewKey"], "kind": v["kind"], "title": v["title"],
                "description": v["description"], "scope": v["scope"], "environment": v.get("environment"),
                "viewerUrl": self.view_url(v["key"])}

    def view(self, q: Query) -> Json:
        key = q.require("key")
        v = self.views.get(key)
        if v is None:
            cands = difflib.get_close_matches(key, list(self.views), n=5, cutoff=0.4)
            raise ApiError(404, "view-not-found", "View not found",
                           f"No view {key!r}." + (" Did you mean: " + ", ".join(repr(c) for c in cands) + "?" if cands else ""),
                           parameter="key", candidates=cands)
        members = [e["id"] for e in self.model["elements"] if key in e["views"]]
        scene = self._scene(v["scene"]) if self._scene else None
        rels: Optional[list[str]] = None
        if scene is not None:
            rels = sorted({rid for edge in scene.get("edges", []) for rid in edge.get("rels", [])})
        view = {**self._view_summary(v), "elements": [self.brief(p) for p in members], "relationships": rels}
        return self.envelope(view=view)

    # --- llms.txt -------------------------------------------------------------------------------

    def llms_txt(self) -> str:
        o = self.orientation()
        b = self.api_base
        c = o["counts"]
        lines = [f"# {str(o['name'] or 'buildzr model')[:100]}", ""]
        if o["status"] == "broken":
            lines += [f"> WARNING: this workspace is broken (building it failed at the {o['stage']} step); the "
                      "answers may be wrong. The orientation document lists the errors.", ""]
        lines.append(f"> A C4 architecture model ({c['elements']} elements, {c['relationships']} relationships, "
                     f"{c['views']} views) with a read-only JSON API. Model hash: {o['modelHash']}.")
        if o["description"]:
            lines.append(f"> {str(o['description'])[:300]}")
        if o["viewerUrl"]:
            lines.append(f"> Viewer for people: {o['viewerUrl']}")
        if o["environments"]:
            envs = ", ".join(f"{str(e['name'])[:60]} (`{e['key']}`)" for e in o["environments"][:10])
            lines.append(f"> Deployment environments: {envs}. Their elements have ids under `deploy/<key>/`.")
        lines += ["", "Start with the orientation document, then ask:", "", f"- [Orientation]({b}): counts, tags, top level, limits"]
        names = {"element": "One element", "search": "Search elements", "tree": "Element tree",
                 "neighbours": "Neighbours", "path": "Shortest chains", "relationships": "Relationships",
                 "views": "Authored views", "view": "One view"}
        for k, tmpl in o["endpoints"].items():
            lines.append(f"- [{names[k]}]({tmpl})")
        lines += ["", "Element ids are slug paths (e.g. `shop/web-app`) and go in query parameters. "
                  "Answers carry `modelHash` and an `ETag`; errors are RFC 9457 problem details.", ""]
        return "\n".join(lines)


def broken_errors(info: Json) -> list[str]:
    """The first 10 errors of a broken ``build.json``."""
    errors = info.get("errors")
    return [str(e) for e in errors[:10]] if isinstance(errors, list) else []


def broken_error(info: Json) -> "ApiError":
    """The 503 answer of every data endpoint of a broken workspace that has no data (stage ``model`` or ``layout``)."""
    stage = info.get("stage")
    errors = broken_errors(info)
    return ApiError(503, "workspace-broken", "Workspace broken",
                    f"building this workspace failed at the {stage} step, so it has no model data"
                    + (f": {errors[0]}" if errors else ""), stage=stage, errors=errors)


class Source:
    """Finds the model of a built workspace through ``data/index.json`` and reloads it when it is rebuilt."""

    def __init__(self, directory: str, public_url: Optional[str] = None, base_path: str = "") -> None:
        self.directory = os.path.abspath(directory)
        self.public_url = public_url
        self.base_path = base_path
        self._api: Optional[Api] = None
        self._sig: Optional[tuple[int, int, int]] = None
        self._lock = threading.Lock()
        self._scenes: dict[str, Optional[Json]] = {}

    def _data_path(self, rel: Any) -> str:
        """``data/<rel>`` for a file name taken from ``index.json``; refuses anything that leaves ``data/``."""
        if not isinstance(rel, str) or not rel or "\0" in rel or "\\" in rel or rel.startswith("/") or \
                ".." in rel.split("/") or ":" in rel.split("/")[0]:
            raise ApiError(503, "model-unavailable", "Model unavailable", f"data/index.json names a bad file: {rel!r}")
        data = os.path.realpath(os.path.join(self.directory, "data"))
        full = os.path.realpath(os.path.join(data, rel))
        if not full.startswith(data + os.sep):
            raise ApiError(503, "model-unavailable", "Model unavailable", f"data/index.json names a bad file: {rel!r}")
        return full

    @staticmethod
    def _read_json(path: str) -> Any:
        with open(path, encoding="utf-8") as f:
            return json.load(f)

    def _load(self) -> Api:
        try:
            if not os.path.exists(os.path.join(self.directory, "data", "index.json")):
                try:
                    info = self._read_json(os.path.join(self.directory, "build.json"))
                except (OSError, ValueError):
                    info = None
                if isinstance(info, dict) and info.get("status") == "broken":
                    raise broken_error(info)
            index = self._read_json(os.path.join(self.directory, "data", "index.json"))
            model = self._read_json(self._data_path(index["model"]["file"]))
            if not isinstance(model, dict) or model.get("schema") != MODEL_SCHEMA:
                raise ApiError(503, "model-unavailable", "Model unavailable",
                               f"the model is not {MODEL_SCHEMA}; this buildzr reads {MODEL_SCHEMA} only")
            self._scenes = {}
            try:
                built: Optional[Json] = self._read_json(os.path.join(self.directory, "build.json"))
                if not isinstance(built, dict):
                    built = None
            except (OSError, ValueError):
                built = None
            viewer = os.path.isfile(os.path.join(self.directory, "index.html"))
            self._index = index
            return Api(model, self.public_url, viewer, self._scene, built, self.base_path)
        except ApiError:
            raise
        except FileNotFoundError:
            raise ApiError(503, "model-unavailable", "Model unavailable",
                           "this workspace has no readable data/index.json or model file (is a build running?)") from None
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            raise ApiError(503, "model-unavailable", "Model unavailable",
                           "the model of this workspace cannot be read (data/index.json or the model file is damaged)") from None

    def _scene(self, key: str) -> Optional[Json]:
        if key in self._scenes:
            return self._scenes[key]
        scene: Optional[Json] = None
        try:
            entry = self._index["scenes"][key]
            data = self._read_json(self._data_path(entry["file"]))
            scene = data if isinstance(data, dict) else None
        except (ApiError, OSError, ValueError, KeyError, TypeError):
            scene = None
        self._scenes[key] = scene
        return scene

    def current(self) -> Api:
        """The :class:`Api` of the workspace as it is now; raises a 503 :class:`ApiError` when it cannot be read."""
        path = os.path.join(self.directory, "data", "index.json")
        try:
            st = os.stat(path)
            sig: Optional[tuple[int, int, int]] = (st.st_mtime_ns, st.st_size, st.st_ino)
        except OSError:
            sig = None
        with self._lock:
            if self._api is None or sig != self._sig:
                self._api = None
                self._sig = None
                api = self._load()
                self._api, self._sig = api, sig
            return self._api
