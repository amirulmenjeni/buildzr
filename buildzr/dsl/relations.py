from typing import (
    Any,
    List,
    Tuple,
    Union,
    Set,
    Generic,
    Optional,
    Callable,
    Sequence,
    Dict,
    cast,
    overload,
)
from typing_extensions import Self, TypeIs
from dataclasses import dataclass
from buildzr.dsl.interfaces import (
    BindLeft,
    BindLeftLate,
    DslRelationship,
    DslFluentRelationship,
    DslElement,
    DslWorkspaceElement,
    TSrc, TDst,
    TParent, TChild,
)
from buildzr.dsl.factory import GenerateId
import buildzr

def _is_software_fluent_relationship(
    obj: '_FluentRelationship[Any]'
) -> TypeIs['_FluentRelationship[buildzr.dsl.SoftwareSystem]']:
    return isinstance(obj._parent, buildzr.dsl.SoftwareSystem)

def _is_container_fluent_relationship(
    obj: '_FluentRelationship[Any]'
) -> TypeIs['_FluentRelationship[buildzr.dsl.Container]']:
    return isinstance(obj._parent, buildzr.dsl.Container)

@dataclass
class With:
    tags: Optional[Set[str]] = None
    properties: Optional[Dict[str, str]] = None
    url: Optional[str] = None

@dataclass
class _UsesData(Generic[TSrc]):
    relationship: buildzr.models.Relationship
    source: TSrc

def desc(value: str, tech: Optional[str]=None) -> '_RelationshipDescription[DslElement]':
    if tech is None:
        return _RelationshipDescription(value)
    else:
        return _RelationshipDescription(value, tech)

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
        if isinstance(destination, DslWorkspaceElement):
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

class _FluentRelationship(DslFluentRelationship[TParent]):

    """
    A hidden class used in the fluent DSL syntax after specifying a model (i.e.,
    Person, Software System, Container) to define relationship(s) within the
    specified model.
    """

    def __init__(self, parent: TParent) -> None:
        self._parent: TParent = parent

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
        ], implied: bool=False) -> TParent:

        relationships: Sequence[DslRelationship] = []

        func = cast(Callable[[TParent], Sequence[Union[DslRelationship, Sequence[DslRelationship]]]], func)

        # Flatten the resulting relationship list.
        relationships = [
            rel for sublist in func(self._parent)
            for rel in (
                sublist if isinstance(sublist, list) else [sublist]
            )
        ]

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

class _RelationshipDescription(Generic[TDst]):

    def __init__(self, description: str, technology: Optional[str]=None) -> None:
        self._description = description
        self._technology = technology

    def __rshift__(self, destination: TDst) -> '_UsesFromLate[TDst]':
        if self._technology:
            return _UsesFromLate(
                description=(self._description, self._technology),
                destination=destination,
            )
        return _UsesFromLate(
            description=self._description,
            destination=destination,
        )

class _UsesFromLate(BindLeftLate[TDst]):
    """
    This method is used to create a relationship between one source element with
    multiple destination elements, like so:

    ```python
    u = Person("user")
    s1 = SoftwareSystem("software1")
    s2 = SoftwareSystem("software2")

    # Each element in the following list is a `_UsesFromLate` object.
    u >> [
        "Uses" >> s1 | With(tags={"linux", "rules"}),
        ("Reads from", "SQL") >> s1,
    ]
    ```

    This requires late left binding (i.e., the source element is bound after the
    the destination elements in the list are bounded. This is in contrast to how
    `_UsesFrom` works, where `u >> "Uses >> s1` binds the source element `u`
    first (i.e., in `u >> "Uses"` into `_UsesFrom` before finally binding `s1`
    in `((u >> "Uses) >> s2)`).
    """

    PossibleSourceType = Optional[DslElement]

    @dataclass
    class _LateBindData:
        tags: Optional[Set[str]] = None
        properties: Optional[Dict[str, str]] = None
        url: Optional[str] = None

    def __init__(self, description: Union[str, Tuple[str, str]], destination: TDst) -> None:
        if isinstance(description, str):
            self._description = description
            self._technology: Optional[str] = None
        elif isinstance(description, tuple) and len(description) == 2:
            self._description = description[0]
            self._technology = description[1]
        self._source: Optional[_UsesFromLate.PossibleSourceType] = None
        self._destination = destination
        self._relationship: Optional[_Relationship[_UsesFromLate.PossibleSourceType, TDst]] = None
        self._late_bind_data: _UsesFromLate._LateBindData = _UsesFromLate._LateBindData()

    def set_source(self, source: PossibleSourceType) -> None:
        self._source = source
        self._relationship =  _Relationship(
            uses_data=_UsesData(
                relationship=buildzr.models.Relationship(
                    id=GenerateId.for_relationship(),
                    description=self._description,
                    technology=self._technology,
                    sourceId=str(self._source.model.id),
                ),
                source=self._source,
            ),
            destination=self._destination,
        )
        self._late_bind_with()

    def get_relationship(self) -> Optional['_Relationship[PossibleSourceType, TDst]']:
        return self._relationship

    def _late_bind_with(self) -> None:
        """
        Binds tags, properties, url to the relationship.
        Called once the relationship is set.
        """
        self._relationship = self._relationship.has(
            tags=self._late_bind_data.tags,
            properties=self._late_bind_data.properties,
            url=self._late_bind_data.url,
        )


    def __or__(self, other: With) -> Self:
        self._late_bind_data.tags = other.tags
        self._late_bind_data.properties = other.properties
        self._late_bind_data.url = other.url

        return self

class DslElementRelationOverrides(DslElement):

    """
    Base class meant to be derived from to override the `__rshift__` method to
    allow for the `>>` operator to be used to create relationships between
    elements.
    """

    @overload # type: ignore[override]
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, DslElement]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, DslElement]:
        ...

    @overload
    def __rshift__(self, _RelationshipDescription: _RelationshipDescription[DslElement]) -> _UsesFrom[Self, DslElement]:
        ...

    @overload
    def __rshift__(self, multiple_destinations: List[_UsesFromLate[DslElement]]) -> List[_Relationship[Self, DslElement]]:
        ...

    def __rshift__(
            self,
            other: Union[
                str,
                Tuple[str, str],
                _RelationshipDescription[DslElement],
                List[_UsesFromLate[DslElement]]
            ]) -> Union[_UsesFrom[Self, DslElement], List[_Relationship[Self, DslElement]]]:
        if isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        elif isinstance(other, _RelationshipDescription):
            return _UsesFrom(self, description=other._description, technology=other._technology)
        elif isinstance(other, list):
            relationships = []
            for dest in other:
                dest.set_source(self)
                relationships.append(dest.get_relationship())
            return cast(List[_Relationship[Self, DslElement]], relationships)
        else:
            raise TypeError(f"Unsupported operand type for >>: '{type(self).__name__}' and {type(other).__name__}")

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