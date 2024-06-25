import uuid
from typing import Optional
from dataclasses import dataclass
from .model import Model

@dataclass
class Workspace:
    id: int
    name: str = ''
    description: str = ''
    version: str = ''
    model: Optional[Model] = None