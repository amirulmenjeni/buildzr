import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class NestedGroups(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace("w", scope='landscape', group_separator="/") as w:
            with Group("Company 1") as company1:
                with Group("Department 1"):
                    a = SoftwareSystem("A")
                with Group("Department 2") as c1d2:
                    b = SoftwareSystem("B")
            with Group("Company 2") as company2:
                with Group("Department 1"):
                    c = SoftwareSystem("C")
                with Group("Department 2") as c2d2:
                    d = SoftwareSystem("D")
            a >> b
            c >> d
            b >> c

            # TODO: Ensure multiple views work.

            SystemLandscapeView(
                key='nested-groups',
                description="Nested Groups Sample"
            )

            SystemContextView(
                software_system_selector=b,
                key='nested-groups-context',
                description="Nested Groups Sample Context",
                include_elements=[c, d],
            )

            StyleElements(
                on=[a, b],
                shape='Box',
            )

            StyleElements(
                on=[c, d],
                shape='RoundedBox',
            )

            StyleElements(
                on=[company1],
                stroke='yellow',
                border='dotted',
            )

            StyleElements(
                on=[c1d2, c2d2],
                color='green',
            )

        return w.model