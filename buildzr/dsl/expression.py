from buildzr.dsl.interfaces import (
    DslElement,
    DslRelationship,
)

from buildzr.dsl.dsl import (
    Workspace,
    Person,
    SoftwareSystem,
    Container,
    Component,
    _Relationship,
)

import buildzr
from typing import Set, Union, Optional, List, Dict, Any, Callable, Tuple, Sequence, Iterable
from typing_extensions import TypeIs

def _has_technology_attribute(obj: DslElement) -> TypeIs[Union[Container, Component]]:
    if isinstance(obj, (Person, SoftwareSystem, Workspace)):
        return False
    return True

class FlattenElement:

    def __init__(self, elements: Iterable[DslElement]):
        self._elements = elements

    @property
    def ids(self) -> Set[Union[str]]:
        # Note that the `element.model` can also be a `Workspace`, whose `id` is
        # of type `int`. But since we know that these are all `DslElements` (`id` of type `str`),
        # we can safely cast all the `id`s as `str` for the type checker to be happy.
        return set([str(element.model.id) for element in self._elements])

    @property
    def names(self) -> Set[Union[str]]:
        return set([str(element.model.name) for element in self._elements])

    @property
    def tags(self) -> Set[Union[str]]:
        all_tags: Set[str] = set()
        for element in self._elements:
            tags = element.tags
            all_tags = all_tags.union(tags)
        return all_tags

class Element:

    def __init__(self, element: DslElement):
        self._element = element

    @property
    def tags(self) -> Set[str]:
        return self._element.tags

    @property
    def technology(self) -> Optional[str]:
        if _has_technology_attribute(self._element):
            return self._element.model.technology
        return None

    # @property
    # def parent(self) -> Optional[Union[Workspace, SoftwareSystem, Container]]:
    #     return self._element.parent

    @property
    def sources(self) -> FlattenElement:
        return FlattenElement(self._element.sources)

    @property
    def destinations(self) -> FlattenElement:
        return FlattenElement(self._element.destinations)

    @property
    def properties(self) -> Dict[str, Any]:
        return self._element.model.properties

    def __eq__(self, element: object) -> bool:
        return isinstance(element, type(self._element)) and\
               element.model.id == self._element.model.id

class Relationship:

    def __init__(self, relationship: _Relationship):
        self._relationship = relationship

    @property
    def tags(self) -> Set[str]:
        return self._relationship.tags

    @property
    def technology(self) -> Optional[str]:
        return self._relationship.model.technology

    @property
    def source(self) -> Element:
        return Element(self._relationship.source)

    @property
    def destination(self) -> Element:
        return Element(self._relationship.destination)

    @property
    def properties(self) -> Dict[str, Any]:
        if self._relationship.model.properties is not None:
            return self._relationship.model.properties
        return dict()

class Expression:

    """
    A class used to filter the elements and the relationships in the workspace.
    To be used when defining views.

    In the Structurizr DSL, these are called "Expressions". See the Structurizr docs here:
    https://docs.structurizr.com/dsl/expressions
    """

    def __init__(
        self,
        elements: Iterable[Callable[[Element], bool]]=[],
        relationships: Iterable[Callable[[Relationship], bool]]=[],
    ) -> 'None':
        self._elements = elements
        self._relationships = relationships

    def elements(
        self,
        workspace: Workspace,
    ) -> List[DslElement]:

        filtered_elements: List[DslElement] = []

        workspace_elements = buildzr.dsl.Explorer(workspace).walk_elements()
        if self._elements:
            for element in workspace_elements:
                if any([f(Element(element)) for f in self._elements]):
                    filtered_elements.append(element)
        else:
            filtered_elements = list(workspace_elements)

        return filtered_elements

    def relationships(
        self,
        workspace: Workspace
    ) -> List[DslRelationship]:

        filtered_relationships: List[DslRelationship] = []

        workspace_relationships = buildzr.dsl.Explorer(workspace).walk_relationships()
        if self._relationships:
            for relationship in workspace_relationships:
                if any([f(Relationship(relationship)) for f in self._relationships]):
                    filtered_relationships.append(relationship)
        else:
            filtered_relationships = list(workspace_relationships)

        return filtered_relationships