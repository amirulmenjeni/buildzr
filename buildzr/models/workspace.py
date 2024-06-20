import uuid
from typing import List, Union
from dataclasses import dataclass, field
from .software_system import SoftwareSystem
from .person import Person

@dataclass
class Workspace:
    name: str = ''
    description: str = ''
    version: str = ''
    models: List[Union[SoftwareSystem, Person]] = field(default_factory=list)
    id: str=str(uuid.uuid4())