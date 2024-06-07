class Container:

    def __init__(
            self,
            id: str,
            name: str,
            description: str='',
            technology: str='',
            tags: set[str]=set(),
            group: str='',
    ) -> None:
        self.id = id
        self.name = name
        self.description = description
        self.technology = technology
        self.tags = tags
        self.group = group