# All tests in this file are to ensure that the typehints are correct.
# IMPORTANT: Run pytest with --mypy flag to check for typehint errors.

from typing import Optional
from buildzr.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    desc,
)

def test_relationship_typehint_person_to_person() -> Optional[None]:

    with Workspace("w") as w:
        p1 = Person("p1")
        p2 = Person("p2")
        p3 = Person("p3")
        p4 = Person("p4")

        # Define relationships
        p1 >> "greet" >> p2
        p1 >> [
            p3,
            desc("greet") >> p4
        ]

def test_relationship_typehint_person_to_software_system() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        s3 = SoftwareSystem("s3")
        s4 = SoftwareSystem("s4")

        # Define relationships
        p >> "use" >> s1
        p >> [
            s2,
            desc("use") >> s3,
            desc("use") >> s4
        ]

def test_relationship_typehint_person_to_container() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        p >> "use" >> c1
        p >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_person_to_component() -> Optional[None]:

    with Workspace("w") as w:
        p = Person("p")
        s = SoftwareSystem("s")
        with s:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        p >> "use" >> c1
        p >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_software_system_to_software_system() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        s3 = SoftwareSystem("s3")
        s4 = SoftwareSystem("s4")

        # Define relationships
        s1 >> "integrate" >> s2
        s1 >> [
            s3,
            desc("integrate") >> s4
        ]

def test_relationship_typehint_software_system_to_container() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        with s2:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        s1 >> "use" >> c1
        s1 >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_software_system_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s1 = SoftwareSystem("s1")
        s2 = SoftwareSystem("s2")
        with s2:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        s1 >> "use" >> c1
        s1 >> [
            c2,
            desc("use") >> c3,
            desc("use") >> c4
        ]

def test_relationship_typehint_container_to_container() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            c3 = Container("c3")
            c4 = Container("c4")

        # Define relationships
        c1 >> "call" >> c2
        c1 >> [
            c3,
            desc("call") >> c4
        ]

def test_relationship_typehint_container_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c1 = Container("c1")
            c2 = Container("c2")
            with c2:
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        c1 >> "call" >> c2.c3
        c1 >> [
            c2.c4,
            desc("call") >> c3,
            desc("call") >> c4
        ]

def test_relationship_typehint_component_to_component() -> Optional[None]:

    with Workspace("w") as w:
        s = SoftwareSystem("s")
        with s:
            c = Container("c")
            with c:
                c1 = Component("c1")
                c2 = Component("c2")
                c3 = Component("c3")
                c4 = Component("c4")

        # Define relationships
        c1 >> "call" >> c2
        c1 >> [
            c3,
            desc("call") >> c4
        ]