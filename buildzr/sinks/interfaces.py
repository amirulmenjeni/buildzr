from typing import (
    Optional,
    Any,
    TypedDict,
    TypeVar,
    Generic,
)
from dataclasses import dataclass
from abc import ABC, abstractmethod
from buildzr.models.models import Workspace

TConfig = TypeVar('TConfig')

class Sink(ABC, Generic[TConfig]):

    @abstractmethod
    def write(self, workspace: Workspace, config: Optional[TConfig]=None) -> None:
        pass