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

# Type alias for all element types that can be explored
ElementType = Union[
    Person,
    SoftwareSystem,
    Container,
    Component,
    DeploymentNode,
    InfrastructureNode,
    SoftwareSystemInstance,
    ContainerInstance
]

class Explorer:

    def __init__(
        self,
        workspace_or_element: Union[
            Workspace,
            ElementType,
        ]
    ):
        self._workspace_or_element = workspace_or_element
        # Cache for walk results to avoid repeated traversals
        self._elements_cache: Optional[List[ElementType]] = None
        self._relationships_cache: Optional[List[DslRelationship]] = None

    def walk_elements(self) -> Generator[ElementType, None, None]:
        # Use cached result if available
        if self._elements_cache is not None:
            yield from self._elements_cache
            return
        
        # Build cache while yielding
        elements: List[ElementType] = []
        
        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:
                elements.append(child)
                yield child
                # Recursively walk child elements using helper
                for descendant in self._walk_elements_recursive(child):
                    elements.append(descendant)
                    yield descendant
        
        # Cache the results for future calls
        self._elements_cache = elements
    
    def _walk_elements_recursive(self, element: ElementType) -> Generator[ElementType, None, None]:
        """Helper method for recursive traversal without creating new Explorer instances."""
        if element.children:
            for child in element.children:
                yield child
                yield from self._walk_elements_recursive(child)

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

                # Recursively walk child relationships using helper
                for rel in self._walk_relationships_recursive(child):
                    relationships.append(rel)
                    yield rel
        
        # Cache the results for future calls
        self._relationships_cache = relationships
    
    def _walk_relationships_recursive(self, element: ElementType) -> Generator[DslRelationship, None, None]:
        """Helper method for recursive traversal without creating new Explorer instances."""
        if element.children:
            for child in element.children:
                if child.relationships:
                    for relationship in child.relationships:
                        yield cast(_Relationship, relationship)
                yield from self._walk_relationships_recursive(child)