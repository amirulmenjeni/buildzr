from dataclasses import dataclass
import buildzr
from abc import ABC
from typing import Type, Generic, Union, Tuple, List, Optional, TypeVar, overload
from typing_extensions import Self
from .factory import GenerateId

class Workspace(buildzr.models.Workspace):
    """
    Represents a Structurizr workspace, which is a wrapper for a software architecture model, views, and documentation.
    """

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_workspace()
        self.name = name
        self.description = description
        self.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )
        self.configuration = buildzr.models.WorkspaceConfiguration(
            scope=buildzr.models.Scope.Landscape
        )

    def contains(self, models: List[Union[
        buildzr.models.Person,
        buildzr.models.SoftwareSystem,
    ]]):
        for model in models:
            if isinstance(model, Person):
                self.model.people.append(model)
            elif isinstance(model, SoftwareSystem):
                self.model.softwareSystems.append(model)
            else:
                # Ignore other model or bad types for now.
                pass

class SoftwareSystem(buildzr.models.SoftwareSystem):
    """
    A software system.
    """

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_element()
        self.name = name
        self.description = description

class Person(buildzr.models.Person):
    """
    A person who uses a software system.
    """

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_element()
        self.name = name
        self.description = description
        self.relationships = []

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> '_UsesFrom':
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> '_UsesFrom':
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, Tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])


Src = Union[Person, SoftwareSystem]
Dst = Union[Person, SoftwareSystem]

@dataclass
class _UsesData:
    relationship: buildzr.models.Relationship
    source: Src

class _UsesFrom:

    def __init__(self, source: Src, description: str="", technology: str="") -> '_UsesTo':
        self.uses_data = _UsesData(
            relationship=buildzr.models.Relationship(
                id=GenerateId.for_relationship(),
                description=description,
                technology=technology,
                sourceId=source.id,
            ),
            source=source,
        )

    def __rshift__(self, destination: Dst) -> '_UsesTo':
        return _UsesTo(self.uses_data, destination)

class _UsesTo:

    def __init__(self, uses_data: _UsesData, destination: Dst) -> None:
        uses_data.relationship.destinationId = destination.id
        if any(uses_data.source.relationships):
            uses_data.source.relationships.append(uses_data.relationship)
        else:
            uses_data.source.relationships = [uses_data.relationship]