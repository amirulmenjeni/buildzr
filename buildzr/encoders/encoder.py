import dataclasses, json
import enum
import humps

class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return humps.camelize(dataclasses.asdict(obj))
        elif isinstance(obj, enum.Enum):
            return str(obj)
        return super().default(obj)