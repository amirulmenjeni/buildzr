"""Synthetic buildzr workspaces of three sizes for the v4 build.

Port of ``synthetic`` from the v4 zoom experiments (``spike/v4zoom/zoom_exp.py``),
with the same parameters and RNG call order, but producing a real DSL
:class:`~buildzr.dsl.Workspace` (``Person``/``SoftwareSystem``/``Container``/
``Component`` and ``>>`` relationships) plus one landscape, one container and one
component view. Everything is deterministic: names come from counters and all
randomness comes from ``random.Random(seed)``.
"""

from __future__ import annotations

import random
from typing import Optional

from buildzr.dsl import (
    Component,
    ComponentView,
    Container,
    ContainerView,
    Person,
    SoftwareSystem,
    SystemLandscapeView,
    Workspace,
)

#: ``size -> (people, systems, fraction of systems with containers)``, as in the spike.
SIZES: dict[str, tuple[int, int, float]] = {
    "S": (3, 6, 0.67),
    "M": (6, 15, 0.67),
    "L": (12, 40, 0.7),
}

_VERBS = ["Uses", "Reads from", "Writes to", "Calls", "Notifies", "Syncs with"]
_TECH = ["HTTPS", "gRPC", "SQL", "AMQP", "JSON/HTTPS"]


class _Plan:
    """The element tree and relationship pairs, by synthetic id (``p0``, ``s1c2k3``)."""

    def __init__(self) -> None:
        self.parent: dict[str, Optional[str]] = {}
        self.kind: dict[str, str] = {}
        self.order: list[str] = []
        self.rels: list[tuple[str, str]] = []

    def add(self, id_: str, kind: str, parent: Optional[str]) -> str:
        self.parent[id_] = parent
        self.kind[id_] = kind
        self.order.append(id_)
        return id_

    def children(self, id_: Optional[str]) -> list[str]:
        return [i for i in self.order if self.parent[i] == id_]


def _plan(n_people: int, n_sys: int, internal_frac: float, seed: int) -> _Plan:
    """Same structure and RNG call order as the spike's ``synthetic``."""
    r = random.Random(seed)
    m = _Plan()
    people = [m.add(f"p{i}", "Person", None) for i in range(n_people)]
    systems = [m.add(f"s{i}", "SoftwareSystem", None) for i in range(n_sys)]
    internal = systems[: max(1, int(n_sys * internal_frac))]
    leaves_by_sys: dict[str, list[str]] = {}
    for s in internal:
        conts = [m.add(f"{s}c{j}", "Container", s) for j in range(r.randint(2, 8))]
        lv: list[str] = []
        for c in conts:
            comps = ([m.add(f"{c}k{k}", "Component", c) for k in range(r.randint(3, 7))]
                     if r.random() < 0.4 else [])
            for k in comps:  # intra-container component edges
                for _ in range(r.choice([0, 1, 1, 2])):
                    o = r.choice(comps)
                    if o != k:
                        m.rels.append((k, o))
            lv += comps or [c]
        for c in conts:  # intra-system edges, between leaves
            for _ in range(r.choice([1, 1, 2])):
                a, b = r.choice([x for x in lv if x.startswith(c)] or [c]), r.choice(lv)
                if not b.startswith(c):
                    m.rels.append((a, b))
        leaves_by_sys[s] = lv
    for s in internal:  # cross-system edges
        for _ in range(r.randint(2, 4)):
            t = r.choice([x for x in systems if x != s])
            m.rels.append((r.choice(leaves_by_sys[s]), r.choice(leaves_by_sys.get(t, [t]))))
    for p in people:
        for _ in range(r.randint(1, 3)):
            s = r.choice(internal)
            m.rels.append((p, r.choice([x for x in leaves_by_sys[s] if m.kind[x] == "Container"]
                                       or leaves_by_sys[s])))
    m.rels = sorted(set(m.rels))
    if not any(k == "Component" for k in m.kind.values()):
        # Guarantee a component view: two components under the first internal container.
        c0 = f"{internal[0]}c0"
        k0, k1 = m.add(f"{c0}k0", "Component", c0), m.add(f"{c0}k1", "Component", c0)
        m.rels = sorted({*m.rels, (k0, k1)})
    return m


def _name(id_: str, kind: str) -> str:
    if kind == "Person":
        return f"Person {id_[1:]}"
    if kind == "SoftwareSystem":
        return f"System {id_[1:]}"
    if kind == "Container":
        s, c = id_[1:].split("c")
        return f"System {s} Container {c}"
    s, rest = id_[1:].split("c")
    c, k = rest.split("k")
    return f"System {s} Container {c} Component {k}"


def synthetic(size: str = "S", seed: int = 7) -> Workspace:
    """Build the synthetic workspace ``size`` ("S", "M" or "L").

    Args:
        size: One of ``SIZES``: S has 3 people and 6 systems, M 6 and 15, L 12 and 40
            (about two thirds of the systems have containers, some of those components).
        seed: RNG seed; the same seed always gives the same workspace.

    Returns:
        A :class:`Workspace` with mixed-level relationships (component to component,
        container to container, cross-system, person to container), one system
        landscape view, one container view and one component view.
    """
    n_people, n_sys, frac = SIZES[size]
    plan = _plan(n_people, n_sys, frac, seed)
    objs: dict[str, object] = {}
    with Workspace(f"Synthetic {size}", description=f"Synthetic workspace, size {size}.",
                   scope=None) as w:
        for pid in plan.children(None):
            kind = plan.kind[pid]
            if kind == "Person":
                objs[pid] = Person(_name(pid, kind), description=f"The {_name(pid, kind)}.")
        for sid in plan.children(None):
            if plan.kind[sid] != "SoftwareSystem":
                continue
            system = SoftwareSystem(_name(sid, "SoftwareSystem"),
                                    description=f"The {_name(sid, 'SoftwareSystem')}.")
            objs[sid] = system
            with system:
                for cid in plan.children(sid):
                    container = Container(_name(cid, "Container"), technology="Python",
                                          description=f"The {_name(cid, 'Container')}.")
                    objs[cid] = container
                    kids = plan.children(cid)
                    if kids:
                        with container:
                            for kid in kids:
                                objs[kid] = Component(_name(kid, "Component"), technology="Python",
                                                      description=f"The {_name(kid, 'Component')}.")
        for i, (a, b) in enumerate(plan.rels):
            src, dst = objs[a], objs[b]
            verb, tech = _VERBS[i % len(_VERBS)], _TECH[i % len(_TECH)]
            src >> (verb, tech) >> dst  # type: ignore[operator]

        first_sys = next(s for s in plan.children(None) if plan.children(s))
        first_comp_container = next(c for c in plan.order
                                    if plan.kind[c] == "Container" and plan.children(c))
        SystemLandscapeView(key="landscape", description="All people and systems.")
        ContainerView(objs[first_sys], key=f"containers-{first_sys}",  # type: ignore[arg-type]
                      description=f"Containers of {_name(first_sys, 'SoftwareSystem')}.")
        ComponentView(objs[first_comp_container], key=f"components-{first_comp_container}",  # type: ignore[arg-type]
                      description=f"Components of {_name(first_comp_container, 'Container')}.")
    return w
