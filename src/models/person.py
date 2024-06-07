import uuid
from typing import Optional
from dataclasses import dataclass
from c4types import Tags, Location, Properties
from . import Relationship

@dataclass
class Person:
    name: str

    description: str = ''
    tags: Optional[Tags] = None
    location: Location = Location.UNSPECIFIED
    group: str = ''
    properties: Optional[Properties] = None
    relationships: list[Relationship] = []
    id: str=str(uuid.uuid4())