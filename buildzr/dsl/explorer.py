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
    List,
    Optional,
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
        # Cache for walk results to avoid repeated traversals
        self._elements_cache: Optional[List[Union[
            Person,
            SoftwareSystem,
            Container,
            Component,
            DeploymentNode,
            InfrastructureNode,
            SoftwareSystemInstance,
            ContainerInstance
        ]]] = None
        self._relationships_cache: Optional[List[DslRelationship]] = None

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
        # Use cached result if available
        if self._elements_cache is not None:
            yield from self._elements_cache
            return
        
        # Build cache while yielding
        elements: List[Union[
            Person,
            SoftwareSystem,
            Container,
            Component,
            DeploymentNode,
            InfrastructureNode,
            SoftwareSystemInstance,
            ContainerInstance
        ]] = []
        
        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:
                elements.append(child)
                yield child
                # Recursively walk child elements
                for descendant in Explorer(child).walk_elements():
                    elements.append(descendant)
                    yield descendant
        
        # Cache the results for future calls
        self._elements_cache = elements

    def walk_relationships(self) -> Generator[DslRelationship, None, None]:
        # Use cached result if available
        if self._relationships_cache is not None:
            yield from self._relationships_cache
            return
        
        # Build cache while yielding
        relationships: List[DslRelationship] = []

        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:

                if child.relationships:
                    for relationship in child.relationships:
                        relationships.append(cast(_Relationship, relationship)) # TODO: Temporary fix. Use a better approach - Generics?
                        yield cast(_Relationship, relationship)

                # Recursively walk child relationships
                for rel in Explorer(child).walk_relationships():
                    relationships.append(rel)
                    yield rel
        
        # Cache the results for future calls
        self._relationships_cache = relationships