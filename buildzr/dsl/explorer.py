from buildzr.dsl.dsl import (
    Person,
    SoftwareSystem,
    Container,
    Component,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance,
)

from buildzr.dsl.relations import (
    _Relationship,
    _UsesData,
)

from typing import (
    Union,
    Generator,
    Iterable,
    cast,
)

from buildzr.dsl.dsl import (
    Workspace,
)

from buildzr.dsl.interfaces import (
    DslRelationship,
)

class Explorer:

    def __init__(
        self,
        workspace_or_element: Union[
            Workspace,
            Person,
            SoftwareSystem,
            Container,
            Component,
            DeploymentNode,
            InfrastructureNode,
            SoftwareSystemInstance,
            ContainerInstance,
        ]
    ):
        self._workspace_or_element = workspace_or_element

    def walk_elements(self) -> Generator[Union[
        Person,
        SoftwareSystem,
        Container,
        Component,
        DeploymentNode,
        InfrastructureNode,
        SoftwareSystemInstance,
        ContainerInstance
    ], None, None]:
        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:
                explorer = Explorer(child).walk_elements()
                yield child
                yield from explorer

    def walk_relationships(self) -> Generator[DslRelationship, None, None]:

        if self._workspace_or_element.children:

            for child in self._workspace_or_element.children:

                if child.relationships:
                    for relationship in child.relationships:
                        yield cast(_Relationship, relationship) # TODO: Temporary fix. Use a better approach - Generics?

                explorer = Explorer(child).walk_relationships()
                yield from explorer