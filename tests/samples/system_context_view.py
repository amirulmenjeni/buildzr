import buildzr
from buildzr.dsl import (
    Workspace,
    SoftwareSystem,
    Person,
    Container,
    SystemContextView,
)
from ..abstract_builder import AbstractBuilder

class SystemContextViewSample(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace('w')\
                .contains(
                    Person('user'),
                    SoftwareSystem('web_app')
                        .contains(
                            Container('database'),
                            Container('api'),
                        ),
                    SoftwareSystem('email_system'),
                )\
                .where(lambda w: [
                    w.person().user >> "uses" >> w.software_system().web_app,
                    w.software_system().web_app >> "sends notification using" >> w.software_system().email_system,
                ])\
                .with_views(
                    SystemContextView(
                        lambda w: w.software_system().web_app,
                        key='web_app_system_context_00',
                        description="Web App System Context",
                        exclude_elements=[
                            lambda w, e: w.person().user == e,
                        ]
                    )
                )\
                .get_workspace()

        return w.model