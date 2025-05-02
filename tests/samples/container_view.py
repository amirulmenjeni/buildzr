# Container view example shown in the cookbook (with a bit of modifications):
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SampleContainerView(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace('w', scope=None) as w:
            user = Person('user')
            with SoftwareSystem('app') as app:
                web_application = Container('web_application')
                database = Container('database')
                web_application >> "Reads from and writes to" >> database
            git_repo = SoftwareSystem('git_repo')  # Unrelated!
            external_system = SoftwareSystem('external_system')  # Also unrelated!
            user >> "Uses" >> web_application
            user >> "Hacks" >> git_repo
            git_repo >> "Uses" >> external_system
            w.apply_views(
                ContainerView(
                    software_system_selector=lambda w: w.software_system().app,
                    key="ss_business_app",
                    description="The business app",
                )
            )
        return w.model