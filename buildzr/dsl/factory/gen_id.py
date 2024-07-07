from typing import Dict

class GenerateId:

    _data: Dict[str, int] = {
        0: 0,
        1: 0,
    }

    def for_workspace() -> int:
        GenerateId._data[0] = GenerateId._data[0] + 1
        return GenerateId._data[0]

    def for_element() -> int:
        GenerateId._data[1] = GenerateId._data[1] + 1
        return GenerateId._data[1]

    def for_relationship() -> int:
        GenerateId._data[1] = GenerateId._data[1] + 1
        return GenerateId._data[1]