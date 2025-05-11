from dataclasses import dataclass
import buildzr
from .factory import GenerateId
from typing_extensions import (
    Self,
    TypeIs,
)
from collections import deque
from contextvars import ContextVar
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
    Callable,
    Iterable,
    Literal,
    cast,
    Type,
)

from buildzr.sinks.interfaces import Sink
from buildzr.dsl.interfaces import (
    DslWorkspaceElement,
    DslElement,
    DslViewElement,
    DslViewsElement,
)
from buildzr.dsl.relations import (
    DslElementRelationOverrides,
    DslRelationship,
    _Relationship,
)
from buildzr.dsl.color import Color

def _child_name_transform(name: str) -> str:
    return name.lower().replace(' ', '_')

TypedModel = TypeVar('TypedModel')
class TypedDynamicAttribute(Generic[TypedModel]):

    def __init__(self, dynamic_attributes: Dict[str, Any]) -> None:
        self._dynamic_attributes = dynamic_attributes

    def __getattr__(self, name: str) -> TypedModel:
        return cast(TypedModel, self._dynamic_attributes.get(name))

_current_workspace: ContextVar[Optional['Workspace']] = ContextVar('current_workspace', default=None)
_current_group_stack: ContextVar[List['Group']] = ContextVar('current_group', default=[])
_current_software_system: ContextVar[Optional['SoftwareSystem']] = ContextVar('current_software_system', default=None)
_current_container: ContextVar[Optional['Container']] = ContextVar('current_container', default=None)

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

    def __init__(
            self,
            name: str,
            description: str="",
            scope: Literal['landscape', 'software_system', None]='software_system',
            implied_relationships: bool=False,
            group_separator: str='/',
        ) -> None:

        self._m = buildzr.models.Workspace()
        self._parent = None
        self._children: Optional[List[Union['Person', 'SoftwareSystem']]] = []
        self._dynamic_attrs: Dict[str, Union['Person', 'SoftwareSystem']] = {}
        self._use_implied_relationships = implied_relationships
        self._group_separator = group_separator
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

        self.model.model.properties = {
            'structurizr.groupSeparator': group_separator,
        }

    def __enter__(self) -> Self:
        self._token = _current_workspace.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:

        from buildzr.dsl.explorer import Explorer

        # Process implied relationships:
        # If we have relationship s >> do >> a.b, then create s >> do >> a.
        # If we have relationship s.ss >> do >> a.b.c, then create s.ss >> do >> a.b and s.ss >> do >> a.
        # And so on...
        if self._use_implied_relationships:
            explorer = Explorer(self)
            relationships = list(explorer.walk_relationships())
            for relationship in relationships:
                source = relationship.source
                destination = relationship.destination
                destination_parent = destination.parent

                while destination_parent is not None and \
                      isinstance(source, DslElement) and \
                      not isinstance(source.model, buildzr.models.Workspace) and \
                      not isinstance(destination_parent, DslWorkspaceElement):

                    if destination_parent is source.parent:
                        break

                    rels = source.model.relationships

                    if rels:
                        already_exists = any(
                            r.destinationId == destination_parent.model.id and
                            r.description == relationship.model.description and
                            r.technology == relationship.model.technology
                            for r in rels
                        )
                        if not already_exists:
                            r = source.uses(
                                destination_parent,
                                description=relationship.model.description,
                                technology=relationship.model.technology,
                            )
                            r.model.linkedRelationshipId = relationship.model.id
                        destination_parent = destination_parent.parent

        _current_workspace.reset(self._token)

    def person(self) -> TypedDynamicAttribute['Person']:
        return TypedDynamicAttribute['Person'](self._dynamic_attrs)

    def software_system(self) -> TypedDynamicAttribute['SoftwareSystem']:
        return TypedDynamicAttribute['SoftwareSystem'](self._dynamic_attrs)

    def add_model(self, model: Union['Person', 'SoftwareSystem']) -> None:
        if isinstance(model, Person):
            self._m.model.people.append(model._m)
            model._parent = self
            self._add_dynamic_attr(model.model.name, model)
            self._children.append(model)
        elif isinstance(model, SoftwareSystem):
            self._m.model.softwareSystems.append(model._m)
            model._parent = self
            self._add_dynamic_attr(model.model.name, model)
            self._children.append(model)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a workspace.'.format(type(model)))

    def apply_views( self, *views: Union[ 'SystemLandscapeView',
            'SystemContextView',
            'ContainerView',
            'ComponentView',
        ]
    ) -> None:
        Views(self).add_views(*views)

    def apply_style( self,
        style: Union['StyleElements', 'StyleRelationships'],
    ) -> None:

        style._parent = self

        if not self.model.views:
            self.model.views = buildzr.models.Views()
        if not self.model.views.configuration:
            self.model.views.configuration = buildzr.models.Configuration()
        if not self.model.views.configuration.styles:
            self.model.views.configuration.styles = buildzr.models.Styles()

        if isinstance(style, StyleElements):
            if self.model.views.configuration.styles.elements:
                self.model.views.configuration.styles.elements.extend(style.model)
            else:
                self.model.views.configuration.styles.elements = style.model
        elif isinstance(style, StyleRelationships):
            if self.model.views.configuration.styles.relationships:
                self.model.views.configuration.styles.relationships.extend(style.model)
            else:
                self.model.views.configuration.styles.relationships = style.model

    def to_json(self, path: str) -> None:
        from buildzr.sinks.json_sink import JsonSink, JsonSinkConfig
        sink = JsonSink()
        sink.write(workspace=self.model, config=JsonSinkConfig(path=path))

    def _add_dynamic_attr(self, name: str, model: Union['Person', 'SoftwareSystem']) -> None:
        if isinstance(model, Person):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        elif isinstance(model, SoftwareSystem):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a workspace.'.format(type(model)))

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
    def relationships(self) -> Set[_Relationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.SoftwareSystem()
        self.model.containers = []
        self._parent: Optional[Workspace] = None
        self._children: Optional[List['Container']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[_Relationship] = set()
        self._tags = {'Element', 'Software System'}.union(tags)
        self._dynamic_attrs: Dict[str, 'Container'] = {}
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.add_model(self)
            workspace._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def __enter__(self) -> Self:
        self._token = _current_software_system.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:
        _current_software_system.reset(self._token)

    def container(self) -> TypedDynamicAttribute['Container']:
        return TypedDynamicAttribute['Container'](self._dynamic_attrs)

    def add_container(self, container: 'Container') -> None:
        if isinstance(container, Container):
            self.model.containers.append(container.model)
            container._parent = self
            self._add_dynamic_attr(container.model.name, container)
            self._children.append(container)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a software system.'.format(type(container)))

    def _add_dynamic_attr(self, name: str, model: 'Container') -> None:
        if isinstance(model, Container):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a software system.'.format(type(model)))

    def __getattr__(self, name: str) -> 'Container':
        return self._dynamic_attrs[name]

    def __getitem__(self, name: str) -> 'Container':
        return self._dynamic_attrs[_child_name_transform(name)]

    def __dir__(self) -> Iterable[str]:
        return list(super().__dir__()) + list(self._dynamic_attrs.keys())

    def labeled(self, label: str) -> 'SoftwareSystem':
        self._label = label
        workspace = _current_workspace.get()
        if workspace is not None:
            workspace._add_dynamic_attr(label, self)
        return self

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
    def relationships(self) -> Set[_Relationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Person()
        self._parent: Optional[Workspace] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[_Relationship] = set()
        self._tags = {'Element', 'Person'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.add_model(self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def labeled(self, label: str) -> 'Person':
        self._label = label
        workspace = _current_workspace.get()
        if workspace is not None:
            workspace._add_dynamic_attr(label, self)
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
    def relationships(self) -> Set[_Relationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Container()
        self.model.components = []
        self._parent: Optional[SoftwareSystem] = None
        self._children: Optional[List['Component']] = []
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[_Relationship] = set()
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

        software_system = _current_software_system.get()
        if software_system is not None:
            software_system.add_container(self)
            software_system._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def __enter__(self) -> Self:
        self._token = _current_container.set(self)
        return self

    def __exit__(self, exc_type: Optional[Type[BaseException]], exc_value: Optional[BaseException], traceback: Optional[Any]) -> None:
        _current_container.reset(self._token)

    def labeled(self, label: str) -> 'Container':
        self._label = label
        software_system = _current_software_system.get()
        if software_system is not None:
            software_system._add_dynamic_attr(label, self)
        return self

    def component(self) -> TypedDynamicAttribute['Component']:
        return TypedDynamicAttribute['Component'](self._dynamic_attrs)

    def add_component(self, component: 'Component') -> None:
        if isinstance(component, Component):
            self.model.components.append(component.model)
            component._parent = self
            self._add_dynamic_attr(component.model.name, component)
            self._children.append(component)
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a container.'.format(type(component)))

    def _add_dynamic_attr(self, name: str, model: 'Component') -> None:
        if isinstance(model, Component):
            self._dynamic_attrs[_child_name_transform(name)] = model
            if model._label:
                self._dynamic_attrs[_child_name_transform(model._label)] = model
        else:
            raise ValueError('Invalid element type: Trying to add an element of type {} to a container.'.format(type(model)))

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
    def relationships(self) -> Set[_Relationship]:
        return self._relationships

    @property
    def tags(self) -> Set[str]:
        return self._tags

    def __init__(self, name: str, description: str="", technology: str="", tags: Set[str]=set(), properties: Dict[str, Any]=dict()) -> None:
        self._m = buildzr.models.Component()
        self._parent: Optional[Container] = None
        self._sources: List[DslElement] = []
        self._destinations: List[DslElement] = []
        self._relationships: Set[_Relationship] = set()
        self._tags = {'Element', 'Component'}.union(tags)
        self._label: Optional[str] = None
        self.model.id = GenerateId.for_element()
        self.model.name = name
        self.model.description = description
        self.model.technology = technology
        self.model.relationships = []
        self.model.tags = ','.join(self._tags)
        self.model.properties = properties

        container = _current_container.get()
        if container is not None:
            container.add_component(self)
            container._add_dynamic_attr(self.model.name, self)

        stack = _current_group_stack.get()
        if stack:
            stack[-1].add_element(self)

    def labeled(self, label: str) -> 'Component':
        self._label = label
        container = _current_container.get()
        if container is not None:
            container._add_dynamic_attr(label, self)
        return self

class Group:

    def __init__(
        self,
        name: str,
        workspace: Optional[Workspace]=None,
    ) -> None:

        if not workspace:
            workspace = _current_workspace.get()
            if workspace is not None:
                self._group_separator = workspace._group_separator

        self._group_separator = workspace._group_separator
        self._name = name

        if len(self._group_separator) > 1:
            raise ValueError('Group separator must be a single character.')

        if self._group_separator in self._name:
            raise ValueError('Group name cannot contain the group separator.')

        stack = _current_group_stack.get()
        new_stack = stack.copy()
        new_stack.extend([self])

        self._full_name = self._group_separator.join([group._name for group in new_stack])

    def full_name(self) -> str:
        return self._full_name

    def add_element(
        self,
        model: Union[
            'Person',
            'SoftwareSystem',
            'Container',
            'Component',
        ]
    ) -> None:


        model.model.group = self._full_name

    def __enter__(self) -> Self:
        stack = _current_group_stack.get() # stack: a/b
        stack.extend([self]) # stack: a/b -> a/b/self
        self._token = _current_group_stack.set(stack)
        return self

    def __exit__(
        self,
        exc_type: Optional[Type[BaseException]],
        exc_value: Optional[BaseException],
        traceback: Optional[Any]
    ) -> None:
        stack = _current_group_stack.get()
        stack.pop() # stack: a/b/self -> a/b
        _current_group_stack.reset(self._token)

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
        include_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
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

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_views(self)

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

        include_view_elements_filter: List[Union[DslElement, Callable[[Workspace, Element], bool]]] = [
            lambda w, e: e.type == Person,
            lambda w, e: e.type == SoftwareSystem
        ]

        exclude_view_elements_filter: List[Union[DslElement, Callable[[Workspace, Element], bool]]] = [
            lambda w, e: e.type == Container,
            lambda w, e: e.type == Component,
        ]

        include_view_relationships_filter: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]] = [
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
        software_system_selector: Union[SoftwareSystem, Callable[[Workspace], SoftwareSystem]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
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

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_views(self)

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        if isinstance(self._selector, SoftwareSystem):
            software_system = self._selector
        else:
            software_system = self._selector(self._parent._parent)
        self._m.softwareSystemId = software_system.model.id
        view_elements_filter: List[Union[DslElement, Callable[[Workspace, Element], bool]]] = [
            lambda w, e: e == software_system,
            lambda w, e: software_system.model.id in e.sources.ids,
            lambda w, e: software_system.model.id in e.destinations.ids,
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]] = [
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
        software_system_selector: Union[SoftwareSystem, Callable[[Workspace], SoftwareSystem]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
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

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_views(self)

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        if isinstance(self._selector, SoftwareSystem):
            software_system = self._selector
        else:
            software_system = self._selector(self._parent._parent)
        self._m.softwareSystemId = software_system.model.id

        container_ids = { container.model.id for container in software_system.children}

        view_elements_filter: List[Union[DslElement, Callable[[Workspace, Element], bool]]] = [
            lambda w, e: e.parent == software_system,
            lambda w, e: any(container_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(container_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]] = [
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
        container_selector: Union[Container, Callable[[Workspace], Container]],
        key: str,
        description: str,
        auto_layout: _AutoLayout='tb',
        title: Optional[str]=None,
        include_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        exclude_elements: List[Union[DslElement, Callable[[Workspace, Element], bool]]]=[],
        include_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
        exclude_relationships: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]]=[],
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

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_views(self)

    def _on_added(self) -> None:

        from buildzr.dsl.expression import Expression, Element, Relationship
        from buildzr.models import ElementView, RelationshipView

        if isinstance(self._selector, Container):
            container = self._selector
        else:
            container = self._selector(self._parent._parent)
        self._m.containerId = container.model.id

        component_ids = { component.model.id for component in container.children }

        view_elements_filter: List[Union[DslElement, Callable[[Workspace, Element], bool]]] = [
            lambda w, e: e.parent == container,
            lambda w, e: any(component_ids.intersection({ id for id in e.sources.ids })),
            lambda w, e: any(component_ids.intersection({ id for id in e.destinations.ids })),
        ]

        view_relationships_filter: List[Union[DslElement, Callable[[Workspace, Relationship], bool]]] = [
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

    # TODO: Make this view a "hidden" class -- it's not a "first class citizen"
    # in buildzr DSL.

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

    def add_views(
        self,
        *views: DslViewElement
    ) -> None:

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

    def get_workspace(self) -> Workspace:
        """
        Get the `Workspace` which contain this views definition.
        """
        return self._parent

class StyleElements:

    from buildzr.dsl.expression import Element

    Shapes = Union[
        Literal['Box'],
        Literal['RoundedBox'],
        Literal['Circle'],
        Literal['Ellipse'],
        Literal['Hexagon'],
        Literal['Cylinder'],
        Literal['Pipe'],
        Literal['Person'],
        Literal['Robot'],
        Literal['Folder'],
        Literal['WebBrowser'],
        Literal['MobileDevicePortrait'],
        Literal['MobileDeviceLandscape'],
        Literal['Component'],
    ]

    @property
    def model(self) -> List[buildzr.models.ElementStyle]:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    # TODO: Validate arguments with pydantic.
    def __init__(
            self,
            on: List[Union[
                DslElement,
                Group,
                Callable[[Workspace, Element], bool],
                Type[Union['Person', 'SoftwareSystem', 'Container', 'Component']],
                str
            ]],
            shape: Optional[Shapes]=None,
            icon: Optional[str]=None,
            width: Optional[int]=None,
            height: Optional[int]=None,
            background: Optional[Union['str', Tuple[int, int, int], Color]]=None,
            color: Optional[Union['str', Tuple[int, int, int], Color]]=None,
            stroke: Optional[Union[str, Tuple[int, int, int], Color]]=None,
            stroke_width: Optional[int]=None,
            font_size: Optional[int]=None,
            border: Optional[Literal['solid', 'dashed', 'dotted']]=None,
            opacity: Optional[int]=None,
            metadata: Optional[bool]=None,
            description: Optional[bool]=None,
    ) -> None:

        # How the tag is populated depends on each element type in the
        # `elemenets`.
        # - If the element is a `DslElement`, then we create a unique tag
        #   specifically to help the stylizer identify that specific element.
        #   For example, if the element has an id `3`, then we should create a
        #   tag, say, `style-element-3`.
        # - If the element is a `Group`, then we simply make create the tag
        #   based on the group name and its nested path. For example,
        #   `Group:Company 1/Department 1`.
        # - If the element is a `Callable[[Workspace, Element], bool]`, we just
        #   run the function to filter out all the elements that matches the
        #   description, and create a unique tag for all of the filtered
        #   elements.
        # - If the element is a `Type[Union['Person', 'SoftwareSystem', 'Container', 'Component']]`,
        #   we create a tag based on the class name. This is based on the fact
        #   that the default tag for each element is the element's type.
        # - If the element is a `str`, we just use the string as the tag.
        #   This is useful for when you want to apply a style to all elements
        #   with a specific tag, just like in the original Structurizr DSL.
        #
        # Note that a new `buildzr.models.ElementStyle` is created for each
        # item, not for each of `StyleElements` instance. This makes the styling
        # makes more concise and flexible.

        from buildzr.dsl.expression import Element
        from uuid import uuid4

        if background:
            assert Color.is_valid_color(background), "Invalid background color: {}".format(background)
        if color:
            assert Color.is_valid_color(color), "Invalid color: {}".format(color)
        if stroke:
            assert Color.is_valid_color(stroke), "Invalid stroke color: {}".format(stroke)

        self._m: List[buildzr.models.ElementStyle] = []
        self._parent: Optional[Workspace] = None

        workspace = _current_workspace.get()
        if workspace is not None:
            self._parent = workspace

        self._elements = on

        border_enum: Dict[str, buildzr.models.Border] = {
            'solid': buildzr.models.Border.Solid,
            'dashed': buildzr.models.Border.Dashed,
            'dotted': buildzr.models.Border.Dotted,
        }

        shape_enum: Dict[str, buildzr.models.Shape] = {
            'Box': buildzr.models.Shape.Box,
            'RoundedBox': buildzr.models.Shape.RoundedBox,
            'Circle': buildzr.models.Shape.Circle,
            'Ellipse': buildzr.models.Shape.Ellipse,
            'Hexagon': buildzr.models.Shape.Hexagon,
            'Cylinder': buildzr.models.Shape.Cylinder,
            'Pipe': buildzr.models.Shape.Pipe,
            'Person': buildzr.models.Shape.Person,
            'Robot': buildzr.models.Shape.Robot,
            'Folder': buildzr.models.Shape.Folder,
            'WebBrowser': buildzr.models.Shape.WebBrowser,
            'MobileDevicePortrait': buildzr.models.Shape.MobileDevicePortrait,
            'MobileDeviceLandscape': buildzr.models.Shape.MobileDeviceLandscape,
            'Component': buildzr.models.Shape.Component,
        }

        # A single unique element to be applied to all elements
        # affected by this style.
        element_tag = "buildzr-styleelements-{}".format(uuid4().hex)

        for element in self._elements:

            element_style = buildzr.models.ElementStyle()
            element_style.shape = shape_enum[shape] if shape else None
            element_style.icon = icon
            element_style.width = width
            element_style.height = height
            element_style.background = Color(background).to_hex() if background else None
            element_style.color = Color(color).to_hex() if color else None
            element_style.stroke = Color(stroke).to_hex() if stroke else None
            element_style.strokeWidth = stroke_width
            element_style.fontSize = font_size
            element_style.border = border_enum[border] if border else None
            element_style.opacity = opacity
            element_style.metadata = metadata
            element_style.description = description

            if isinstance(element, DslElement) and not isinstance(element.model, buildzr.models.Workspace):
                element_style.tag = element_tag
                element.add_tags(element_tag)
            elif isinstance(element, Group):
                element_style.tag = f"Group:{element.full_name()}"
            elif isinstance(element, type):
                element_style.tag = f"{element.__name__}"
            elif isinstance(element, str):
                element_style.tag = element
            elif callable(element):
                from buildzr.dsl.expression import Element, Expression
                if self._parent:
                    matched_elems = Expression(include_elements=[element]).elements(self._parent)
                    for e in matched_elems:
                        element_style.tag = element_tag
                        e.add_tags(element_tag)
                else:
                    raise ValueError("Cannot use callable to select elements to style without a Workspace.")
            self._m.append(element_style)

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_style(self)

class StyleRelationships:

    from buildzr.dsl.expression import Relationship

    @property
    def model(self) -> List[buildzr.models.RelationshipStyle]:
        return self._m

    @property
    def parent(self) -> Optional[Workspace]:
        return self._parent

    def __init__(
        self,
        on: Optional[List[Union[
            DslRelationship,
            Group,
            Callable[[Workspace, Relationship], bool],
            str
        ]]]=None,
        thickness: Optional[int]=None,
        color: Optional[Union[str, Tuple[int, int, int], Color]]=None,
        routing: Optional[Literal['Direct', 'Orthogonal', 'Curved']]=None,
        font_size: Optional[int]=None,
        width: Optional[int]=None,
        dashed: Optional[bool]=None,
        position: Optional[int]=None,
        opacity: Optional[int]=None,
    ) -> None:

        from uuid import uuid4

        if color is not None:
            assert Color.is_valid_color(color), "Invalid color: {}".format(color)

        routing_enum: Dict[str, buildzr.models.Routing1] = {
            'Direct': buildzr.models.Routing1.Direct,
            'Orthogonal': buildzr.models.Routing1.Orthogonal,
            'Curved': buildzr.models.Routing1.Curved,
        }

        self._m: List[buildzr.models.RelationshipStyle] = []
        self._parent: Optional[Workspace] = None

        workspace = _current_workspace.get()
        if workspace is not None:
            self._parent = workspace

        # A single unique tag to be applied to all relationships
        # affected by this style.
        relation_tag = "buildzr-stylerelationships-{}".format(uuid4().hex)

        if on is None:
            self._m.append(buildzr.models.RelationshipStyle(
                thickness=thickness,
                color=Color(color).to_hex() if color else None,
                routing=routing_enum[routing] if routing else None,
                fontSize=font_size,
                width=width,
                dashed=dashed,
                position=position,
                opacity=opacity,
                tag="Relationship",
            ))
        else:
            for relationship in on:

                relationship_style = buildzr.models.RelationshipStyle()
                relationship_style.thickness = thickness
                relationship_style.color = Color(color).to_hex() if color else None
                relationship_style.routing = routing_enum[routing] if routing else None
                relationship_style.fontSize = font_size
                relationship_style.width = width
                relationship_style.dashed = dashed
                relationship_style.position = position
                relationship_style.opacity = opacity

                if isinstance(relationship, DslRelationship):
                    relationship.add_tags(relation_tag)
                    relationship_style.tag = relation_tag
                elif isinstance(relationship, Group):
                    from buildzr.dsl.expression import Expression
                    if self._parent:
                        rels = Expression(include_relationships=[
                            lambda w, r: r.source.group == relationship.full_name() and \
                                         r.destination.group == relationship.full_name()
                        ]).relationships(self._parent)
                        for r in rels:
                            r.add_tags(relation_tag)
                        relationship_style.tag = relation_tag
                    else:
                        raise ValueError("Cannot use callable to select elements to style without a Workspace.")
                elif isinstance(relationship, str):
                    relationship_style.tag = relationship
                elif callable(relationship):
                    from buildzr.dsl.expression import Expression
                    if self._parent:
                        matched_rels = Expression(include_relationships=[relationship]).relationships(self._parent)
                        for matched_rel in matched_rels:
                            matched_rel.add_tags(relation_tag)
                            relationship_style.tag = relation_tag
                    else:
                        raise ValueError("Cannot use callable to select elements to style without a Workspace.")
                self._m.append(relationship_style)

        workspace = _current_workspace.get()
        if workspace is not None:
            workspace.apply_style(self)