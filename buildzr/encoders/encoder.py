import dataclasses, json
import humps

class JsonEncoder(json.JSONEncoder):
    def default(self, obj):
        if dataclasses.is_dataclass(obj):
            return humps.camelize(dataclasses.asdict(obj))
        return super().default(obj)