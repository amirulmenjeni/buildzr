# Container view example shown in the cookbook:
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SampleContainerView(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace('w', scope=None)\
                .contains(
                    Person('u'),
                    SoftwareSystem('email_system')\
                        .contains(
                            Container('email_c1'),
                            Container('email_c2'),
                        )\
                        .where(lambda c1, c2: [
                            c1 >> "Uses" >> c2,
                        ]),
                    SoftwareSystem('business_app')
                        .contains(
                            Container('business_app_c1'),
                            Container('business_app_c2'),
                        )
                        .where(lambda c1, c2: [
                            c1 >> "Gets data from" >> c2,
                        ]),
                    SoftwareSystem('git_repo'), # Unrelated!
                    SoftwareSystem('external_system'), # Also unrelated!
                )\
                .where(lambda u, email_system, business_app, git_repo, external_system: [
                    u >> "Uses" >> business_app,
                    u >> "Hacks" >> git_repo,
                    business_app >> "Notifies users using" >> email_system,
                    git_repo >> "Uses" >> external_system,
                ])\
                .with_views(
                    ContainerView(
                        software_system_selector=lambda w: w.software_system().business_app,
                        key="ss_business_app",
                        description="The business app",
                    )
                )\
                .get_workspace()

        return w.model