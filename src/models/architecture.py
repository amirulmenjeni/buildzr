import uuid
from typing import Self, Dict
from abc import ABCMeta, abstractmethod
from common import Location
from relationship import Relationship

class Architecture(metaclass=ABCMeta):

    @abstractmethod
    def __init__(
            self,
            id: str,
            name: str='',
            description: str='',
            tags: set[str]=set(),
            location: Location=Location.INTERNAL,
            group: str='',
            properties: Dict[str, str | int]={}
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.location = location
        self.group = group
        self.properties = properties
        self.relationships: list[Relationship] = []

    def has_relationship_with(
            self,
            other: Self,
            description: str='',
            tags: set[str]=set(),
            technology: str='',
    ) -> Self:
        relationship = Relationship(
            str(uuid.uuid4()),
            source_id=self.id,
            destination_id=other.id,
            description=description,
            tags=tags,
            technology=technology
        )
        self.relationships.append(relationship)
        return self