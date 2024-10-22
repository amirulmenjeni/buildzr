# Container view example shown in the cookbook (with a bit of modifications):
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SampleContainerView(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace('w', scope=None)\
                .contains(
                    Person('user'),
                    SoftwareSystem('app')
                        .contains(
                            Container('web_application'),
                            Container('database'),
                        )
                        .where(lambda app: [
                            app.web_application >> "Reads from and writes to" >> app.database,
                        ]),
                    SoftwareSystem('git_repo'), # Unrelated!
                    SoftwareSystem('external_system'), # Also unrelated!
                )\
                .where(lambda w: [
                    w.user >> "Uses" >> w.software_system().app.web_application,
                    w.user >> "Hacks" >> w.git_repo,
                    w.git_repo >> "Uses" >> w.external_system,
                ])\
                .with_views(
                    ContainerView(
                        software_system_selector=lambda w: w.software_system().app,
                        key="ss_business_app",
                        description="The business app",
                    )
                )\
                .get_workspace()

        return w.model