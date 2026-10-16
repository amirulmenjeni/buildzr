"""Build the level graphs (``buildzr.levels/2``): the model-to-layout hand-over.

One level per scene to lay out: ``landscape``, ``e/<path>`` for every element
with children and ``v/<key>`` for every authored view. A level has nodes with
resolved style and unwrapped label lines, rolled-up edges with the explicit
relationships they stand for, and (element levels) ports, one per edge of the
parent level that touches the scope. See ``schema/levels.schema.json``.
"""

from __future__ import annotations

from typing import Any, Optional

from buildzr.site.canonical import rnd
from buildzr.site.model import DRAWN_TYPES, ModelIndex, VIEW_KINDS, slug, workspace_json
from buildzr.site.styles import TYPE_TEXT, Styles

Json = dict[str, Any]

LEVELS_SCHEMA = "buildzr.levels/2"
TIER_RATIO = 0.75  # tier 1 and 2 text size relative to the node font size (16 -> 12)


class _Builder:
    def __init__(self, ws: Json, model: Json, text_color: str) -> None:
        self.ws = ws
        self.model = model
        self.idx = ModelIndex(model)
        self.styles = Styles(ws, text_color)
        self._anc: dict[str, list[str]] = {}
        self.raw_rels: dict[str, Json] = {}  # Structurizr id -> relationship (implied ones too)
        m = ws.get("model", {})
        holders: list[Json] = list(m.get("people", []))
        for s in m.get("softwareSystems", []):
            holders.append(s)
            for c in s.get("containers", []):
                holders.append(c)
                holders.extend(c.get("components", []))
        for h in holders:
            for r in h.get("relationships", []):
                self.raw_rels[str(r["id"])] = r

    # --- nodes ---------------------------------------------------------------------

    def anc(self, path: str) -> list[str]:
        if path not in self._anc:
            self._anc[path] = self.idx.ancestors_or_self(path)
        return self._anc[path]

    def lines(self, el: Json, role: str, fs: float) -> list[Json]:
        small = rnd(fs * TIER_RATIO)
        tech = f": {el['technology']}" if el["technology"] else ""
        out: list[Json] = [{"text": el["name"], "tier": 0, "weight": "bold"},
                           {"text": f"[{TYPE_TEXT.get(el['type'], el['type'])}{tech}]", "tier": 1, "size": small}]
        if el["description"] and role == "element":
            out.append({"text": el["description"], "tier": 2, "size": small})
        return out

    def node(self, path: str, role: str, parent: Optional[str], with_children: bool) -> Json:
        el = self.idx.el[path]
        style, shape = self.styles.node(el["type"], el["tags"], role)
        n: Json = {"id": path, "modelId": el["modelId"], "role": role, "type": el["type"], "parent": parent,
                   "name": el["name"], "tags": el["tags"], "shape": shape, "style": style,
                   "lines": self.lines(el, role, float(style["fontSize"]))}
        if with_children and el["children"]:
            n["children"] = len(el["children"])
            n["childType"] = self.idx.el[el["children"][0]]["type"]
        return n

    def arrange(self, parent_of: dict[str, Optional[str]], boundaries: set[str], with_children: bool) -> list[Json]:
        """Nodes in pre-order (siblings sorted by id), wrapping elements of a group in group boundaries.

        ``parent_of`` maps every element path of the level to its enclosing boundary element (or None).
        A group of the element becomes a ``group:<slug path>`` boundary node unless it is the group of the
        enclosing boundary element itself (Structurizr groups are scoped to one level).
        """
        final: dict[str, Optional[str]] = {}
        groups: dict[str, Json] = {}
        for n, p in parent_of.items():
            g = self.idx.el[n]["group"]
            if not g or g == (self.idx.el[p]["group"] if p else None):
                final[n] = p
                continue
            segs, parent = g.split("/"), p
            prefix = f"group:{p}/" if p else "group:"
            for i in range(len(segs)):
                gid = prefix + "/".join(slug(x) for x in segs[: i + 1])
                if gid not in groups:
                    full = "/".join(segs[: i + 1])
                    style, shape = self.styles.node("Group", ["Element", "Group", f"Group:{full}"], "boundary")
                    groups[gid] = {"id": gid, "role": "boundary", "type": "Group", "parent": parent,
                                   "name": segs[i], "tags": ["Element", "Group", f"Group:{full}"],
                                   "shape": shape, "style": style,
                                   "lines": [{"text": segs[i], "tier": 0, "weight": "bold"}]}
                parent = gid
            final[n] = parent
        kids: dict[Optional[str], list[str]] = {}
        for n, p in final.items():
            kids.setdefault(p, []).append(n)
        for gid, g in groups.items():
            kids.setdefault(g["parent"], []).append(gid)
        out: list[Json] = []

        def walk(p: Optional[str]) -> None:
            for n in sorted(kids.get(p, [])):
                if n in groups:
                    out.append(groups[n])
                else:
                    out.append(self.node(n, "boundary" if n in boundaries else "element", p, with_children))
                walk(n)

        walk(None)
        return out

    # --- edges ---------------------------------------------------------------------

    def edge_lines(self, rel_ids: list[str], size: float) -> list[Json]:
        if len(rel_ids) > 1:
            return [{"text": f"{len(rel_ids)} relationships", "tier": 0, "size": rnd(size)}]
        r = self.idx.rel[rel_ids[0]]
        out: list[Json] = []
        if r["description"]:
            out.append({"text": r["description"], "tier": 0, "size": rnd(size)})
        if r["technology"]:
            out.append({"text": f"[{r['technology']}]", "tier": 1, "size": rnd(size - 1)})
        return out

    def edge(self, id_: str, source: Any, target: Any, rel_ids: list[str], order: Optional[str] = None) -> Json:
        rel_ids = sorted(set(rel_ids))
        style = self.styles.merged_edge([self.idx.rel[r]["tags"] for r in rel_ids])
        e: Json = {"id": id_, "source": source, "target": target, "rels": rel_ids, "style": style,
                   "lines": self.edge_lines(rel_ids, float(style.get("fontSize", 12)))}
        if order is not None:
            e["order"] = order
        return e

    def lift(self, path: str, nodes: set[str]) -> Optional[str]:
        for a in self.anc(path):
            if a in nodes:
                return a
        return None

    def rolled_edges(self, nodes: set[str]) -> dict[tuple[str, str], list[str]]:
        groups: dict[tuple[str, str], list[str]] = {}
        for r in self.model["relationships"]:
            a, b = self.lift(r["source"], nodes), self.lift(r["destination"], nodes)
            if a is not None and b is not None and a != b:
                groups.setdefault((a, b), []).append(r["id"])
        return groups

    # --- levels --------------------------------------------------------------------

    def level(self, key: str, kind: str, scope: Optional[str], title: str, ports: list[Json],
              nodes: list[Json], edges: list[Json]) -> Json:
        return {"key": key, "level": {"kind": kind, "scope": scope}, "title": title,
                "ports": sorted(ports, key=lambda p: p["id"]),
                "nodes": nodes, "edges": sorted(edges, key=lambda e: e["id"])}

    def element_level(self, key: str, kind: str, scope: Optional[str], title: str, roots: list[str],
                      parent_edges: list[Json]) -> Json:
        nodes = sorted(roots)
        nodeset = set(nodes)
        edges = [self.edge(f"{a}->{b}", a, b, rels) for (a, b), rels in self.rolled_edges(nodeset).items()]
        ports: list[Json] = []
        if scope is not None:
            for pe in parent_edges:
                if pe["target"] == scope:
                    direction, inner_of = "in", lambda r: self.idx.rel[r]["destination"]
                elif pe["source"] == scope:
                    direction, inner_of = "out", lambda r: self.idx.rel[r]["source"]
                else:
                    continue
                pid = pe["id"]
                ports.append({"id": pid, "dir": direction})
                by_child: dict[str, list[str]] = {}
                for rid in pe["rels"]:
                    inner = inner_of(rid)
                    if inner == scope:
                        continue  # declared on the scope itself: does not continue inside
                    child = self.lift(inner, nodeset)
                    if child is not None:
                        by_child.setdefault(child, []).append(rid)
                for child, rels in by_child.items():
                    if direction == "in":
                        edges.append(self.edge(f"port:{pid}->{child}", {"port": pid}, child, rels))
                    else:
                        edges.append(self.edge(f"{child}->port:{pid}", child, {"port": pid}, rels))
        return self.level(key, kind, scope, title, ports,
                          self.arrange({n: None for n in nodes}, set(), True), edges)

    def explicit_id(self, structurizr_id: str) -> Optional[str]:
        """Model relationship id of a Structurizr relationship (following implied -> explicit)."""
        seen = 0
        cur: Optional[str] = structurizr_id
        while cur is not None and seen < 16:
            if cur in self.idx.rel_by_model_id:
                return str(self.idx.rel_by_model_id[cur])
            raw = self.raw_rels.get(cur)
            cur = str(raw["linkedRelationshipId"]) if raw and raw.get("linkedRelationshipId") else None
            seen += 1
        return None

    def view_level(self, mv: Json, sv: Json) -> Json:
        idx = self.idx
        members = [e["id"] for e in self.model["elements"]
                   if mv["key"] in e["views"] and e["type"] in DRAWN_TYPES]
        scope = mv["scope"]
        parent_of: dict[str, Optional[str]] = {m: None for m in members}
        if scope is not None and mv["kind"] in ("container", "component", "dynamic"):
            kids = [m for m in members if idx.el[m]["parent"] == scope]
            if kids:
                for m in kids:
                    parent_of[m] = scope
                parent_of.setdefault(scope, None)
        nodeset = set(parent_of)
        nodes = self.arrange(parent_of, {p for p in parent_of.values() if p is not None}, False)
        edges: list[Json] = []
        groups: dict[tuple[str, str], list[str]] = {}
        for rv in sv.get("relationships", []):
            raw = self.raw_rels.get(str(rv.get("id")))
            rid = self.explicit_id(str(rv.get("id")))
            if raw is None or rid is None:
                continue
            a, b = idx.by_model_id.get(str(raw["sourceId"])), idx.by_model_id.get(str(raw["destinationId"]))
            if a not in nodeset or b not in nodeset or a is None or b is None:
                continue
            if mv["kind"] == "dynamic":
                order = str(rv.get("order", ""))
                step = self.edge(f"{a}->{b}#{order}", a, b, [rid], order=order)
                if rv.get("description"):
                    step["lines"] = [{"text": f"{order}: {rv['description']}", "tier": 0,
                                      "size": step["lines"][0]["size"] if step["lines"] else 12}]
                edges.append(step)
            else:
                groups.setdefault((a, b), []).append(rid)
        edges += [self.edge(f"{a}->{b}", a, b, rels) for (a, b), rels in groups.items()]
        return self.level(mv["scene"], "view", mv["key"], mv["title"], [], nodes, edges)


def build_levels(workspace: Any, model: Json, text_color: str = "wcag") -> Json:
    """Return the ``buildzr.levels/2`` object for ``workspace`` and its exported ``model``.

    Args:
        workspace: A buildzr DSL ``Workspace`` (or its Structurizr JSON as a dict).
        model: The result of :func:`buildzr.site.model.export_model` for the same workspace.
        text_color: ``"wcag"`` picks black or white text by contrast with the fill unless a
            style sets a colour; ``"c4"`` keeps the C4 default text colours.

    Returns:
        The level graphs as a plain dict; write it with :func:`buildzr.site.canonical.dumps`.
    """
    ws = workspace_json(workspace)
    b = _Builder(ws, model, text_color)
    levels: list[Json] = []
    landscape = b.element_level("landscape", "landscape", None, model["workspace"]["name"],
                            [r for r in b.idx.roots if b.idx.el[r]["type"] in DRAWN_TYPES], [])
    levels.append(landscape)
    by_key: dict[str, Json] = {"landscape": landscape}
    for el in model["elements"]:
        if not el["children"]:
            continue
        parent = el["parent"]
        parent_key = f"e/{parent}" if parent else "landscape"
        lv = b.element_level(f"e/{el['id']}", "element", el["id"], el["name"], el["children"],
                             by_key[parent_key]["edges"])
        levels.append(lv)
        by_key[lv["key"]] = lv
    raw_views: dict[tuple[str, str], Json] = {}
    for list_name, kind in VIEW_KINDS:
        for v in ws.get("views", {}).get(list_name, []):
            raw_views.setdefault((kind, v.get("key", "")), v)
    for mv in model["views"]:
        sv = raw_views.get((mv["kind"], mv["viewKey"]), {})
        levels.append(b.view_level(mv, sv))
    return {"schema": LEVELS_SCHEMA, "modelHash": model["modelHash"], "levels": levels}
