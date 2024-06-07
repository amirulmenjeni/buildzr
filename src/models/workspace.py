from typing import Self

class Workspace:

    def __init__(self, id, description='') -> None:
        self.__id = id
        self.__description = description
        self.__models: list = []