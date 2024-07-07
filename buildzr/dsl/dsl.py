from dataclasses import dataclass
import buildzr
from abc import ABC
from typing import Type, Generic, Union, Tuple, List, Optional, TypeVar, overload
from typing_extensions import Self
from .factory import GenerateId

class Workspace(buildzr.models.Workspace):

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_workspace()
        self.name = name
        self.description = description
        self.model = buildzr.models.Model(
            people=[],
            softwareSystems=[],
            deploymentNodes=[],
        )
        self.configuration = buildzr.models.WorkspaceConfiguration(
            scope=buildzr.models.Scope.Landscape
        )

    def contains(self, models: List[Union[
        buildzr.models.Person,
        buildzr.models.SoftwareSystem,
    ]]):
        for model in models:
            if isinstance(model, Person):
                self.model.people.append(model)
            elif isinstance(model, SoftwareSystem):
                self.model.softwareSystems.append(model)
            else:
                # Ignore other model or bad types for now.
                pass

class SoftwareSystem(buildzr.models.SoftwareSystem):

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_element()
        self.name = name
        self.description = description

class Person(buildzr.models.Person):

    def __init__(self, name: str, description: str="") -> None:
        self.id = GenerateId.for_element()
        self.name = name
        self.description = description
        self.relationships = []

    def __rshift__(self, description: str) -> 'UsesFrom':
        return UsesFrom(self, description)

Src = Union[Person, SoftwareSystem]
Dst = Union[Person, SoftwareSystem]

@dataclass
class UsesData:
    relationship: buildzr.models.Relationship
    source: Src

class UsesFrom:

    def __init__(self, source: Src, description: str="", technology: str="") -> 'UsesTo':
        self.uses_data = UsesData(
            relationship=buildzr.models.Relationship(
                id=GenerateId.for_relationship(),
                description=description,
                technology=technology,
                sourceId=source.id,
            ),
            source=source,
        )

    def __rshift__(self, destination: Dst) -> 'UsesTo':
        return UsesTo(self.uses_data, destination)

class UsesTo:

    def __init__(self, uses_data: UsesData, destination: Dst) -> None:
        uses_data.relationship.destinationId = destination.id
        if any(uses_data.source.relationships):
            uses_data.source.relationships.append(uses_data.relationship.id)
        else:
            uses_data.source.relationships = [uses_data.relationship]