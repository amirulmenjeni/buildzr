import uuid
from typing import Optional
from dataclasses import dataclass
from c4types import Tags, Properties

@dataclass
class Relationship:
    description: str
    source_id: str
    destination_id: str

    tags: Optional[Tags] = None
    properties: Optional[Properties] = None
    technology: str = ''
    linked_relationship_id: str = ''
    id: str=str(uuid.uuid4())