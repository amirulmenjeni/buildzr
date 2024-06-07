from dataclasses import dataclass
from .system_landscape_view import SystemLandscapeView
from .system_context_view import SystemContextView
from .container_view import ContainerView
from .component_view import ComponentView

@dataclass
class Views:

    system_landscape_views: list[SystemLandscapeView] = []

    system_context_views: list[SystemContextView] = []

    container_views: list[ContainerView] = []

    component_views: list[ComponentView] = []