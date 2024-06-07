import uuid
from typing import Self
from dataclasses import dataclass
from .software_system import SoftwareSystem
from .person import Person

@dataclass
class Workspace:
    name: str = ''
    description: str = ''
    version: str = ''
    models: list[SoftwareSystem | Person] = []
    id: str=str(uuid.uuid4())