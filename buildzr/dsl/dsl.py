from dataclasses import dataclass
import buildzr
from abc import ABC, abstractmethod
from typing import Union, Tuple, List, overload
from typing_extensions import Self
from .factory import GenerateId

Model = Union[
    buildzr.models.Workspace,
    buildzr.models.Person,
    buildzr.models.SoftwareSystem,
]

class DslElement(ABC):
    """An abstract class used to label classes that are part of the buildzr DSL"""

    @property
    @abstractmethod
    def model(self) -> Model:
        pass

class Workspace(DslElement):
    """
    Represents a Structurizr workspace, which is a wrapper for a software architecture model, views, and documentation.
    """

    @property
    def model(self) -> buildzr.models.Workspace:
        return self._m

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Workspace()
        self.model.id = GenerateId.for_workspace()
        self.model.name = name
        self.model.description = description
        self.model.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )
        self.model.configuration = buildzr.models.WorkspaceConfiguration(
            scope=buildzr.models.Scope.Landscape
        )

    def contains(self, models: List[Union[
        'Person',
        'SoftwareSystem'
    ]]) -> None:
        for model in models:
            if isinstance(model, Person):
                if self._m.model is not None:
                    if self._m.model.people is not None:
                        self._m.model.people.append(model._m)
            elif isinstance(model, SoftwareSystem):
                self._m.model.softwareSystems.append(model)
            else:
                # Ignore other model or bad types for now.
                pass

class SoftwareSystem(DslElement):
    """
    A software system.
    """

    @property
    def model(self) -> buildzr.models.SoftwareSystem:
        return self._m

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.SoftwareSystem()
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description

class Person(DslElement):
    """
    A person who uses a software system.
    """

    @property
    def model(self) -> buildzr.models.Person:
        return self._m

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Person()
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> '_UsesFrom':
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> '_UsesFrom':
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")

Src = Union[Person, SoftwareSystem]
Dst = Union[Person, SoftwareSystem]

@dataclass
class _UsesData:
    relationship: buildzr.models.Relationship
    source: Src

class _UsesFrom:

    def __init__(self, source: Src, description: str="", technology: str="") -> None:
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