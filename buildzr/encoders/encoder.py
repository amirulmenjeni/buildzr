from __future__ import annotations
import dataclasses, json
import enum
import humps
from buildzr.dsl.interfaces import DslElement, DslWorkspaceElement
from typing import Union, List, TYPE_CHECKING, Type, Any, Dict, cast
from typing_extensions import TypeGuard

if TYPE_CHECKING:
    from _typeshed import DataclassInstance
    JsonEncodable = Union[DslElement, DslWorkspaceElement, DataclassInstance, enum.Enum]
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

def _remove_nones(d: Union[dict[str, Any], List[Any]]) -> Union[dict[str, Any], List[Any]]:

    """
    Remove the `null` valued JSON objects, as they're causing problem when read
    by Structurizr.

    I'm lazy. This code is stolen and modified from https://stackoverflow.com/a/66127889.
    """

    if isinstance(d, dict):
        for key, value in list(d.items()):
            if isinstance(value, (list, dict)):
                d[key] = _remove_nones(value)
            elif value is None or key is None:
                del d[key]
    elif isinstance(d, list):
        if isinstance(d, list):
            d = [_remove_nones(item) for item in d if item is not None]

    return d

class JsonEncoder(json.JSONEncoder):
    def default(self, obj: JsonEncodable) -> Union[str, list, dict]:
        # Handle the default encoder the nicely wrapped DSL elements.
        if isinstance(obj, DslElement) or isinstance(obj, DslWorkspaceElement):
            return cast(Union[str, list, dict], humps.camelize(_remove_nones(dataclasses.asdict(obj.model))))

        # Handle the default encoder for those `dataclass`es models generated in
        # `buildzr.model`
        elif _is_dataclass(obj):
            d = dataclasses.asdict(obj)
            # Special handling for 'properties' fields of type Dict[str, Any]
            if 'properties' in d and isinstance(d['properties'], dict):
                d['properties'] = self._encode_properties(d['properties'])
            return cast(Union[str, list, dict], humps.camelize(_remove_nones(d)))

        # Handle the enums
        elif isinstance(obj, enum.Enum):
            return str(obj.value)

        return super().default(obj) #type: ignore[no-any-return]

    def _encode_properties(self, props: dict) -> dict:
        # Recursively encode values in the properties dict
        result: Dict[str, Any] = {}
        for k, v in props.items():
            if _is_dataclass(v):
                result[k] = humps.camelize(_remove_nones(dataclasses.asdict(v)))
            elif isinstance(v, enum.Enum):
                result[k] = str(v.value)
            elif isinstance(v, dict):
                result[k] = self._encode_properties(v)
            elif isinstance(v, list):
                result[k] = [self._encode_properties(i) if isinstance(i, dict) else i for i in v]
            else:
                result[k] = v
        return result