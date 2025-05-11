from buildzr.dsl.dsl import (
    Person,
    SoftwareSystem,
    Container,
    Component,
)

from buildzr.dsl.relations import (
    _Relationship,
    _UsesData,
)

from typing import (
    Union,
    Generator,
    Iterable,
)

from buildzr.dsl.dsl import (
    Workspace,
)

class Explorer:

    def __init__(self, workspace_or_element: Union[Workspace, Person, SoftwareSystem, Container, Component]):
        self._workspace_or_element = workspace_or_element

    def walk_elements(self) -> Generator[Union[Person, SoftwareSystem, Container, Component], None, None]:
        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:
                explorer = Explorer(child).walk_elements()
                yield child
                yield from explorer

    def walk_relationships(self) -> Generator[_Relationship, None, None]:

        if self._workspace_or_element.children:

            for child in self._workspace_or_element.children:

                if child.relationships:
                    for relationship in child.relationships:
                        yield relationship

                explorer = Explorer(child).walk_relationships()
                yield from explorer