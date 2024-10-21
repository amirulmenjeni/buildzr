# Implied relationships example as shown in the Cookbook:
# https://docs.structurizr.com/dsl/cookbook/implied-relationships/

import buildzr
from buildzr.dsl import *
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
                                .where(lambda db, api, ui: [
                                    ui >> ("Calls HTTP API from", "http/api") >> api,
                                    api >> ("Runs queries from", "sql/sqlite") >> db,
                                ]),\
                            Container("database"),
                        )\
                        .where(lambda webapp, database: [
                            webapp >> "Uses" >> database
                        ], implied=True)
                )\
                .where(lambda u, s: [
                    u >> "Runs SQL queries" >> s.database,
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