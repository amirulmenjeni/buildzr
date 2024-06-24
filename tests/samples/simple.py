# A simple example as shown in https://docs.structurizr.com/dsl/example.

from buildzr.encoders import *
from buildzr.models import *
from buildzr.models import Workspace
from ..abstract_builder import AbstractBuilder

class Simple(AbstractBuilder):

    def build(self) -> Workspace:

        workspace = Workspace(
            name='engineering',
            description='engineering apps landscape',
        )

        u = Person(
            name="User"
        )

        ss = SoftwareSystem(
            name='Software System'
        )

        workspace.models.extend([u, ss])

        r0 = Relationship(
            description="Uses",
            source_id=u.id,
            destination_id=ss.id
        )

        u.relationships.append(r0)
        ss.relationships.append(r0)

        return workspace