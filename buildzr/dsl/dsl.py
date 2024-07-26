from dataclasses import dataclass
import buildzr
from abc import ABC, abstractmethod
from .factory import GenerateId
from typing_extensions import (
    Self,
    ParamSpec,
)
from typing import (
    Any,
    Union,
    Tuple,
    List,
    Dict,
    Optional,
    Generic,
    TypeVar,
    Protocol,
    Callable,
    overload,
)

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

TParent = TypeVar('TParent', bound='DslElement', covariant=True)
TChild = TypeVar('TChild', bound='DslElement', contravariant=True)

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

    def __rshift__(self, destination: TDst) -> '_Relationship[TSrc, TDst]':
        if isinstance(destination, Workspace):
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(destination).__name__}")
        return _Relationship(self.uses_data, destination)

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

class DslRelationship(ABC, Generic[TSrc, TDst]):
    """
    An abstract class specially used to label classes that are part of the
    relationship definer in the buildzr DSL
    """

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Relationship:
        pass

class _Relationship(DslRelationship[TSrc, TDst]):

    @property
    def model(self) -> buildzr.models.Relationship:
        return self._m

    def __init__(self, uses_data: _UsesData[TSrc], destination: TDst) -> None:
        self._m = uses_data.relationship

        uses_data.relationship.destinationId = str(destination.model.id)

        if not isinstance(uses_data.source.model, buildzr.models.Workspace):
            if any(uses_data.source.model.relationships):
                uses_data.source.model.relationships.append(uses_data.relationship)
            else:
                uses_data.source.model.relationships = [uses_data.relationship]

        # Used to pass the `_UsesData` object as reference to the `__or__`
        # operator overloading method.
        self._ref: Tuple[_UsesData] = (uses_data,)

    def __or__(self, _with: With) -> Self:
        return self.has(
            tags=_with.tags,
            properties=_with.properties,
            url=_with.url,
        )

    def has(
        self,
        tags: Optional[List[str]]=None,
        properties: Optional[Dict[str, str]]=None,
        url: Optional[str]=None,
    ) -> Self:
        if tags:
            self._ref[0].relationship.tags = " ".join(tags)
        if properties:
            self._ref[0].relationship.properties = properties
        if url:
            self._ref[0].relationship.url = url
        return self

class _FluentRelationship(Generic[TParent, TChild]):

    def __init__(self, parent: TParent, children: Tuple[TChild, ...]) -> None:
        self._children: Tuple[TChild, ...] = children
        self._parent: TParent = parent

    def where(self, func: Callable[..., List[DslRelationship]]) -> TParent:
        func(*self._children)
        return self._parent

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

    def contains(self, *models: Union['Person', 'SoftwareSystem']) -> _FluentRelationship['Workspace', Union['Person', 'SoftwareSystem']]:
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
        return _FluentRelationship['Workspace', Union['Person', 'SoftwareSystem', Any]](self, models)

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

    def contains(self, *containers: 'Container') -> _FluentRelationship['SoftwareSystem', 'Container']:
        if not self.model.containers:
            self.model.containers = []
        for container in containers:
            self.model.containers.append(container.model)
            container._parent = self
        return _FluentRelationship['SoftwareSystem', Union['Container', Any]](self, containers)

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