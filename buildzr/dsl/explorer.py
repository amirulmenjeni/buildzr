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
        import buildzr
        from buildzr.dsl.factory.gen_id import GenerateId

        if self._workspace_or_element.children:
            for child in self._workspace_or_element.children:
                # Relationships aren't materialized in the `Workspace` or in any
                # of the `DslElement`s. As such, we need to recreate the `_Relationship` objects
                # from the Structurizr model.

                if child.model.relationships and child.destinations:
                    for relationship, destination in zip(child.model.relationships, child.destinations):
                        fake_relationship = _Relationship(
                            _UsesData(
                                relationship=buildzr.models.Relationship(
                                    id=relationship.id,
                                    description=relationship.description,
                                    properties=relationship.properties,
                                    technology=relationship.technology,
                                    tags=relationship.tags,
                                    sourceId=relationship.sourceId,
                                ),
                                source=child,
                            ),
                            destination=destination,
                            _include_in_model=False,
                        )
                        fake_relationship._tags = set(relationship.tags.split(','))

                        yield fake_relationship

                explorer = Explorer(child).walk_relationships()
                yield from explorer