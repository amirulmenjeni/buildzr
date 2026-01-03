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

    @staticmethod
    def set_offset(offset: int) -> None:
        """
        Set the element/relationship ID counter to start after the given offset.

        This is used when extending a workspace to ensure new element IDs
        don't collide with IDs from the extended (parent) workspace.

        Args:
            offset: The highest ID from the parent workspace. New IDs will
                    start at offset + 1.
        """
        GenerateId._data[1] = offset

    @staticmethod
    def reset() -> None:
        """
        Reset all ID counters to zero.

        Primarily used in testing to ensure clean state between tests.
        """
        GenerateId._data[0] = 0
        GenerateId._data[1] = 0