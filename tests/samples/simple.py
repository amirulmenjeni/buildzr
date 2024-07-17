# A simple example as shown in https://docs.structurizr.com/dsl/example.

from buildzr.encoders import *
from buildzr.models import *
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> Workspace:

        workspace_config = WorkspaceConfiguration(
            scope=Scope.Landscape
        )

        u = Person(
            id=str(1),
            name="User"
        )

        ss = SoftwareSystem(
            id=str(2),
            name='Software System'
        )

        r0 = Relationship(
            id=str(3),
            description="Uses",
            sourceId=u.id,
            destinationId=ss.id
        )

        # Note that in `r0`, `u` is the source element.
        u.relationships = [r0]

        workspace = Workspace(
            id=0,
            name='engineering',
            description='engineering apps landscape',
            model=Model(
                people=[u],
                softwareSystems=[ss]
            ),
            configuration=workspace_config
        )

        return workspace