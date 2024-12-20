from buildzr.dsl.interfaces import (
    DslWorkspaceElement,
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
from typing import Set, Union, Optional, List, Dict, Any, Callable, Tuple, Sequence, Iterable, cast, Type
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

    # TODO: Make a test for this in `tests/test_expression.py`
    @property
    def id(self) -> str:
        return cast(str, self._element.model.id)

    @property
    def type(self) -> Type:
        return type(self._element)

    @property
    def tags(self) -> Set[str]:
        return self._element.tags

    @property
    def technology(self) -> Optional[str]:
        if _has_technology_attribute(self._element):
            return self._element.model.technology
        return None

    # TODO: Make a test for this in `tests/test_expression.py`
    @property
    def parent(self) -> Optional[Union[DslWorkspaceElement, DslElement]]:
        return self._element.parent

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

    # TODO: Make a test for this in `tests/test_expression.py`
    @property
    def id(self) -> str:
        return cast(str, self._relationship.model.id)

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
        include_elements: Iterable[Callable[[Workspace, Element], bool]]=[lambda w, e: True],
        exclude_elements: Iterable[Callable[[Workspace, Element], bool]]=[],
        include_relationships: Iterable[Callable[[Workspace, Relationship], bool]]=[lambda w, e: True],
        exclude_relationships: Iterable[Callable[[Workspace, Relationship], bool]]=[],
    ) -> 'None':
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

    def elements(
        self,
        workspace: Workspace,
    ) -> List[DslElement]:

        filtered_elements: List[DslElement] = []

        workspace_elements = buildzr.dsl.Explorer(workspace).walk_elements()
        for element in workspace_elements:
            any_includes = any([f(workspace, Element(element)) for f in self._include_elements])
            any_excludes = any([f(workspace, Element(element)) for f in self._exclude_elements])
            if any_includes and not any_excludes:
                filtered_elements.append(element)

        return filtered_elements

    def relationships(
        self,
        workspace: Workspace
    ) -> List[DslRelationship]:

        """
        Returns the relationships that are included as defined in
        `include_relationships` and excludes those that are defined in
        `exclude_relationships`. Any relationships that directly works on
        elements that are excluded as defined in `exclude_elements` will also be
        excluded.
        """

        filtered_relationships: List[DslRelationship] = []

        def _is_relationship_of_excluded_elements(
            workspace: Workspace,
            relationship: Relationship,
            exclude_element_predicates: Iterable[Callable[[Workspace, Element], bool]],
        ) -> bool:
            return any([
                f(workspace, relationship.source) for f in exclude_element_predicates
            ] + [
                f(workspace, relationship.destination) for f in exclude_element_predicates
            ])

        workspace_relationships = buildzr.dsl.Explorer(workspace).walk_relationships()
        for relationship in workspace_relationships:
            any_includes = any([f(workspace, Relationship(relationship)) for f in self._include_relationships])

            # Also exclude relationships whose source or destination elements are excluded.
            any_excludes = any([
                f(workspace, Relationship(relationship))
                for f in self._exclude_relationships
            ] + [
                _is_relationship_of_excluded_elements(
                    workspace,
                    Relationship(relationship),
                    self._exclude_elements,
                )
            ])
            if any_includes and not any_excludes:
                filtered_relationships.append(relationship)

        return filtered_relationships