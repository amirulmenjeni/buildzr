from common import InteractionStyle

class Relationship:

    def __init__(
            self,
            id: str,
            source_id: str,
            destination_id: str,
            description: str='',
            tags: set[str]=set(),
            technology: str='',
            interaction_style: InteractionStyle=InteractionStyle.SYNCHRONOUS,
            linked_relationship_id: str='',
    ):
        pass
