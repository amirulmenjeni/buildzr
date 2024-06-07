from typing import NewType, Dict
from enum import StrEnum, auto

class Location(StrEnum):
    INTERNAL    = 'Internal'
    EXTERNAL    = 'External'
    UNSPECIFIED = 'Unspecified'

class InteractionStyle(StrEnum):
    SYNCHRONOUS  = 'Synchronous'
    ASYNCHRONOUS = 'Asynchronous'

Tags = NewType('Tags', str)
Properties = NewType('Properties', Dict[str, str | int | float])