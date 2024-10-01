from abc import ABC, abstractmethod
from typing import (
    Optional,
    Union,
    TypeVar,
    Generic,
    List,
    Set,
    Tuple,
    Callable,
    overload,
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

class BindLeft(ABC, Generic[TSrc, TDst]):

    # Note: an abstraction of _UsesFrom

    @abstractmethod
    def __rshift__(self, destination: TDst) -> 'DslRelationship[TSrc, TDst]':
        pass


class BindRight(ABC, Generic[TSrc, TDst]):

    @overload
    @abstractmethod
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> BindLeft[TSrc, TDst]:
        ...

    @overload
    @abstractmethod
    def __rshift__(self, description: str) -> BindLeft[TSrc, TDst]:
        ...

    @abstractmethod
    def __rshift__(self, other: Union[str, Tuple[str, str]]) -> BindLeft[TSrc, TDst]:
        pass

class DslWorkspaceElement(ABC):

    @property
    @abstractmethod
    def model(self) -> buildzr.models.Workspace:
        pass

    @property
    @abstractmethod
    def parent(self) -> None:
        pass

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
    def tags(self) -> Set[str]:
        pass

    def uses(
        self,
        other: 'DslElement',
        description: Optional[str]=None,
        technology: Optional[str]=None,
        tags: Set[str]=set()) -> 'DslRelationship[Self, DslElement]':
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

class DslFluentRelationship(ABC, Generic[TParent, TChild]):

    @abstractmethod
    def where(self, func: Callable[..., List[DslRelationship]]) -> TParent:
        pass

    @abstractmethod
    def get(self) -> TParent:
        pass