import os
import subprocess
import sys
import textwrap

from buildzr.dsl import (
    Container,
    DeploymentEnvironment,
    DeploymentNode,
    Person,
    SoftwareSystem,
    With,
    Workspace,
)
from buildzr.dsl.relations import OrderedSet


def test_with_constructs() -> None:
    w = With(tags={"a"}, properties={"k": "v"}, url="https://example.com")
    assert w.tags == {"a"}
    assert w.properties == {"k": "v"}
    assert w.url == "https://example.com"
    assert With() == With(tags=None, properties=None, url=None)


def test_with_tags_applied_to_relationship() -> None:
    with Workspace("w"):
        a = Person("A")
        b = SoftwareSystem("B")
        rel = a >> "uses" >> b | With(tags={"y", "x"})
    assert rel.model.tags == "Relationship,x,y"


def test_plain_set_input_is_sorted_and_list_order_kept() -> None:
    with Workspace("w"):
        p = Person("P", tags={"c", "a", "b"})
    assert p.model.tags == "Element,Person,a,b,c"
    s = OrderedSet(["z", "m", "a"])
    assert ",".join(s) == "z,m,a"


def test_default_tags_come_first() -> None:
    with Workspace("w") as w:
        user = Person("User", tags={"zeta", "alpha"})
        system = SoftwareSystem("System")
        with system:
            container = Container("Web", tags={"b", "a"})
        with DeploymentEnvironment("Live"):
            node = DeploymentNode("Server")
        rel = (user >> ("uses", "HTTP") >> container | With(tags={"y", "x"}))

    assert user.model.tags == "Element,Person,alpha,zeta"
    assert system.model.tags == "Element,Software System"
    assert container.model.tags == "Element,Container,a,b"
    assert node.model.tags == "Element,Deployment Node"
    assert rel.model.tags is not None
    assert rel.model.tags.split(",")[0] == "Relationship"
    assert rel.model.tags == "Relationship,x,y"


def test_add_tags_appends() -> None:
    with Workspace("w"):
        p = Person("User")
        p.add_tags("late", "later")
    assert p.model.tags == "Element,Person,late,later"


_SCRIPT = textwrap.dedent(
    """
    from buildzr.dsl import (
        Workspace, Person, SoftwareSystem, Container, SystemContextView,
        ContainerView, DeploymentEnvironment, DeploymentNode, With,
    )
    with Workspace("w") as w:
        u = Person("User", tags={"t1", "t2", "t3"})
        s = SoftwareSystem("S")
        with s:
            a = Container("A")
            b = Container("B")
        with DeploymentEnvironment("Live"):
            DeploymentNode("N")
        u >> "uses" >> a
        a >> ("calls", "gRPC") >> b | With(tags={"r1", "r2"})
        SystemContextView(s, "ctx", "d")
        ContainerView(s, "cont", "d")
    print(w.to_json())
    """
)


def _build(seed: int) -> str:
    env = dict(os.environ, PYTHONHASHSEED=str(seed))
    p = subprocess.run(
        [sys.executable, "-I", "-c", _SCRIPT],
        env=env, capture_output=True, text=True, check=True,
    )
    return p.stdout


def test_to_json_identical_across_hash_seeds() -> None:
    first = _build(1)
    assert '"Element,Person' in first
    assert first == _build(2)
    assert first == _build(3)


def test_ordered_set_operators_keep_left_order() -> None:
    a = OrderedSet(["c", "a", "b"])
    b = {"b", "z", "c"}
    assert list(a | b) == ["c", "a", "b", "z"]
    assert list(a & b) == ["c", "b"]
    assert list(a - b) == ["a"]
    assert list(a ^ b) == ["a", "z"]
    assert list(a.union(["q"], ["p"])) == ["c", "a", "b", "q", "p"]
    assert list(a.intersection(b)) == ["c", "b"]
    assert list(a.difference(b)) == ["a"]
    assert list(a.symmetric_difference(b)) == ["a", "z"]
    for res in (a | b, a & b, a - b, a ^ b):
        assert isinstance(res, OrderedSet)
    assert a == {"a", "b", "c"}
    # Reflected operators: the plain-set operand is on the left.
    assert isinstance(b | a, OrderedSet) and isinstance(b - a, OrderedSet)
    assert list(OrderedSet(["x", "y"]) | OrderedSet(["y", "w"])) == ["x", "y", "w"]


def test_ordered_set_inplace_operators() -> None:
    s = OrderedSet(["c", "a", "b"])
    s &= {"b", "c"}
    assert list(s) == ["c", "b"]
    s |= {"q"}
    assert list(s) == ["c", "b", "q"]
    s -= {"b"}
    assert list(s) == ["c", "q"]
    s ^= {"q", "k"}
    assert list(s) == ["c", "k"]
    assert s == {"c", "k"}
    s.add("c")
    s.discard("c")
    s.add("c")
    assert list(s) == ["k", "c"]
