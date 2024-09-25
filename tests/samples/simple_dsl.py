# A simple example as shown in https://docs.structurizr.com/dsl/example.

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class SimpleDsl(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        workspace = Workspace("My workspace")
        user = Person("A user")
        software_system = SoftwareSystem("A software system")

        workspace.contains(user, software_system)

        user >> ("Uses", "CLI") >> software_system | With(
            tags={"linux", "rules"}
        )

        return workspace.model