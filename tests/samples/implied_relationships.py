# Implied relationships example as shown in the Cookbook:
# https://docs.structurizr.com/dsl/cookbook/implied-relationships/

import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class SampleImpliedRelationships(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace("w")\
                .contains(
                    Person("u"),
                    SoftwareSystem("s")\
                        .contains(
                            Container("webapp")\
                                .contains(
                                    Component("database layer"),
                                    Component("API layer"),
                                    Component("UI layer"),
                                )\
                                .where(lambda webapp: [
                                    webapp.ui_layer >> ("Calls HTTP API from", "http/api") >> webapp.api_layer,
                                    webapp.api_layer >> ("Runs queries from", "sql/sqlite") >> webapp.database_layer,
                                ]),\
                            Container("database"),
                        )\
                        .where(lambda s: [
                            s.webapp >> "Uses" >> s.database
                        ], implied=True)
                )\
                .where(lambda w: [
                    w.person().u >> "Runs SQL queries" >> w.software_system().s.database,
                ], implied=True)\
                .with_views(
                    SystemContextView(
                        key='sample-implied-relationships',
                        software_system_selector=lambda w: cast(SoftwareSystem, w.s),
                        description="Sample Implied Relationships"
                    )
                )\
                .get_workspace()

        return w.model