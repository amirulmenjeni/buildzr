# Container view example shown in the cookbook:
# https://docs.structurizr.com/dsl/cookbook/container-view/

import buildzr
from buildzr.dsl import *
from ..abstract_builder import AbstractBuilder

class ViewSugar(AbstractBuilder):

    def build(self) -> buildzr.models.Workspace:

        w = Workspace("w")\
            .contains(
                Person("u"),
                SoftwareSystem("s"),
            )\
            .where(lambda w: [
                w.u >> "Uses" >> w.s
            ])

        print(w.model)

        return w.model

