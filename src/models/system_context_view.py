import uuid
from typing import Optional, Tuple
from dataclasses import dataclass
from .c4types import Properties

@dataclass
class SystemContextView:

    """A system context view.
    """

    order: int

    software_system_id: str

    dimensions: Tuple[int, int]

    title: str = ''

    description: str = ''

    properties: Optional[Properties] = None

    key: str = str(uuid.uuid4())