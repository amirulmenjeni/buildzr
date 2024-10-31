import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class GroupsSample(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace("w", scope=None)\
            .contains(
                Group(
                    "Company 1",
                    SoftwareSystem("A")\
                    .contains(
                        Container("a1"),
                        Container("a2"),
                    )
                ),
                Group(
                    "Company 2",
                    SoftwareSystem("B")\
                    .contains(
                        Container("b1"),
                        Container("b2")
                        .contains(
                            Component("c1"),
                        )
                    )
                ),
                SoftwareSystem("C"),
            )\
            .where(lambda w: [
                w.software_system().a >> "Uses" >> w.software_system().b,
                w.software_system().a.container().a1 >> "Uses" >> w.software_system().b.container().b1,
                w.software_system().a >> "Uses" >> w.software_system().c,
            ])\
            .with_views(
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
            )\
            .get_workspace()

        return w.model