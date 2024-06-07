from models import *

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