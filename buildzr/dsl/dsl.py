from dataclasses import dataclass
import buildzr
from abc import ABC, abstractproperty
from typing import Type, Generic, Union, Tuple, List, Optional, TypeVar, overload
from typing_extensions import Self
from .factory import GenerateId

class DslElement(ABC):
    """An abstract class used to label classes that are part of the buildzr DSL"""
    ...

class Workspace(DslElement):
    """
    Represents a Structurizr workspace, which is a wrapper for a software architecture model, views, and documentation.
    """

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Workspace()
        self._m.id = GenerateId.for_workspace()
        self._m.name = name
        self._m.description = description
        self._m.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )
        self._m.configuration = buildzr.models.WorkspaceConfiguration(
            scope=buildzr.models.Scope.Landscape
        )

    def contains(self, models: List[Union[
        buildzr.models.Person,
        buildzr.models.SoftwareSystem,
    ]]):
        for model in models:
            if isinstance(model, Person):
                self._m.model.people.append(model)
            elif isinstance(model, SoftwareSystem):
                self._m.model.softwareSystems.append(model)
            else:
                # Ignore other model or bad types for now.
                pass

class SoftwareSystem(DslElement):
    """
    A software system.
    """

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.SoftwareSystem()
        self._m.id = GenerateId.for_element()
        self._m.name = name
        self._m.description = description

class Person(DslElement):
    """
    A person who uses a software system.
    """

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Person()
        self._m.id = GenerateId.for_element()
        self._m.name = name
        self._m.description = description
        self._m.relationships = []

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
                sourceId=source._m.id,
            ),
            source=source,
        )

    def __rshift__(self, destination: Dst) -> '_UsesTo':
        return _UsesTo(self.uses_data, destination)

class _UsesTo:

    def __init__(self, uses_data: _UsesData, destination: Dst) -> None:
        uses_data.relationship.destinationId = destination._m.id
        if any(uses_data.source._m.relationships):
            uses_data.source._m.relationships.append(uses_data.relationship)
        else:
            uses_data.source._m.relationships = [uses_data.relationship]