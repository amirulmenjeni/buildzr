import uuid
from typing import List
from dataclasses import dataclass
from .software_system import SoftwareSystem
from .person import Person

@dataclass
class Model:
    people: List[Person]
    softwareSystems: List[SoftwareSystem]