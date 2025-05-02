# Implied relationships example as shown in the Cookbook:
# https://docs.structurizr.com/dsl/cookbook/implied-relationships/

import buildzr
from buildzr.dsl import *
from typing import cast
from ..abstract_builder import AbstractBuilder

class SampleImpliedRelationships(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace("w", implied_relationships=True) as w:
            u = Person("u")
            with SoftwareSystem("s") as s:
                with Container("webapp") as webapp:
                    db_layer = Component("database layer")
                    api_layer = Component("API layer")
                    ui_layer = Component("UI layer")
                    ui_layer >> ("Calls HTTP API from", "http/api") >> api_layer
                    api_layer >> ("Runs queries from", "sql/sqlite") >> db_layer
                database = Container("database")
                ui_layer >> "Uses" >> database
            u >> "Runs SQL queries" >> database
            w.apply_views(
                SystemContextView(
                    key='sample-implied-relationships',
                    software_system_selector=lambda w: cast(SoftwareSystem, w.s),
                    description="Sample Implied Relationships"
                )
            )
        return w.model