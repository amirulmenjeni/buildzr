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
        with Workspace('w') as w:
            user = Person('user')
            with SoftwareSystem('web_app') as web_app:
                Container('database')
                Container('api')
            email_system = SoftwareSystem('email_system')
            user >> "uses" >> web_app
            web_app >> "sends notification using" >> email_system
            w.apply_views(
                SystemContextView(
                    lambda w: w.software_system().web_app,
                    key='web_app_system_context_00',
                    description="Web App System Context",
                    exclude_elements=[
                        lambda w, e: w.person().user == e,
                    ]
                )
            )
        return w.model