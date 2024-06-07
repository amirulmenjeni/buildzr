from typing import Literal, Optional
from dataclasses import dataclass

@dataclass
class AutomaticLayout:
    implementation: Literal['Graphviz', 'Dagre'] = 'Graphviz'

    rank_direction: Literal[\
            'TopBottom',
            'BottomTop',
            'LeftRight',
            'RightLeft'
        ] = 'LeftRight'

    rank_separation: Optional[int] = None

    node_separation: Optional[int] = None

    edge_separation: Optional[int] = None

    vertices: bool = True
