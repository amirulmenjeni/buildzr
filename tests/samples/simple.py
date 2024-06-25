# A simple example as shown in https://docs.structurizr.com/dsl/example.

from buildzr.encoders import *
from buildzr.models import *
from buildzr.models import Workspace
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> Workspace:

        u = Person(
            id=1,
            name="User"
        )

        ss = SoftwareSystem(
            id=2,
            name='Software System'
        )

        r0 = Relationship(
            id=3,
            description="Uses",
            source_id=u.id,
            destination_id=ss.id
        )

        # Note that in `r0`, `u` is the source element.
        u.relationships.append(r0)

        workspace = Workspace(
            id=0,
            name='engineering',
            description='engineering apps landscape',
            model=Model(
                people=[u],
                softwareSystems=[ss]
            )
        )

        return workspace