import uuid
from typing import List
from dataclasses import dataclass
from .c4types import Tags, Properties
from . import Relationship

@dataclass
class Component:
    id: int
    name: str
    description: str
    technology: str
    tags: Tags
    group: str
    properties: Properties
    relationships: List[Relationship]