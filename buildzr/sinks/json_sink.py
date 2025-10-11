from typing import (
    Optional,
)
from dataclasses import dataclass
from buildzr.models.models import Workspace
from buildzr.encoders.encoder import JsonEncoder
from buildzr.sinks.interfaces import Sink

@dataclass
class JsonSinkConfig:
    path: str
    pretty: bool = False

class JsonSink(Sink[JsonSinkConfig]):

    def write(self, workspace: Workspace, config: Optional[JsonSinkConfig]=None) -> None:
        if config is not None:
            indent = 2 if config.pretty else None
            with open(config.path, 'w') as file:
                file.write(JsonEncoder(indent=indent).encode(workspace))
        else:
            import os
            workspace_name = workspace.name.replace(' ', '_').lower()

            with open(os.path.join(os.curdir, f'{workspace_name}.json'), 'w') as file:
                file.write(JsonEncoder().encode(workspace))