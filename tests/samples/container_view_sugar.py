# Container view example shown in the cookbook:
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class ViewSugar(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:
        with Workspace("w") as w:
            u = Person("u")
            s = SoftwareSystem("s")
            u >> "Uses" >> s
        print(w.model)
        return w.model

