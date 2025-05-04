import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class GroupsSample(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace("w", scope=None) as w:
            with Group("Company 1"):
                with SoftwareSystem("A") as a:
                    Container("a1")
                    Container("a2")
            with Group("Company 2"):
                with SoftwareSystem("B") as b:
                    Container("b1")
                    with Container("b2") as b2:
                        Component("c1")
            c = SoftwareSystem("C")
            a >> "Uses" >> b
            a.a1 >> "Uses" >> b.b1
            a >> "Uses" >> c
            w.apply_views(
                SystemLandscapeView(
                    key='groups-sample',
                    description="Groups Sample"
                ),
                SystemContextView(
                    key='groups-sample-a',
                    software_system_selector=lambda w: cast(SoftwareSystem, w.a),
                    description="Groups Sample - Software System A"
                ),
                SystemContextView(
                    key='groups-sample-b',
                    software_system_selector=lambda w: cast(SoftwareSystem, w.b),
                    description="Groups Sample - Software System B"
                ),
                ContainerView(
                    key='groups-sample-b2',
                    software_system_selector=lambda w: w.software_system().b,
                    description="Groups Sample - Container B2"
                ),
            )
        return w.model