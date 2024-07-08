import dataclasses, json
import enum
import humps
import buildzr

class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        # Handle the default encoder the nicely wrapped `DslElement`s.
        if isinstance(obj, buildzr.dsl.DslElement):
            return humps.camelize(dataclasses.asdict(obj._m))

        # Handle the default encoder for those `dataclass`es models generated in
        # `buildzr.model`
        elif dataclasses.is_dataclass(obj):
            return humps.camelize(dataclasses.asdict(obj))

        # Handle the enums
        elif isinstance(obj, enum.Enum):
            return str(obj)
        return super().default(obj)