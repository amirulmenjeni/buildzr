from __future__ import annotations
import dataclasses, json
import enum
import humps
from buildzr.dsl import DslElement
from typing import Union, TYPE_CHECKING, Type, Any
from typing_extensions import TypeGuard

if TYPE_CHECKING:
    from _typeshed import DataclassInstance
    JsonEncodable = Union[DslElement, DataclassInstance, enum.Enum]
else:
    # Need this so that when we're not type checking with mypy, we're still on
    # the clear.
    JsonEncodable = Union[Any, None]

def _is_dataclass(obj: JsonEncodable) -> TypeGuard['DataclassInstance']:
    """
    Make mypy happy by ensuring that `obj` is indeed a `DataclassInstance`, and
    not merely its `Type[DataclassInstance]`.
    """

    return dataclasses.is_dataclass(obj) and not isinstance(obj, type)

class JsonEncoder(json.JSONEncoder):
    def default(self, obj: JsonEncodable) -> Union[str, list, dict]:
        # Handle the default encoder the nicely wrapped `DslElement`s.
        if isinstance(obj, DslElement):
            return humps.camelize(dataclasses.asdict(obj.model))

        # Handle the default encoder for those `dataclass`es models generated in
        # `buildzr.model`
        elif _is_dataclass(obj):
            return humps.camelize(dataclasses.asdict(obj))

        # Handle the enums
        elif isinstance(obj, enum.Enum):
            return str(obj)

        return super().default(obj) #type: ignore[no-any-return]