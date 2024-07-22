from dataclasses import dataclass
import buildzr
from abc import ABC, abstractmethod
from typing import Union, Tuple, List, Dict, Optional, Generic, TypeVar, overload
from .factory import GenerateId

Model = Union[
    buildzr.models.Workspace,
    buildzr.models.Person,
    buildzr.models.SoftwareSystem,
    buildzr.models.Container,
]

DslParentElement = Union[
    None,
    'Workspace',
    'Person',
    'SoftwareSystem',
    'Container',
]

TSrc = TypeVar('TSrc', bound='DslElement', contravariant=True)
TDst = TypeVar('TDst', bound='DslElement', contravariant=True)

@dataclass
class With:
    tags: Optional[List[str]] = None
    properties: Optional[Dict[str, str]] = None
    url: Optional[str] = None

@dataclass
class _UsesData(Generic[TSrc]):
    relationship: buildzr.models.Relationship
    source: TSrc

class _UsesFrom(Generic[TSrc, TDst]):

    def __init__(self, source: TSrc, description: str="", technology: str="") -> None:
        self.uses_data = _UsesData(
            relationship=buildzr.models.Relationship(
                id=GenerateId.for_relationship(),
                description=description,
                technology=technology,
                sourceId=str(source.model.id),
            ),
            source=source,
        )

    def __rshift__(self, destination: TDst) -> '_UsesTo[TSrc, TDst]':
        if isinstance(destination, Workspace):
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(destination).__name__}")
        return _UsesTo(self.uses_data, destination)

class _UsesTo(Generic[TSrc, TDst]):

    def __init__(self, uses_data: _UsesData[TSrc], destination: TDst) -> None:
        uses_data.relationship.destinationId = str(destination.model.id)

        if not isinstance(uses_data.source.model, buildzr.models.Workspace):
            if any(uses_data.source.model.relationships):
                uses_data.source.model.relationships.append(uses_data.relationship)
            else:
                uses_data.source.model.relationships = [uses_data.relationship]

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

    @property
    @abstractmethod
    def parent(self) -> DslParentElement:
        pass

class Workspace(DslElement):
    """
    Represents a Structurizr workspace, which is a wrapper for a software architecture model, views, and documentation.
    """

    @property
    def model(self) -> buildzr.models.Workspace:
        return self._m

    @property
    def parent(self) -> None:
        return None

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Workspace()
        self._parent = None
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
                self._m.model.people.append(model._m)
                model._parent = self
            elif isinstance(model, SoftwareSystem):
                self._m.model.softwareSystems.append(model._m)
                model._parent = self
            else:
                # Ignore other model or bad types for now.
                pass

class SoftwareSystem(DslElement):
    """
    A software system.
    """

    _SoftwareSystemRelation = _UsesFrom['SoftwareSystem', Union['Person', 'SoftwareSystem', 'Container']]

    @property
    def model(self) -> buildzr.models.SoftwareSystem:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.SoftwareSystem()
        self._parent: Optional[Workspace] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description

    def contains(self, containers: List['Container']) -> None:
        if not self.model.containers:
            self.model.containers = []
        for container in containers:
            self.model.containers.append(container.model)
            container._parent = self

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _SoftwareSystemRelation:
        ...

    @overload
    def __rshift__(self, description: str) -> _SoftwareSystemRelation:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _SoftwareSystemRelation:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")

class Person(DslElement):
    """
    A person who uses a software system.
    """

    _PersonRelation = _UsesFrom['Person', Union['Person', 'SoftwareSystem', 'Container']]

    @property
    def model(self) -> buildzr.models.Person:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    def __init__(self, name: str, description: str="") -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _PersonRelation:
        ...

    @overload
    def __rshift__(self, description: str) -> _PersonRelation:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _PersonRelation:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")

class Container(DslElement):
    """
    A container (something that can execute code or host data).
    """

    _ContainerRelation = _UsesFrom['Container', Union[Person, SoftwareSystem, 'Container']]

    @property
    def model(self) -> buildzr.models.Container:
        return self._m

    @property
    def parent(self) -> Optional[SoftwareSystem]:
        return self._parent

    def __init__(self, name: str, description: str="", technology: str="") -> None:
        self._m = buildzr.models.Container()
        self._parent: Optional[SoftwareSystem] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.technology = technology

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _ContainerRelation:
        ...

    @overload
    def __rshift__(self, description: str) -> _ContainerRelation:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _ContainerRelation:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")