from typing import Self, Generic, TypeVar
from models.workspace import Workspace
from models.software_system import SoftwareSystem
from models.person import Person

class Fluent:

    S = TypeVar('S')
    D = TypeVar('D')

    class Workspace:
        
        counter = 0
        
        def __init__(self, name: str) -> None:
            self.data: Workspace = Workspace(
                id=f"workspace-{self.__class__.counter}",
                name=name,
                description='',
                models=[],
                version=''
            )
            self.__class__.counter += 1
        
        def with_description(self, description: str) -> 'Fluent.WorkspaceWriter':
            self.data.description = description
            return Fluent.WorkspaceWriter(self.data)

    class WorkspaceWriter:

        def __init__(self, workspace: Workspace) -> None:
            self.workspace = workspace
        
        def contains(self, model: SoftwareSystem | Person) -> Self:
            self.workspace.models.append(model)
            return self
        
        def where(self) -> 'Fluent.RelationshipWriter':
            return Fluent.RelationshipWriter(self.workspace)
    
    class RelationshipWriter(Generic[S, D]):

        def __init__(self, workspace: Workspace) -> None:
            self.workspace = workspace

Fluent\
    .Workspace('engineering')\
    .with_description('engineering apps landscape')\
    .contains(SoftwareSystem(
        name='app01',
    ))\
    .contains(Person(
        name='user01'
    ))