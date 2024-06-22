from buildzr.encoders import JsonEncoder
from buildzr.models import Workspace
from abc import ABCMeta, abstractmethod
import json

class AbstractBuilder(metaclass=ABCMeta):

    @abstractmethod
    def build(self) -> Workspace:
        """Builds the `Workspace` using buildzr.

        This is an abstract method, and the deriving class is required to
        overwrite this method to provide the workspace build definition.
        Otherwise, `NotImplementedError` will be raised.
        """

        raise NotImplementedError()

    def writes_json_to(self, path: str) -> None:
        """Encode the `Workspace` as JSON and write to a file.

        This method requires the `build` method to be implemented.
        """

        workspace = self.build()

        with open(path, 'w', encoding='utf-8') as f:
            json.dump(workspace, f, ensure_ascii=False, indent=4, cls=JsonEncoder)