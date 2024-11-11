from abc import ABC, abstractmethod
from typing import (
    Any,
    Optional,
    Union,
    TypeVar,
    Generic,
    List,
    Set,
    Tuple,
    Callable,
    overload,
    Sequence,
    cast,
)
from typing_extensions import (
    Self
)
import buildzr

Model = Union[
    buildzr.models.Workspace,
    buildzr.models.Person,
    buildzr.models.SoftwareSystem,
    buildzr.models.Container,
    buildzr.models.Component,
]

TSrc = TypeVar('TSrc', bound='DslElement', contravariant=True)
TDst = TypeVar('TDst', bound='DslElement', contravariant=True)

TParent = TypeVar('TParent', bound=Union['DslWorkspaceElement', 'DslElement'], covariant=True)
TChild = TypeVar('TChild', bound='DslElement', contravariant=True)

class BindLeftLate(ABC, Generic[TDst]):

    @abstractmethod
    def set_source(self, source: Any) -> None:
        pass

    @abstractmethod
    def get_relationship(self) -> 'Optional[DslRelationship[Any, TDst]]':
        pass

class BindLeft(ABC, Generic[TSrc, TDst]):

    # Note: an abstraction of _UsesFrom

    @abstractmethod
    def __rshift__(self, destination: TDst) -> 'DslRelationship[TSrc, TDst]':
        pass

class BindRight(ABC, Generic[TSrc, TDst]):

    @overload
    @abstractmethod
    def __rshift__(self, other: TDst) -> 'DslRelationship[TSrc, TDst]':
        ...

    @overload
    @abstractmethod
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> BindLeft[TSrc, TDst]:
        ...

    @overload
    @abstractmethod
    def __rshift__(self, description: str) -> BindLeft[TSrc, TDst]:
        ...

    @overload
    @abstractmethod
    def __rshift__(self, multiple_destinations: List[Union[TDst, BindLeftLate[TDst]]]) -> 'List[DslRelationship[TSrc, TDst]]':
        ...

    @abstractmethod
    def __rshift__(self, other: Union[TDst, str, Tuple[str, str], List[Union[TDst, BindLeftLate[TDst]]]]) -> Union[BindLeft[TSrc, TDst], 'DslRelationship[TSrc, TDst]', 'List[DslRelationship[TSrc, TDst]]']:
        ...

class DslWorkspaceElement(ABC):

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Workspace:
        pass

    @property
    @abstractmethod
    def parent(self) -> None:
        pass

    @property
    @abstractmethod
    def children(self) -> Optional[Sequence['DslElement']]:
        pass

    def __contains__(self, other: 'DslElement') -> bool:
        return self.model.id == other.parent.model.id

class DslElement(BindRight[TSrc, TDst]):
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
    def parent(self) -> Union[None, DslWorkspaceElement, 'DslElement']:
        pass

    @property
    @abstractmethod
    def children(self) -> Union[None, Sequence['DslElement']]:
        pass

    @property
    @abstractmethod
    def sources(self) -> List['DslElement']:
        pass

    @property
    @abstractmethod
    def destinations(self) -> List['DslElement']:
        pass

    @property
    @abstractmethod
    def tags(self) -> Set[str]:
        pass

    def uses(
        self,
        other: 'DslElement',
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> 'DslRelationship[Self, DslElement]':
        pass

    def __contains__(self, other: 'DslElement') -> bool:
        return self.model.id == other.parent.model.id

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

    def __contains__(self, other: 'DslElement') -> bool:
        return self.source.model.id == other.model.id or self.destination.model.id == other.model.id

class DslFluentRelationship(ABC, Generic[TParent]):

    """
    The abstract class that defines the interface for the fluent relationship
    definition, where the one or more relationships between elements accessible
    from the `TParent` element.
    """

    @abstractmethod
    def where(
        self,
        func: Callable[
            [TParent],
            Sequence[
                Union[
                    DslRelationship,
                    Sequence[DslRelationship]
                ]
            ]
        ]) -> TParent:
        pass

    @abstractmethod
    def get(self) -> TParent:
        pass

class DslFluentSink(ABC):

    @abstractmethod
    def to_json(self, path: str) -> None:
        pass

class DslViewElement(ABC):

    ViewModel = Union[
        buildzr.models.SystemLandscapeView,
        buildzr.models.SystemContextView,
        buildzr.models.ContainerView,
        buildzr.models.ComponentView,
        buildzr.models.DynamicView,
        buildzr.models.DeploymentView,
    ]

    @property
    @abstractmethod
    def model(self) -> ViewModel:
        pass

    @property
    @abstractmethod
    def parent(self) -> 'DslViewsElement':
        pass

    def _on_added(self) -> None:
        pass

class DslViewsElement(ABC):

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Views:
        pass

    @property
    @abstractmethod
    def parent(self) -> DslWorkspaceElement:
        pass

    @abstractmethod
    def contains(
        self,
        *views: Union[DslViewElement],
    ) -> DslFluentSink:
        pass