from dataclasses import dataclass
import buildzr
from .factory import GenerateId
from typing_extensions import (
    Self,
    TypeGuard,
    TypeIs,
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
    Literal,
    cast,
    overload,
    Sequence,
    Type,
)

from buildzr.dsl.interfaces import (
    DslWorkspaceElement,
    DslElement,
    DslRelationship,
    DslFluentRelationship,
    DslViewsElement,
    BindLeft,
    TSrc, TDst,
    TParent, TChild,
)

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


TypedModel = TypeVar('TypedModel')
class TypedDynamicAttribute(Generic[TypedModel]):

    def __init__(self, dynamic_attributes: Dict[str, Any]) -> None:
        self._dynamic_attributes = dynamic_attributes

    def __getattr__(self, name: str) -> TypedModel:
        return cast(TypedModel, self._dynamic_attributes.get(name))

class _UsesFrom(BindLeft[TSrc, TDst]):

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

    def __init__(
            self,
            uses_data: _UsesData[TSrc],
            destination: TDst,
            tags: Set[str]=set(),
            _include_in_model: bool=True,
        ) -> None:

        self._m = uses_data.relationship
        self._tags = {'Relationship'}.union(tags)
        self._src = uses_data.source
        self._dst = destination
        self.model.tags = ','.join(self._tags)

        uses_data.relationship.destinationId = str(destination.model.id)

        if not isinstance(uses_data.source.model, buildzr.models.Workspace):
            uses_data.source.destinations.append(self._dst)
            self._dst.sources.append(self._src)
            if _include_in_model:
                if uses_data.source.model.relationships:
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

class _FluentRelationship(DslFluentRelationship[TParent, TChild]):

    """
    A hidden class used in the fluent DSL syntax after specifying a model (i.e.,
    Person, Software System, Container) to define relationship(s) within the
    specified model.
    """

    def __init__(self, parent: TParent, children: Tuple[TChild, ...]) -> None:
        self._children: Tuple[TChild, ...] = children
        self._parent: TParent = parent

    def where(self, func: Callable[..., List[DslRelationship]], implied:bool=False) -> TParent:
        relationships = func(*self._children)

        # If we have relationship s >> do >> a.b, then create s >> do >> a.
        # If we have relationship s.ss >> do >> a.b.c, then create s.ss >> do >> a.b and s.ss >> do >> a.
        # And so on...
        if implied:
            for relationship in relationships:
                source = relationship.source
                parent = relationship.destination.parent
                while parent is not None and not isinstance(parent, DslWorkspaceElement):
                    r = source.uses(parent, description=relationship.model.description, technology=relationship.model.technology)
                    r.model.linkedRelationshipId = relationship.model.id
                    parent = parent.parent

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

    @property
    def children(self) -> Optional[List[Union['Person', 'SoftwareSystem']]]:
        return self._children

    def __init__(self, name: str, description: str="", scope: Literal['landscape', 'software_system', None]='software_system') -> None:
        self._m = buildzr.models.Workspace()
        self._parent = None
        self._children: Optional[List[Union['Person', 'SoftwareSystem']]] = []
        self._dynamic_attrs: Dict[str, Union['Person', 'SoftwareSystem']] = {}
        self.model.id = GenerateId.for_workspace()
        self.model.name = name
        self.model.description = description
        self.model.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )

        scope_mapper: Dict[
            str,
            Literal[buildzr.models.Scope.Landscape, buildzr.models.Scope.SoftwareSystem, None]
        ] = {
            'landscape': buildzr.models.Scope.Landscape,
            'software_system': buildzr.models.Scope.SoftwareSystem,
            None: None
        }

        self.model.configuration = buildzr.models.WorkspaceConfiguration(
            scope=scope_mapper[scope],
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
                self._children.append(model)
            elif isinstance(model, SoftwareSystem):
                self._m.model.softwareSystems.append(model._m)
                model._parent = self
                self._dynamic_attrs[_child_name_transform(model.model.name)] = model
                args.append(model)
                self._children.append(model)
            elif _is_software_container_fluent_relationship(model):
                self._m.model.softwareSystems.append(model._parent._m)
                model._parent._parent = self
                self._dynamic_attrs[_child_name_transform(model._parent.model.name)] = model._parent
                args.append(model._parent)
                self._children.append(model._parent)
            elif _is_container_component_fluent_relationship(model):
                self._m.model.softwareSystems.append(model._parent._parent._m)
                model._parent._parent._parent = self
                self._dynamic_attrs[_child_name_transform(model._parent._parent.model.name)] = model._parent._parent
                args.append(model._parent._parent)
                self._children.append(model._parent._parent)
        return _FluentRelationship['Workspace', Union['Person', 'SoftwareSystem']](self, tuple(args))

    def person(self) -> TypedDynamicAttribute['Person']:
        return TypedDynamicAttribute['Person'](self._dynamic_attrs)

    def software_system(self) -> TypedDynamicAttribute['SoftwareSystem']:
        return TypedDynamicAttribute['SoftwareSystem'](self._dynamic_attrs)

    def with_views(
        self,
        *views: Union[
            'SystemLandscapeView',
            'SystemContextView',
            'ContainerView',
            'ComponentView',
        ]
    ) -> 'Views':
        return Views(self).contains(*views)

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

    @property
    def model(self) -> buildzr.models.SoftwareSystem:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> Optional[List['Container']]:
        return self._children

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: DslElement,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, DslElement]:

        source = self

        uses_from = _UsesFrom[Self, DslElement](
            source=source,
            description=description,
            technology=technology
        )

        return _Relationship(
            uses_from.uses_data,
            destination=other,
            tags=tags,
        )

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.SoftwareSystem()
        self._parent: Optional[Workspace] = None
        self._children: Optional[List['Container']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Software System'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Container'] = {}
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

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
                self._children.append(child)
            elif _is_container_component_fluent_relationship(child):
                self._m.containers.append(child._parent._m)
                child._parent._parent = self
                self._dynamic_attrs[_child_name_transform(child._parent.model.name)] = child._parent
                args.append(child._parent)
                self._children.append(child._parent)
        return _FluentRelationship['SoftwareSystem', 'Container'](self, tuple(args))

    def container(self) -> TypedDynamicAttribute['Container']:
        return TypedDynamicAttribute['Container'](self._dynamic_attrs)

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, _Affectee]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, _Affectee]:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _UsesFrom[Self, _Affectee]:
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

    @property
    def model(self) -> buildzr.models.Person:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    @property
    def children(self) -> None:
        """
        The `Person` element does not have any children, and will always return
        `None`.
        """
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: DslElement,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, DslElement]:

        source = self

        uses_from = _UsesFrom[Self, DslElement](
            source=source,
            description=description,
            technology=technology
        )

        return _Relationship(
            uses_from.uses_data,
            destination=other,
            tags=tags,
        )

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Person'}.union(tags)
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, _Affectee]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, _Affectee]:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _UsesFrom[Self, _Affectee]:
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

    @property
    def model(self) -> buildzr.models.Container:
        return self._m

    @property
    def parent(self) -> Optional[SoftwareSystem]:
        return self._parent

    @property
    def children(self) -> Optional[List['Component']]:
        return self._children

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: DslElement,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, DslElement]:

        source = self

        uses_from = _UsesFrom[Self, DslElement](
            source=source,
            description=description,
            technology=technology
        )

        return _Relationship(
            uses_from.uses_data,
            destination=other,
            tags=tags,
        )

    def contains(self, *components: 'Component') -> _FluentRelationship['Container', 'Component']:
        if not self.model.components:
            self.model.components = []
        for component in components:
            self.model.components.append(component.model)
            component._parent = self
            self._dynamic_attrs[_child_name_transform(component.model.name)] = component
            self._children.append(component)
        return _FluentRelationship['Container', 'Component'](self, components)

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Container()
        self._parent: Optional[SoftwareSystem] = None
        self._children: Optional[List['Component']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Container'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Component'] = {}
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.technology = technology
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    def component(self) -> TypedDynamicAttribute['Component']:
        return TypedDynamicAttribute['Component'](self._dynamic_attrs)

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, _Affectee]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, _Affectee]:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _UsesFrom[Self, _Affectee]:
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

    @property
    def model(self) -> buildzr.models.Component:
        return self._m

    @property
    def parent(self) -> Optional[Container]:
        return self._parent

    @property
    def children(self) -> None:
        return None

    @property
    def sources(self) -> List[DslElement]:
        return self._sources

    @property
    def destinations(self) -> List[DslElement]:
        return self._destinations

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def uses(
        self,
        other: DslElement,
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> _Relationship[Self, DslElement]:

        source = self

        uses_from = _UsesFrom[Self, DslElement](
            source=source,
            description=description,
            technology=technology
        )

        return _Relationship(
            uses_from.uses_data,
            destination=other,
            tags=tags,
        )

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Component()
        self._parent: Optional[Container] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Component'}.union(tags)
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.technology = technology
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, _Affectee]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, _Affectee]:
        ...

    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> _UsesFrom[Self, _Affectee]:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")

_RankDirection = Literal['tb', 'bt', 'lr', 'rl']

_AutoLayout = Optional[
    Union[
        _RankDirection,
        Tuple[_RankDirection, float],
        Tuple[_RankDirection, float, float]
    ]
]

def _auto_layout_to_model(auto_layout: _AutoLayout) -> buildzr.models.AutomaticLayout:
    """
    See: https://docs.structurizr.com/dsl/language#autolayout
    """

    model = buildzr.models.AutomaticLayout()

    def is_auto_layout_with_rank_separation(\
        auto_layout: _AutoLayout,
    ) -> TypeIs[Tuple[_RankDirection, float]]:
        if isinstance(auto_layout, tuple):
            return len(auto_layout) == 2 and \
                    type(auto_layout[0]) is _RankDirection and \
                    type(auto_layout[1]) is float
        return False

    def is_auto_layout_with_node_separation(\
        auto_layout: _AutoLayout,
    ) -> TypeIs[Tuple[_RankDirection, float, float]]:
        if isinstance(auto_layout, tuple) and len(auto_layout) == 3:
            return type(auto_layout[0]) is _RankDirection and \
                   all([type(x) is float for x in auto_layout[1:]])
        return False

    map_rank_direction: Dict[_RankDirection, buildzr.models.RankDirection] = {
        'lr': buildzr.models.RankDirection.LeftRight,
        'tb': buildzr.models.RankDirection.TopBottom,
        'rl': buildzr.models.RankDirection.RightLeft,
        'bt': buildzr.models.RankDirection.BottomTop,
    }

    if auto_layout is not None:
        if is_auto_layout_with_rank_separation(auto_layout):
            d, rs = cast(Tuple[_RankDirection, float], auto_layout)
            model.rankDirection = map_rank_direction[cast(_RankDirection, d)]
            model.rankSeparation = rs
        elif is_auto_layout_with_node_separation(auto_layout):
            d, rs, ns = cast(Tuple[_RankDirection, float, float], auto_layout)
            model.rankDirection = map_rank_direction[cast(_RankDirection, d)]
            model.rankSeparation = rs
            model.nodeSeparation = ns
        else:
            model.rankDirection = map_rank_direction[cast(_RankDirection, auto_layout)]

    if model.rankSeparation is None:
        model.rankSeparation = 300
    if model.nodeSeparation is None:
        model.nodeSeparation = 300
    if model.edgeSeparation is None:
        model.edgeSeparation = 0
    if model.implementation is None:
        model.implementation = buildzr.models.Implementation.Graphviz
    if model.vertices is None:
        model.vertices = False

    return model

class SystemLandscapeView:

    from buildzr.dsl.expression import Expression

    @property
    def model(self) -> buildzr.models.SystemLandscapeView:
        return self._m

    @property
    def parent(self) -> Optional['Views']:
        return self._parent

    def __init__(
        self,
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        expression: Optional[Expression]=None,
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.SystemLandscapeView()
        self._parent: Optional['Views'] = None

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

class SystemContextView:

    """
    If no filter is applied, this view includes all elements that have a direct
    relationship with the selected `SoftwareSystem`.
    """

    from buildzr.dsl.expression import Expression, Element, Relationship

    @property
    def model(self) -> buildzr.models.SystemContextView:
        return self._m

    @property
    def parent(self) -> Optional['Views']:
        return self._parent

    def __init__(
        self,
        software_system_selector: Callable[[Workspace], SoftwareSystem],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Callable[[Workspace, Element], bool]]=[],
        exclude_elements: List[Callable[[Workspace, Element], bool]]=[],
        include_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        exclude_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.SystemContextView()
        self._parent: Optional['Views'] = None

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._selector = software_system_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        # TODO: Refactor below codes. Similar patterns may exists for other views.
        # Maybe make the views a subclass of some abstract `BaseView` class?

        software_system = self._selector(self._parent._parent)
        self._m.softwareSystemId = software_system.model.id
        view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e == software_system,
            lambda w, e: software_system.model.id in e.sources.ids,
            lambda w, e: software_system.model.id in e.destinations.ids,
        ]

        # TODO: (Or, TOTHINK?) The code below includes all sources and all
        # destinations of the subject software system. What if we want to
        # exclude a source? Maybe the predicates in `elements` and
        # `relationships` should be ANDed together afterall?
        view_relationships_filter: List[Callable[[Workspace, Relationship], bool]] = [
            lambda w, r: software_system == r.source,
            lambda w, r: software_system == r.destination,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        workspace = self._parent._parent

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            self._m.elements.append(ElementView(id=element_id))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class ContainerView:

    from buildzr.dsl.expression import Expression, Element, Relationship

    @property
    def model(self) -> buildzr.models.ContainerView:
        return self._m

    @property
    def parent(self) -> Optional['Views']:
        return self._parent

    def __init__(
        self,
        software_system_selector: Callable[[Workspace], SoftwareSystem],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Callable[[Workspace, Element], bool]]=[],
        exclude_elements: List[Callable[[Workspace, Element], bool]]=[],
        include_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        exclude_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.ContainerView()
        self._parent: Optional['Views'] = None

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._selector = software_system_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        software_system = self._selector(self._parent._parent)
        self._m.softwareSystemId = software_system.model.id

        container_ids = { container.model.id for container in software_system.children}

        view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e.parent == software_system,
            lambda w, e: any(container_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(container_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Callable[[Workspace, Relationship], bool]] = [
            lambda w, r: software_system == r.source.parent,
            lambda w, r: software_system == r.destination.parent,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        workspace = self._parent._parent

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            self._m.elements.append(ElementView(id=element_id))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class ComponentView:

    from buildzr.dsl.expression import Expression, Element, Relationship

    @property
    def model(self) -> buildzr.models.ComponentView:
        return self._m

    @property
    def parent(self) -> Optional['Views']:
        return self._parent

    def __init__(
        self,
        container_selector: Callable[[Workspace], Container],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Callable[[Workspace, Element], bool]]=[],
        exclude_elements: List[Callable[[Workspace, Element], bool]]=[],
        include_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        exclude_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.ComponentView()
        self._parent: Optional['Views'] = None

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._selector = container_selector
        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        container = self._selector(self._parent._parent)
        self._m.containerId = container.model.id

        component_ids = { component.model.id for component in container.children }

        view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e.parent == container,
            lambda w, e: any(component_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(component_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Callable[[Workspace, Relationship], bool]] = [
            lambda w, r: container == r.source.parent,
            lambda w, r: container == r.destination.parent,
        ]

        expression = Expression(
            include_elements=self._include_elements + view_elements_filter,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships + view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

        workspace = self._parent._parent

        element_ids = map(
            lambda x: str(x.model.id),
            expression.elements(workspace)
        )

        relationship_ids = map(
            lambda x: str(x.model.id),
            expression.relationships(workspace)
        )

        self._m.elements = []
        for element_id in element_ids:
            self._m.elements.append(ElementView(id=element_id))

        self._m.relationships = []
        for relationship_id in relationship_ids:
            self._m.relationships.append(RelationshipView(id=relationship_id))

class Views(DslViewsElement):

    @property
    def model(self) -> buildzr.models.Views:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    def __init__(
        self,
        workspace: Workspace,
    ) -> None:
        self._m = buildzr.models.Views()
        self._parent = workspace
        self._parent._m.views = self._m

    def contains(
        self,
        *views: Union[
            SystemLandscapeView,
            SystemContextView,
            ContainerView,
            ComponentView,
        ]) -> Self:

        for view in views:
            view._parent = self
            if isinstance(view, SystemLandscapeView):
                if self._m.systemLandscapeViews:
                    self._m.systemLandscapeViews.append(view.model)
                else:
                    self._m.systemLandscapeViews = [view.model]
            elif isinstance(view, SystemContextView):
                view._on_added()
                if self._m.systemContextViews:
                    self._m.systemContextViews.append(view.model)
                else:
                    self._m.systemContextViews = [view.model]
            elif isinstance(view, ContainerView):
                view._on_added()
                if self._m.containerViews:
                    self._m.containerViews.append(view.model)
                else:
                    self._m.containerViews = [view.model]
            elif isinstance(view, ComponentView):
                view._on_added()
                if self._m.componentViews:
                    self._m.componentViews.append(view.model)
                else:
                    self._m.componentViews = [view.model]
            else:
                raise NotImplementedError("The view {0} is currently not supported", type(view))

        return self

    def get_workspace(self) -> Workspace:
        """
        Get the `Workspace` which contain this views definition.
        """
        return self._parent