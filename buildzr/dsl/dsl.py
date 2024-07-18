from dataclasses import dataclass
import buildzr
from abc import ABC, abstractmethod
from typing import Union, Tuple, List, Dict, Optional, overload
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
        """
        Returns the `dataclass` of the `DslElement` that follows Structurizr's
        JSON Schema (see https://github.com/structurizr/json)
        """
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
                self._m.model.softwareSystems.append(model._m)
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

    @overload
    def __rshift__(self, description: str) -> '_UsesFrom':
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
class With:
    tags: Optional[List[str]] = None
    properties: Optional[Dict[str, str]] = None
    url: Optional[str] = None

@dataclass
class _UsesData:
    relationship: buildzr.models.Relationship
    source: Src

class _AddRelationshipExtras:

    def __init__(self, uses_to: '_UsesTo', relationship_extras: With) -> None:
        if relationship_extras.tags:
            uses_to.uses_data.relationship.tags = " ".join(relationship_extras.tags)
        if relationship_extras.properties:
            uses_to.uses_data.relationship.properties = relationship_extras.properties
        if relationship_extras.url:
            uses_to.uses_data.relationship.url = relationship_extras.url

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

        # Used to pass the `_UsesData` object as reference to the `__or__`
        # operator overloading method.
        self._ref: Tuple[_UsesData] = (uses_data,)

    def __or__(self, _with: With) -> None:
        if _with.tags:
            self._ref[0].relationship.tags = " ".join(_with.tags)
        if _with.properties:
            self._ref[0].relationship.properties = _with.properties
        if _with.url:
            self._ref[0].relationship.url = _with.url