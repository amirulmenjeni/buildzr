import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SampleComponentView(AbstractBuilder):

    """
    An example of a component view, as seen in
    https://docs.structurizr.com/dsl/cookbook/component-view/.
    """

    def build(self) -> buildzr.models.Workspace:
        with Workspace('workspace') as w:
            user = Person('User')
            with SoftwareSystem("Software System") as ss:
                with Container("Web Application") as web_app:
                    c1 = Component("Component 1")
                    c2 = Component("Component 2")
                    c1 >> "Uses" >> c2
                db = Container("Database")
                web_app.component_2 >> "Reads from and writes to" >> db
            user >> "Uses" >> c1
            w.apply_views(
                ComponentView(
                    container_selector=lambda w: w.software_system().software_system.web_application,
                    key="web_application_container_00",
                    description="Component View Test",
                )
            )
        return w.model