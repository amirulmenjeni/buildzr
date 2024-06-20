import uuid
from typing import Optional, List
from dataclasses import dataclass, field
from .c4types import Location, Tags, Properties
from . import Relationship

@dataclass
class SoftwareSystem:
    name: str

    description: str = ''
    location: Location = Location.UNSPECIFIED
    relationships: List[Relationship] = field(default_factory=list)
    tags: Optional[Tags] = None
    group: str=''
    properties: Optional[Properties]=None
    id: str=str(uuid.uuid4())