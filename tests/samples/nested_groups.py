import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class NestedGroups(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace("w", scope='landscape', group_separator="/") as w:
            with Group("Company 1"):
                with Group("Department 1"):
                    a = SoftwareSystem("A")
                with Group("Department 2"):
                    b = SoftwareSystem("B")
            with Group("Company 2"):
                with Group("Department 1"):
                    c = SoftwareSystem("C")
                with Group("Department 2"):
                    d = SoftwareSystem("D")
            a >> b
            c >> d
            b >> c

            # TODO: Add styles applied to each group.
            SystemLandscapeView(
                key='nested-groups',
                description="Nested Groups Sample"
            )
        return w.model