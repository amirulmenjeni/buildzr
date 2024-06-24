# A simple example as shown in https://docs.structurizr.com/dsl/example.

from buildzr.encoders import *
from buildzr.models import *
from buildzr.models import Workspace
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> Workspace:

        workspace = Workspace(
            id=0,
            name='engineering',
            description='engineering apps landscape',
        )

        u = Person(
            id=0,
            name="User"
        )

        ss = SoftwareSystem(
            id=0,
            name='Software System'
        )

        workspace.models.extend([u, ss])

        r0 = Relationship(
            id=0,
            description="Uses",
            source_id=u.id,
            destination_id=ss.id
        )

        u.relationships.append(r0)
        ss.relationships.append(r0)

        return workspace