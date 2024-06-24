from dataclasses import dataclass, field
from typing import List
from .system_landscape_view import SystemLandscapeView
from .system_context_view import SystemContextView
from .container_view import ContainerView
from .component_view import ComponentView

@dataclass
class Views:

    system_landscape_views: List[SystemLandscapeView] = field(default_factory=list)

    system_context_views: List[SystemContextView] = field(default_factory=list)

    container_views: List[ContainerView] = field(default_factory=list)

    component_views: List[ComponentView] = field(default_factory=list)