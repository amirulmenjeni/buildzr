import uuid
from dataclasses import dataclass
from c4types import Tags, Properties
from . import Relationship

@dataclass
class Component:
    name: str
    description: str
    technology: str
    tags: Tags
    group: str
    properties: Properties
    relationships: list[Relationship]
    id: str=str(uuid.uuid4())