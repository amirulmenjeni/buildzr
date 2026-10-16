from typing import (
    Any,
    List,
    Tuple,
    Union,
    Set,
    Generic,
    Optional,
    Callable,
    AbstractSet,
    TypeVar,
    Iterable,
    Iterator,
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
    DslElement,
    DslWorkspaceElement,
    TSrc, TDst,
)
from buildzr.dsl.factory import GenerateId
import buildzr

T = TypeVar('T')


class OrderedSet(Set[T]):
    """A ``set`` that iterates in insertion order (used for tags and relationships).

    Subclasses ``set`` so the public ``Set[str]`` type of ``tags`` is unchanged,
    but ``__iter__`` follows a side ``dict``. ``','.join(tags)`` is therefore
    independent of ``PYTHONHASHSEED``.
    """

    def __init__(self, *iterables: Iterable[T]) -> None:
        super().__init__()
        self._order: Dict[T, None] = {}
        for it in iterables:
            self.update(it)

    def __iter__(self) -> Iterator[T]:
        return iter(self._order)

    def add(self, item: T) -> None:
        super().add(item)
        self._order.setdefault(item, None)

    def update(self, *others: Iterable[T]) -> None:
        for other in others:
            # A plain set/frozenset has no order of its own: sort it so the
            # result does not depend on PYTHONHASHSEED. Ordered inputs
            # (list, tuple, OrderedTags, dict) keep their order.
            items = sorted(other) if type(other) in (set, frozenset) and all(isinstance(i, str) for i in other) else other  # type: ignore[type-var]
            for item in items:
                self.add(item)

    def discard(self, item: T) -> None:
        super().discard(item)
        self._order.pop(item, None)

    def remove(self, item: T) -> None:
        super().remove(item)
        self._order.pop(item, None)

    def pop(self) -> T:
        item = next(iter(self._order))
        self.remove(item)
        return item

    def clear(self) -> None:
        super().clear()
        self._order.clear()

    def union(self, *others: Iterable[T]) -> 'OrderedSet[T]':
        return OrderedSet(self, *others)

    def copy(self) -> 'OrderedSet[T]':
        return OrderedSet(self)

    def difference_update(self, *others: Iterable[T]) -> None:
        for other in others:
            for item in other:
                self.discard(item)

    def __ior__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override,misc]
        self.update(other)
        return self

    # Set algebra keeps the left operand's order first (right-hand variants:
    # the left operand is then the plain set/iterable `other`).
    def intersection(self, *others: Iterable[T]) -> 'OrderedSet[T]':
        keep = set(self)
        for other in others:
            keep &= set(other)
        return OrderedSet(t for t in self if t in keep)

    def difference(self, *others: Iterable[T]) -> 'OrderedSet[T]':
        drop: Set[T] = set()
        for other in others:
            drop |= set(other)
        return OrderedSet(t for t in self if t not in drop)

    def symmetric_difference(self, other: Iterable[T]) -> 'OrderedSet[T]':
        other_list = list(OrderedSet(other))
        o, s = set(other_list), set(self)
        return OrderedSet([t for t in self if t not in o], [t for t in other_list if t not in s])

    def __or__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return self.union(other) if isinstance(other, AbstractSet) else NotImplemented

    def __and__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return self.intersection(other) if isinstance(other, AbstractSet) else NotImplemented

    def __sub__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return self.difference(other) if isinstance(other, AbstractSet) else NotImplemented

    def __xor__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return self.symmetric_difference(other) if isinstance(other, AbstractSet) else NotImplemented

    def __ror__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return OrderedSet(other, self) if isinstance(other, AbstractSet) else NotImplemented

    def __rand__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return OrderedSet(other).intersection(self) if isinstance(other, AbstractSet) else NotImplemented

    def __rsub__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return OrderedSet(other).difference(self) if isinstance(other, AbstractSet) else NotImplemented

    def __rxor__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override]
        return OrderedSet(other).symmetric_difference(self) if isinstance(other, AbstractSet) else NotImplemented

    def intersection_update(self, *others: Iterable[T]) -> None:
        result = self.intersection(*others)
        self.clear()
        self.update(result)

    def symmetric_difference_update(self, other: Iterable[T]) -> None:
        result = self.symmetric_difference(other)
        self.clear()
        self.update(result)

    def __iand__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override,misc]
        self.intersection_update(other)
        return self

    def __isub__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override,misc]
        self.difference_update(other)
        return self

    def __ixor__(self, other: Any) -> 'OrderedSet[T]':  # type: ignore[override,misc]
        self.symmetric_difference_update(other)
        return self

    def __repr__(self) -> str:
        return '{' + ', '.join(repr(t) for t in self._order) + '}' if self._order else 'set()'


OrderedTags = OrderedSet[str]


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
        self._tags = OrderedSet(['Relationship'], tags)
        self._src = uses_data.source
        self._dst = destination
        self.model.tags = ','.join(self._tags)

        uses_data.relationship.destinationId = str(destination.model.id)

        if not isinstance(uses_data.source.model, buildzr.models.Workspace):

            # Prevent any duplicate sources/destinations, especially when creating implied relationships.
            if not any([self._dst.model.id == dest.model.id for dest in uses_data.source.destinations]):
                uses_data.source.destinations.append(self._dst)
            if not any([self._src.model.id == src.model.id for src in self._dst.sources]):
                self._dst.sources.append(self._src)

            # Make this relationship accessible from the source element.
            if not any([r.model.id == self.model.id for r in self._src.relationships]):
                self._src.relationships.add(self)

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

class _UsesFromLate(Generic[TDst], BindLeftLate[TDst]):
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

class DslElementRelationOverrides(Generic[TSrc, TDst], DslElement[TSrc, TDst]):

    """
    Base class meant to be derived from to override the `__rshift__` method to
    allow for the `>>` operator to be used to create relationships between
    elements.
    """

    # TODO: Check why need to ignore the override error here.
    @overload  # type: ignore[override]
    def __rshift__(self, other: TDst) -> _Relationship[Self, TDst]:
        """
        Create a relationship between the source element and the destination
        without specifying description or technology.

        Example: `source >> destination`.
        """
        ...

    @overload
    def __rshift__(self, description_and_technology: Tuple[str, str]) -> _UsesFrom[Self, TDst]:
        ...

    @overload
    def __rshift__(self, description: str) -> _UsesFrom[Self, TDst]:
        ...

    @overload
    def __rshift__(self, _RelationshipDescription: _RelationshipDescription[TDst]) -> _UsesFrom[Self, TDst]:
        ...

    @overload
    def __rshift__(self, multiple_destinations: List[Union[TDst, _UsesFromLate[TDst]]]) -> List[_Relationship[Self, TDst]]:
        ...

    def __rshift__(
            self,
            other: Union[
                TDst,
                str,
                Tuple[str, str],
                _RelationshipDescription[TDst],
                List[Union[TDst, _UsesFromLate[TDst]]]
            ]) -> Union[_UsesFrom[Self, TDst], _Relationship[Self, TDst], List[_Relationship[Self, TDst]]]:
        if isinstance(other, DslElement):
            return cast(
                _Relationship[Self, DslElement],
                cast(
                    _UsesFrom[Self, DslElement],
                    _UsesFrom(self)
                ) >> other
            )
        elif isinstance(other, str):
            return _UsesFrom(self, other)
        elif isinstance(other, tuple):
            return _UsesFrom(self, description=other[0], technology=other[1])
        elif isinstance(other, _RelationshipDescription):
            return _UsesFrom(self, description=other._description, technology=other._technology)
        elif isinstance(other, list):
            relationships: List[_Relationship[Self, TDst]] = []
            for dest in other:
                if isinstance(dest, _UsesFromLate):
                    dest.set_source(self)
                    relationships.append(dest.get_relationship())
                elif isinstance(dest, DslElement):
                    relationships.append(
                        cast(
                            _Relationship[Self, DslElement[Self, TDst]],
                            cast(
                                _UsesFrom[Self, DslElement[Self, TDst]],
                                _UsesFrom(self)
                            ) >> dest
                        )
                    )
            return cast(
                Union[
                    List[_Relationship[Self, TDst]],
                    _UsesFrom[Self, TDst],
                    _Relationship[Self, TDst],
                ],
                relationships
            )
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