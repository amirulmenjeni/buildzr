import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SampleComponentView(AbstractBuilder):

    """
    An example of a component view, as seen in
    https://docs.structurizr.com/dsl/cookbook/component-view/.
    """

    def build(self) -> buildzr.models.Workspace:

        w = Workspace('workspace')\
            .contains(
                Person('User'),
                SoftwareSystem("Software System")\
                .contains(
                    Container("Web Application")\
                    .contains(
                        Component("Component 1"),
                        Component("Component 2"),
                    )\
                    .where(lambda c1, c2: [
                        c1 >> "Uses" >> c2,
                    ]),
                    Container("Database"),
                )\
                .where(lambda web_application, database: [
                    web_application.component_2 >> "Reads from and writes to" >> database,
                ]),
            )\
            .where(lambda user, software_system: [
                user >> "Uses" >> software_system.web_application.component_1,
            ])\
            .with_views(
                ComponentView(
                    container_selector=lambda w: w.software_system().software_system.web_application,
                    key="web_application_container_00",
                    description="Component View Test",
                )
            )\
            .get_workspace()

        return w.model