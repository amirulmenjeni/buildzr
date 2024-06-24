import uuid
from typing import Optional, List
from dataclasses import dataclass, field
from .c4types import Tags, Location, Properties
from . import Relationship

@dataclass
class Person:
    id: int
    name: str
    description: str = ''
    tags: Optional[Tags] = None
    location: Location = Location.UNSPECIFIED
    group: str = ''
    properties: Optional[Properties] = None
    relationships: List[Relationship] = field(default_factory=list)