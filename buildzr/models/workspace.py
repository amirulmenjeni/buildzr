import uuid
from typing import Optional
from dataclasses import dataclass
from .model import Model
from .properties import Properties

@dataclass
class Workspace:
    id: int
    name: str = ''
    description: str = ''
    version: str = ''
    model: Optional[Model] = None
    properties: Optional[Properties] = None