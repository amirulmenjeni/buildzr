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
                    SoftwareSystem('email'),
                )\
                .where(lambda user, web_app, _email: [
                    user >> "uses" >> web_app,
                ])\
                .with_views(
                    SystemContextView(
                        lambda w: w.software_system().web_app,
                        key='web_app_system_context_00',
                        description="Web App System Context",
                    )
                )\
                .get_workspace()

        return w.model