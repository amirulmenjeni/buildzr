import uuid
from typing import Self, Protocol
from abc import ABC, abstractmethod
from common import Location, InteractionStyle

class Relationship:

    def __init__(
            self,
            id: str,
            source_id: str,
            destination_id: str,
            description: str='',
            tags: set[str]=set(),
            technology: str='',
            interaction_style: InteractionStyle=InteractionStyle.SYNCHRONOUS,
            linked_relationship_id: str='',
    ):
        pass

class Architecture:

    def __init__(
            self,
            id: str,
            tags: set[str]=set(),
    ) -> None:
        self.id = id
        self.tags = tags
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

class Person(Architecture):

    def __init__(
            self,
            id: str,
            name: str,
            description: str='',
            tags: set[str]=set(),
            location: Location=Location.INTERNAL,
            group: str='',
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.tags = tags
        self.location = location
        self.group = group
        self.relationships: list[Relationship] = []

class SoftwareSystems(Architecture):
    
    def __init__(self, id) -> None:
        self.id = id