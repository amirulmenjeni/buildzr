from typing import Dict

class GenerateId:

    _data: Dict[int, int] = {
        0: 0,
        1: 0,
    }

    @staticmethod
    def for_workspace() -> int:
        GenerateId._data[0] = GenerateId._data[0] + 1
        return GenerateId._data[0]

    @staticmethod
    def for_element() -> str:
        GenerateId._data[1] = GenerateId._data[1] + 1
        return str(GenerateId._data[1])

    @staticmethod
    def for_relationship() -> str:
        GenerateId._data[1] = GenerateId._data[1] + 1
        return str(GenerateId._data[1])