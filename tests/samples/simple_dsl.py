# A simple example as shown in https://docs.structurizr.com/dsl/example.

from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> Workspace:

        workspace = Workspace("My workspace")
        user = Person("A user")
        software_system = SoftwareSystem("A software system")

        workspace.contains([user, software_system])

        user >> ("Uses", "CLI") >> software_system

        return workspace