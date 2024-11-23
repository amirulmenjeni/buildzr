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

    w = (
        Workspace("w")
        .contains(
            Person("p1"),
            Person("p2"),
            Person("p3"),
            Person("p4"),
        )
        .where(lambda w: [
            w.person().p1 >> "greet" >> w.person().p2,
            w.person().p1 >> [
                w.person().p3,
                desc("greet") >> w.person().p4,
            ]
        ])
    )

def test_relationship_typehint_person_to_software_system() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            Person("p"),
            SoftwareSystem("s1"),
            SoftwareSystem("s2"),
            SoftwareSystem("s3"),
            SoftwareSystem("s4"),
        )
        .where(lambda w: [
            w.person().p >> "use" >> w.software_system().s1,
            w.person().p >> [
                w.software_system().s2,
                desc("use") >> w.software_system().s3,
                desc("use") >> w.software_system().s4,
            ]
        ])
    )

def test_relationship_typehint_person_to_container() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            Person('p'),
            SoftwareSystem('s')
            .contains(
                Container('c1'),
                Container('c2'),
                Container('c3'),
                Container('c4'),
            )
        )
        .where(lambda w: [
            w.person().p >> "use" >> w.software_system().s.container().c1,
            w.person().p >> [
                w.software_system().s.container().c2,
                desc("use") >> w.software_system().s.container().c3,
                desc("use") >> w.software_system().s.container().c4,
            ]
        ])
    )

def test_relationship_typehint_person_to_component() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            Person('p'),
            SoftwareSystem('s')
            .contains(
                Container('c')
                .contains(
                    Component('c1'),
                    Component('c2'),
                    Component('c3'),
                    Component('c4'),
                )
            )
        )
        .where(lambda w: [
            w.person().p >> "use" >> w.software_system().s.container().c.component().c1,
            w.person().p >> [
                w.software_system().s.container().c.component().c2,
                desc("use") >> w.software_system().s.container().c.component().c3,
                desc("use") >> w.software_system().s.container().c.component().c4,
            ]
        ])
    )

def test_relationship_typehint_software_system_to_software_system() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem("s1"),
            SoftwareSystem("s2"),
            SoftwareSystem("s3"),
            SoftwareSystem("s4"),
        )
        .where(lambda w: [
            w.software_system().s1 >> "integrate" >> w.software_system().s2,
            w.software_system().s1 >> [
                w.software_system().s3,
                desc("integrate") >> w.software_system().s4,
            ]
        ])
    )

def test_relationship_typehint_software_system_to_container() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem('s1'),
            SoftwareSystem('s2')
            .contains(
                Container('c1'),
                Container('c2'),
                Container('c3'),
                Container('c4'),
            )
        )
        .where(lambda w: [
            w.software_system().s1 >> "use" >> w.software_system().s2.container().c1,
            w.software_system().s1 >> [
                w.software_system().s2.container().c2,
                desc("use") >> w.software_system().s2.container().c3,
                desc("use") >> w.software_system().s2.container().c4,
            ]
        ])
    )

def test_relationship_typehint_software_system_to_component() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem('s1'),
            SoftwareSystem('s2')
            .contains(
                Container('c')
                .contains(
                    Component('c1'),
                    Component('c2'),
                    Component('c3'),
                    Component('c4'),
                )
            )
        )
        .where(lambda w: [
            w.software_system().s1 >> "use" >> w.software_system().s2.container().c.component().c1,
            w.software_system().s1 >> [
                w.software_system().s2.container().c.component().c2,
                desc("use") >> w.software_system().s2.container().c.component().c3,
                desc("use") >> w.software_system().s2.container().c.component().c4,
            ]
        ])
    )

def test_relationship_typehint_container_to_container() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem('s')
            .contains(
                Container('c1'),
                Container('c2'),
                Container('c3'),
                Container('c4'),
            )
        )
        .where(lambda w: [
            w.software_system().s.container().c1 >> "call" >> w.software_system().s.container().c2,
            w.software_system().s.container().c1 >> [
                w.software_system().s.container().c3,
                desc("call") >> w.software_system().s.container().c4,
            ]
        ])
    )

def test_relationship_typehint_container_to_component() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem('s')
            .contains(
                Container('c1'),
                Container('c2')
                .contains(
                    Component('c1'),
                    Component('c2'),
                    Component('c3'),
                    Component('c4'),
                )
            )
        )
        .where(lambda w: [
            w.software_system().s.container().c1 >> "call" >> w.software_system().s.container().c2.component().c1,
            w.software_system().s.container().c1 >> [
                w.software_system().s.container().c2.component().c2,
                desc("call") >> w.software_system().s.container().c2.component().c3,
                desc("call") >> w.software_system().s.container().c2.component().c4,
            ]
        ])
    )

def test_relationship_typehint_component_to_component() -> Optional[None]:

    w = (
        Workspace("w")
        .contains(
            SoftwareSystem('s')
            .contains(
                Container('c')
                .contains(
                    Component('c1'),
                    Component('c2'),
                    Component('c3'),
                    Component('c4'),
                )
            )
        )
        .where(lambda w: [
            w.software_system().s.container().c.component().c1 >> "call" >> w.software_system().s.container().c.component().c2,
            w.software_system().s.container().c.component().c1 >> [
                w.software_system().s.container().c.component().c3,
                desc("call") >> w.software_system().s.container().c.component().c4,
            ]
        ])
    )
