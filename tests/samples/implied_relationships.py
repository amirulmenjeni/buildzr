# Implied relationships example as shown in the Cookbook:
# https://docs.structurizr.com/dsl/cookbook/implied-relationships/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class ImpliedRelationships(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        return Workspace("Implied Relationships")\
               .contains(
                   Person("User"),
                   SoftwareSystem("Software System")\
                   .contains(
                       Container("Web Application")
                   )
                   .get(),
               )\
               .where(lambda u, s: [
                    u >> "Uses" >> s.web_application,
               ])\
               .model