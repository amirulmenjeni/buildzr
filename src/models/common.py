from enum import StrEnum, auto

class Location(StrEnum):
    INTERNAL    = 'Internal'
    EXTERNAL    = 'External'
    UNSPECIFIED = 'Unspecified'

class InteractionStyle(StrEnum):
    SYNCHRONOUS  = 'Synchronous'
    ASYNCHRONOUS = 'Asynchronous'