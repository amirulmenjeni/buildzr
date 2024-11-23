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

from buildzr.sinks.interfaces import Sink

from buildzr.dsl.interfaces import (
    DslWorkspaceElement,
    DslElement,
    DslViewElement,
    DslViewsElement,
    DslFluentSink,
    TSrc, TDst,
    TParent, TChild,
)
from buildzr.dsl.relations import (
    _is_software_fluent_relationship,
    _is_container_fluent_relationship,
    _Relationship,
    _RelationshipDescription,
    _FluentRelationship,
    DslElementRelationOverrides,
)

def _child_name_transform(name: str) -> str:
    return name.lower().replace(' ', '_')

TypedModel = TypeVar('TypedModel')
class TypedDynamicAttribute(Generic[TypedModel]):

    def __init__(self, dynamic_attributes: Dict[str, Any]) -> None:
        self._dynamic_attributes = dynamic_attributes

    def __getattr__(self, name: str) -> TypedModel:
        return cast(TypedModel, self._dynamic_attributes.get(name))

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

    def _contains_group(
        self,
        name: str,
        *models: Union[
            'Person',
            'SoftwareSystem',
            _FluentRelationship['SoftwareSystem'],
            _FluentRelationship['Container'],
        ]
    ) -> None:

        def recursive_group_name_assign(software_system: 'SoftwareSystem') -> None:
            software_system.model.group = name
            for container in software_system.children:
                container.model.group = name
                for component in container.children:
                    component.model.group = name

        for model in models:
            if isinstance(model, Person):
                model.model.group = name
            elif isinstance(model, SoftwareSystem):
                recursive_group_name_assign(model)
            elif _is_software_fluent_relationship(model):
                recursive_group_name_assign(model._parent)
            elif _is_container_fluent_relationship(model):
                recursive_group_name_assign(model._parent._parent)

        self.contains(*models)

    def contains(
        self,
        *models: Union[
            'Group',
            'Person',
            'SoftwareSystem',
            _FluentRelationship['SoftwareSystem'],
            _FluentRelationship['Container'],
        ]) -> _FluentRelationship['Workspace']:

        for model in models:
            if isinstance(model, Group):
                self._contains_group(model._name, *model._elements)
            elif isinstance(model, Person):
                self.add_element(model)
            elif isinstance(model, SoftwareSystem):
                self.add_element(model)
            elif _is_software_fluent_relationship(model):
                self.add_element(model._parent)
            elif _is_container_fluent_relationship(model):
                self.add_element(model._parent._parent)
        return _FluentRelationship['Workspace'](self)

    def person(self) -> TypedDynamicAttribute['Person']:
        return TypedDynamicAttribute['Person'](self._dynamic_attrs)

    def software_system(self) -> TypedDynamicAttribute['SoftwareSystem']:
        return TypedDynamicAttribute['SoftwareSystem'](self._dynamic_attrs)

    def add_element(self, element: Union['Person', 'SoftwareSystem']) -> None:
        if isinstance(element, Person):
            self._m.model.people.append(element._m)
            element._parent = self
            self._dynamic_attrs[_child_name_transform(element.model.name)] = element
            if element._label:
                self._dynamic_attrs[_child_name_transform(element._label)] = element
            self._children.append(element)
        elif isinstance(element, SoftwareSystem):
            self._m.model.softwareSystems.append(element._m)
            element._parent = self
            self._dynamic_attrs[_child_name_transform(element.model.name)] = element
            if element._label:
                self._dynamic_attrs[_child_name_transform(element._label)] = element
            self._children.append(element)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a workspace.'.format(type(element)))

    def with_views(
        self,
        *views: Union[
            'SystemLandscapeView',
            'SystemContextView',
            'ContainerView',
            'ComponentView',
        ]
    ) -> '_FluentSink':
        return Views(self).contains(*views)

    def __getattr__(self, name: str) -> Union['Person', 'SoftwareSystem']:
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> Union['Person', 'SoftwareSystem']:
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class SoftwareSystem(DslElementRelationOverrides[
    'SoftwareSystem',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component'
    ]
]):
    """
    A software system.
    """

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

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.SoftwareSystem()
        self._parent: Optional[Workspace] = None
        self._children: Optional[List['Container']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Software System'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Container'] = {}
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    def contains(
        self,
        *containers: Union['Container', _FluentRelationship['Container']]
    ) -> _FluentRelationship['SoftwareSystem']:
        if not self.model.containers:
            self.model.containers = []

        for child in containers:
            if isinstance(child, Container):
                self.add_element(child)
            elif _is_container_fluent_relationship(child):
                self.add_element(child._parent)
        return _FluentRelationship['SoftwareSystem'](self)

    def labeled(self, label: str) -> 'SoftwareSystem':
        self._label = label
        return self

    def container(self) -> TypedDynamicAttribute['Container']:
        return TypedDynamicAttribute['Container'](self._dynamic_attrs)

    def add_element(self, element: 'Container') -> None:
        if isinstance(element, Container):
            self.model.containers.append(element.model)
            element._parent = self
            self._dynamic_attrs[_child_name_transform(element.model.name)] = element
            if element._label:
                self._dynamic_attrs[_child_name_transform(element._label)] = element
            self._children.append(element)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a software system.'.format(type(element)))

    def __getattr__(self, name: str) -> 'Container':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Container':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class Person(DslElementRelationOverrides[
    'Person',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component'
    ]
]):
    """
    A person who uses a software system.
    """

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

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Person'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    def labeled(self, label: str) -> 'Person':
        self._label = label
        return self

class Container(DslElementRelationOverrides[
    'Container',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component'
    ]
]):
    """
    A container (something that can execute code or host data).
    """

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

    def contains(self, *components: 'Component') -> _FluentRelationship['Container']:
        if not self.model.components:
            self.model.components = []
        for component in components:
            self.add_element(component)
        return _FluentRelationship['Container'](self)

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Container()
        self._parent: Optional[SoftwareSystem] = None
        self._children: Optional[List['Component']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Container'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Component'] = {}
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.technology = technology
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    def labeled(self, label: str) -> 'Container':
        self._label = label
        return self

    def component(self) -> TypedDynamicAttribute['Component']:
        return TypedDynamicAttribute['Component'](self._dynamic_attrs)

    def add_element(self, element: 'Component') -> None:
        if isinstance(element, Component):
            self.model.components.append(element.model)
            element._parent = self
            self._dynamic_attrs[_child_name_transform(element.model.name)] = element
            if element._label:
                self._dynamic_attrs[_child_name_transform(element._label)] = element
            self._children.append(element)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a container.'.format(type(element)))

    def __getattr__(self, name: str) -> 'Component':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Component':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

class Component(DslElementRelationOverrides[
    'Component',
    Union[
        'Person',
        'SoftwareSystem',
        'Container',
        'Component'
    ]
]):
    """
    A component (a grouping of related functionality behind an interface that runs inside a container).
    """

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

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Component()
        self._parent: Optional[Container] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._tags = {'Element', 'Component'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.technology = technology
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

    def labeled(self, label: str) -> 'Component':
        self._label = label
        return self

class Group:

    def __init__(
        self,
        name: str,
        *elements: Union[
            Person,
            SoftwareSystem,
            _FluentRelationship[SoftwareSystem],
            _FluentRelationship[Container],
    ]) -> None:
        self._name = name
        self._elements = elements

class _FluentSink(DslFluentSink):

    def __init__(self, workspace: Workspace) -> None:
        self._workspace = workspace

    def to_json(self, path: str) -> None:
        from buildzr.sinks.json_sink import JsonSink, JsonSinkConfig
        sink = JsonSink()
        sink.write(workspace=self._workspace.model, config=JsonSinkConfig(path=path))

    def get_workspace(self) -> Workspace:
        return self._workspace

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

class SystemLandscapeView(DslViewElement):

    from buildzr.dsl.expression import Expression, Element, Relationship

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
        include_elements: List[Callable[[Workspace, Element], bool]]=[],
        exclude_elements: List[Callable[[Workspace, Element], bool]]=[],
        include_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        exclude_relationships: List[Callable[[Workspace, Relationship], bool]]=[],
        properties: Optional[Dict[str, str]]=None,
    ) -> None:
        self._m = buildzr.models.SystemLandscapeView()
        self._parent: Optional['Views'] = None

        self._m.key = key
        self._m.description = description

        self._m.automaticLayout = _auto_layout_to_model(auto_layout)
        self._m.title = title
        self._m.properties = properties

        self._include_elements = include_elements
        self._exclude_elements = exclude_elements
        self._include_relationships = include_relationships
        self._exclude_relationships = exclude_relationships

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        expression = Expression(
            include_elements=self._include_elements,
            exclude_elements=self._exclude_elements,
            include_relationships=self._include_relationships,
            exclude_relationships=self._exclude_relationships,
        )

        workspace = self._parent._parent

        include_view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e.type == Person,
            lambda w, e: e.type == SoftwareSystem
        ]

        exclude_view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e.type == Container,
            lambda w, e: e.type == Component,
        ]

        include_view_relationships_filter: List[Callable[[Workspace, Relationship], bool]] = [
            lambda w, r: r.source.type == Person,
            lambda w, r: r.source.type == SoftwareSystem,
            lambda w, r: r.destination.type == Person,
            lambda w, r: r.destination.type == SoftwareSystem,
        ]

        expression = Expression(
            include_elements=self._include_elements + include_view_elements_filter,
            exclude_elements=self._exclude_elements + exclude_view_elements_filter,
            include_relationships=self._include_relationships + include_view_relationships_filter,
            exclude_relationships=self._exclude_relationships,
        )

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

class SystemContextView(DslViewElement):

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

        software_system = self._selector(self._parent._parent)
        self._m.softwareSystemId = software_system.model.id
        view_elements_filter: List[Callable[[Workspace, Element], bool]] = [
            lambda w, e: e == software_system,
            lambda w, e: software_system.model.id in e.sources.ids,
            lambda w, e: software_system.model.id in e.destinations.ids,
        ]

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

class ContainerView(DslViewElement):

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

class ComponentView(DslViewElement):

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
        *views: DslViewElement
    ) -> _FluentSink:

        for view in views:
            if isinstance(view, SystemLandscapeView):
                view._parent = self
                view._on_added()
                if self._m.systemLandscapeViews:
                    self._m.systemLandscapeViews.append(view.model)
                else:
                    self._m.systemLandscapeViews = [view.model]
            elif isinstance(view, SystemContextView):
                view._parent = self
                view._on_added()
                if self._m.systemContextViews:
                    self._m.systemContextViews.append(view.model)
                else:
                    self._m.systemContextViews = [view.model]
            elif isinstance(view, ContainerView):
                view._parent = self
                view._on_added()
                if self._m.containerViews:
                    self._m.containerViews.append(view.model)
                else:
                    self._m.containerViews = [view.model]
            elif isinstance(view, ComponentView):
                view._parent = self
                view._on_added()
                if self._m.componentViews:
                    self._m.componentViews.append(view.model)
                else:
                    self._m.componentViews = [view.model]
            else:
                raise NotImplementedError("The view {0} is currently not supported", type(view))

        return _FluentSink(self._parent)

    def get_workspace(self) -> Workspace:
        """
        Get the `Workspace` which contain this views definition.
        """
        return self._parent