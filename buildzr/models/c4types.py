from typing import NewType, Dict, Union
from enum import Enum, auto

class Location(str, Enum):
    INTERNAL    = 'Internal'
    EXTERNAL    = 'External'
    UNSPECIFIED = 'Unspecified'

class InteractionStyle(str, Enum):
    SYNCHRONOUS  = 'Synchronous'
    ASYNCHRONOUS = 'Asynchronous'

Tags = NewType('Tags', str)
Properties = NewType('Properties', Dict[str, Union[str, int, float]])