from buildzr.models import Workspace, Person, SoftwareSystem, Relationship

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

workspace.model.people.append(u)
workspace.model.softwareSystems.append(ss)

r0 = Relationship(
    description="Uses",
    sourceId=u.id,
    destinationId=ss.id
)