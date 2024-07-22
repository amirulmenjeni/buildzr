# Container view example shown in the cookbook:
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        workspace = Workspace("My workspace")

        u = Person("User")
        s = SoftwareSystem("Software System")
        workspace.contains([u, s])

        webapp = Container("Web Application")
        database = Container("Database")
        s.contains([webapp, database])

        u >> "Uses" >> webapp
        webapp >> "Reads and writes to" >> database

        return workspace.model