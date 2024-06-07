from architecture import Architecture
from common import Location

class SoftwareSystems(Architecture):
    
    def __init__(
            self,
            id: str,
            name: str,
            description: str='',
            tags: set[str]=set(),
            location: Location=Location.INTERNAL,
            group: str='',
    ) -> None:
        super().__init__(
            id=id,
            name=name,
            description=description,
            tags=tags,
            location=location,
            group=group
        )
        self.containers = []