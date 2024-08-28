from dataclasses import dataclass
import buildzr
from abc import ABC, abstractmethod
from .factory import GenerateId
from typing_extensions import (
    Self,
    ParamSpec,
    TypeGuard,
)
from typing import (
    Any,
    Union,
    Tuple,
    List,
    Set,
    Dict,
    Optional,
    Generic,
    TypeVar,
    Protocol,
    Callable,
    Iterable,
    cast,
    overload,
)

Model = Union[
    buildzr.models.Workspace,
    buildzr.models.Person,
    buildzr.models.SoftwareSystem,
    buildzr.models.Container,
    buildzr.models.Component,
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

TParent = TypeVar('TParent', bound=Union['DslWorkspaceElement', 'DslElement'], covariant=True)
TChild = TypeVar('TChild', bound='DslElement', contravariant=True)

def _child_name_transform(name: str) -> str:
    return name.lower().replace(' ', '_')

def _is_software_container_fluent_relationship(
    obj: '_FluentRelationship[Any, Any]') -> TypeGuard["_FluentRelationship['SoftwareSystem', 'Container']"]:

    return isinstance(obj._parent, SoftwareSystem) and all([
        isinstance(x, Container) for x in obj._children
    ])

def _is_container_component_fluent_relationship(
    obj: '_FluentRelationship[Any, Any]') -> TypeGuard["_FluentRelationship['Container', 'Component']"]:

    return isinstance(obj._parent, Container) and all([
        isinstance(x, Component) for x in obj._children
    ])

def _create_linked_relationship_from(
    relationship: '_Relationship[TSrc, TDst]') -> buildzr.models.Relationship:

    src = relationship.source
    dst = relationship.destination

    return buildzr.models.Relationship(
        id=GenerateId.for_relationship(),
        sourceId=str(src.model.id),
        destinationId=str(dst.parent.model.id),
        linkedRelationshipId=relationship.model.id,
    )

@dataclass
class With:
    tags: Optional[Set[str]] = None
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

class DslWorkspaceElement(ABC):

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Workspace:
        pass

    @property
    @abstractmethod
    def parent(self) -> None:
        pass

class DslElement(ABC):
    """An abstract class used to label classes that are part of the buildzr DSL"""

    _Affectee = Union['Person', 'SoftwareSystem', 'Container', 'Component']

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

    @property
    @abstractmethod
    def tags(self) -> Set[str]:
        pass

    TAffectee = TypeVar('TAffectee', bound=_Affectee, contravariant=True)
    def uses(
        self,
        other: TAffectee,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> '_Relationship[Self, TAffectee]':

        source = self
        return _Relationship(
            _UsesData(
                relationship=buildzr.models.Relationship(
                    description=description,
                    technology=technology,
                ),
                source=source,
            ),
            destination=other,
            tags=tags,
        )

class DslRelationship(ABC, Generic[TSrc, TDst]):
    """
    An abstract class specially used to label classes that are part of the
    relationship definer in the buildzr DSL
    """

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Relationship:
        pass

    @property
    @abstractmethod
    def tags(self) -> Set[str]:
        pass

    @property
    @abstractmethod
    def source(self) -> DslElement:
        pass

    @property
    @abstractmethod
    def destination(self) -> DslElement:
        pass

class _Relationship(DslRelationship[TSrc, TDst]):

    @property
    def model(self) -> buildzr.models.Relationship:
        return self._m

    @property
    def tags(self) -> Set[str]:
        return self._tags

    @property
    def source(self) -> DslElement:
        return self._src

    @property
    def destination(self) -> DslElement:
        return self._dst

    def __init__(self, uses_data: _UsesData[TSrc], destination: TDst, tags: Set[str]=set()) -> None:
        self._m = uses_data.relationship
        self._tags = {'Relationship'}.union(tags)
        self._src = uses_data.source
        self._dst = destination
        self.model.tags = ','.join(self._tags)

        uses_data.relationship.destinationId = str(destination.model.id)

        if not isinstance(uses_data.source.model, buildzr.models.Workspace):
            if any(uses_data.source.model.relationships):
                uses_data.source.model.relationships.append(uses_data.relationship)
            else:
                uses_data.source.model.relationships = [uses_data.relationship]

            # TODO: Create implied relationship(s)

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
        tags: Optional[Set[str]]=None,
        properties: Optional[Dict[str, str]]=None,
        url: Optional[str]=None,
    ) -> Self:
        """
        Adds extra info to the relationship.

        This can also be achieved using the syntax sugar `DslRelationship |
        With(...)`.
        """
        if tags:
            self._tags = self._tags.union(tags)
            self._ref[0].relationship.tags = ",".join(self._tags)
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

    def get(self) -> TParent:
        return self._parent

class Workspace(DslWorkspaceElement):
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
        self._dynamic_attrs: Dict[str, Union['Person', 'SoftwareSystem']] = {}
        self.model.id = GenerateId.for_workspace()
        self.model.name = name
        self.model.description = description
        self.model.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )
        self.model.configuration = buildzr.models.WorkspaceConfiguration(
            scope=buildzr.models.Scope.Landscape,
        )

    def contains(
        self,
        *models: Union[
            'Person',
            'SoftwareSystem',
            _FluentRelationship['SoftwareSystem', 'Container'],
            _FluentRelationship['Container', 'Component'],
        ]) -> _FluentRelationship['Workspace', Union['Person', 'SoftwareSystem']]:

        args: List[Union[Person, SoftwareSystem]] = []

        for model in models:
            if isinstance(model, Person):
                self._m.model.people.append(model._m)
                model._parent = self
                self._dynamic_attrs[_child_name_transform(model.model.name)] = model
                args.append(model)
            elif isinstance(model, SoftwareSystem):
                self._m.model.softwareSystems.append(model._m)
                model._parent = self
                self._dynamic_attrs[_child_name_transform(model.model.name)] = model
                args.append(model)
            elif _is_software_container_fluent_relationship(model):
                self._m.model.softwareSystems.append(model._parent._m)
                model._parent._parent = self
                self._dynamic_attrs[_child_name_transform(model._parent.model.name)] = model._parent
                args.append(model._parent)
            elif _is_container_component_fluent_relationship(model):
                self._m.model.softwareSystems.append(model._parent._parent._m)
                model._parent._parent._parent = self
                self._dynamic_attrs[_child_name_transform(model._parent._parent.model.name)] = model._parent._parent
                args.append(model._parent._parent)
        return _FluentRelationship['Workspace', Union['Person', 'SoftwareSystem']](self, tuple(args))

    def __getattr__(self, name: str) -> Union['Person', 'SoftwareSystem']:
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> Union['Person', 'SoftwareSystem']:
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class SoftwareSystem(DslElement):
    """
    A software system.
    """

    _Affectee = Union['Person', 'SoftwareSystem', 'Container', 'Component']
    _SoftwareSystemRelation = _UsesFrom['SoftwareSystem', _Affectee]

    @property
    def model(self) -> buildzr.models.SoftwareSystem:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: _Affectee,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, _Affectee]:
        return super().uses(other, description=description, technology=technology, tags=tags)

    def __init__(self, name: str, description: str="", tags: Set[str]=set()) -> None:
        self._m = buildzr.models.SoftwareSystem()
        self._parent: Optional[Workspace] = None
        self._tags = {'Element', 'Software System'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Container'] = {}
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.tags = ','.join(self._tags)

    def contains(
        self,
        *containers: Union['Container', _FluentRelationship['Container', 'Component']]
    ) -> _FluentRelationship['SoftwareSystem', 'Container']:
        if not self.model.containers:
            self.model.containers = []

        args: List[Container] = []

        for child in containers:
            if isinstance(child, Container):
                self.model.containers.append(child.model)
                child._parent = self
                self._dynamic_attrs[_child_name_transform(child.model.name)] = child
                args.append(child)
            elif _is_container_component_fluent_relationship(child):
                self._m.containers.append(child._parent._m)
                child._parent._parent = self
                self._dynamic_attrs[_child_name_transform(child._parent.model.name)] = child._parent
                args.append(child._parent)
        return _FluentRelationship['SoftwareSystem', 'Container'](self, tuple(args))

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

    def __getattr__(self, name: str) -> 'Container':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Container':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class Person(DslElement):
    """
    A person who uses a software system.
    """

    _Affectee = Union['Person', 'SoftwareSystem', 'Container', 'Component']
    _PersonRelation = _UsesFrom['Person', _Affectee]

    @property
    def model(self) -> buildzr.models.Person:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: _Affectee,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, _Affectee]:
        return super().uses(other, description=description, technology=technology, tags=tags)

    def __init__(self, name: str, description: str="", tags: Set[str]=set()) -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self._tags = {'Element', 'Person'}.union(tags)
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)

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

    _Affectee = Union[Person, SoftwareSystem, 'Container', 'Component']
    _ContainerRelation = _UsesFrom['Container', _Affectee]

    @property
    def model(self) -> buildzr.models.Container:
        return self._m

    @property
    def parent(self) -> Optional[SoftwareSystem]:
        return self._parent

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: _Affectee,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, _Affectee]:
        return super().uses(other, description=description, technology=technology, tags=tags)

    def contains(self, *components: 'Component') -> _FluentRelationship['Container', 'Component']:
        if not self.model.components:
            self.model.components = []
        for component in components:
            self.model.components.append(component.model)
            component._parent = self
            self._dynamic_attrs[_child_name_transform(component.model.name)] = component
        return _FluentRelationship['Container', 'Component'](self, components)

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set()) -> None:
        self._m = buildzr.models.Container()
        self._parent: Optional[SoftwareSystem] = None
        self._tags = {'Element', 'Container'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Component'] = {}
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.technology = technology
        self.model.tags = ','.join(self._tags)

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

    def __getattr__(self, name: str) -> 'Component':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Component':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class Component(DslElement):
    """
    A component (a grouping of related functionality behind an interface that runs inside a container).
    """

    _Affectee = Union[Person, SoftwareSystem, Container, 'Component']
    _ComponentRelation = _UsesFrom['Component', _Affectee]

    @property
    def model(self) -> buildzr.models.Component:
        return self._m

    @property
    def parent(self) -> Optional[Container]:
        return self._parent

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: _Affectee,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, _Affectee]:
        return super().uses(other, description=description, technology=technology, tags=tags)

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set()) -> None:
        self._m = buildzr.models.Component()
        self._parent: Optional[Container] = None
        self._tags = {'Element', 'Component'}.union(tags)
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.technology = technology
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _ComponentRelation:
        ...

    @overload
    def __rshift__(self, description: str) -> _ComponentRelation:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _ComponentRelation:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")